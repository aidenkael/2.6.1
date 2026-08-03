from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Any

from profit_accounting_26.domain.models import AIObservation, PackagingProposal, PackagingScenario, PackagingState


class PackagingEstimationService:
    """Arbitrate AI, CAL and generic packaging candidates under hard facts.

    CAL is local experience: it may provide a compatible candidate, but it does
    not replace a complete, self-consistent current AI packaging observation.
    """

    ENGINE_VERSION = "packaging-estimation-v2-candidate-arbitration"
    CALIBRATION_VERSION = "local-calibration-v3-77-samples-rules-v1"

    def __init__(self, calibration_path: str | Path | None = None, *,
                 calibration_version: str | None = None,
                 rule_registry_path: str | Path | None = None) -> None:
        self.calibration_path = Path(calibration_path) if calibration_path else None
        self.calibration_version = calibration_version or self.CALIBRATION_VERSION
        self.samples = self._load_list(self.calibration_path)
        self.rule_registry_path = Path(rule_registry_path) if rule_registry_path else (
            self.calibration_path.with_name("packaging_rule_registry_v1.json") if self.calibration_path else None
        )
        self.registry = self._load_registry(self.rule_registry_path)
        self.sample_by_id = {str(item.get("sample_id")): item for item in self.samples if item.get("sample_id")}

    def activate(self, calibration_path: str | Path, *, version: str) -> None:
        path = Path(calibration_path)
        samples = self._load_list(path)
        if not samples:
            raise ValueError("校准数据为空或格式无效")
        self.calibration_path = path
        self.calibration_version = version
        self.samples = samples
        sibling = path.with_name("packaging_rule_registry_v1.json")
        if sibling.is_file():
            self.rule_registry_path = sibling
            self.registry = self._load_registry(sibling)
        self.sample_by_id = {str(item.get("sample_id")): item for item in self.samples if item.get("sample_id")}

    @staticmethod
    def _load_list(path: Path | None) -> list[dict[str, Any]]:
        if not path or not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    @staticmethod
    def _load_registry(path: Path | None) -> dict[str, Any]:
        if not path or not path.is_file():
            return {"aggregate_rules": [], "sample_rules": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"aggregate_rules": [], "sample_rules": []}
        return data if isinstance(data, dict) else {"aggregate_rules": [], "sample_rules": []}

    @staticmethod
    def _text(observation: AIObservation) -> str:
        values = (
            observation.product_name, observation.product_type, observation.product_family,
            observation.material, observation.material_family, observation.product_type_code,
            observation.product_family_code, observation.material_family_code,
        )
        return " ".join(str(value or "").lower() for value in values)

    @staticmethod
    def _complete(values: tuple[float | None, ...]) -> bool:
        return all(value is not None and float(value) > 0 for value in values)

    @staticmethod
    def _hard_state(observation: AIObservation) -> tuple[bool, bool]:
        values = (
            observation.has_hard_bottom, observation.has_hard_backboard,
            observation.has_frame, observation.has_rigid_insert,
            observation.has_rigid_parts, observation.retail_box_visible,
            observation.hard_card_visible, observation.requires_shape_retention,
        )
        return any(value is True for value in values), any(value is None for value in values)

    @staticmethod
    def _actions(observation: AIObservation) -> set[str]:
        return {str(value) for value in (observation.packing_actions or []) if str(value)}

    @staticmethod
    def _constraints(observation: AIObservation) -> set[str]:
        return {str(value) for value in (observation.packing_constraints or []) if str(value)}

    @staticmethod
    def _scenario(label: str, state: PackagingState, method: str,
                  dims: tuple[float, float, float] | None, weight: float | None,
                  reason: str, confidence: str, needs_review: bool,
                  defaults: list[str] | None = None) -> PackagingScenario:
        length = width = height = None
        if dims:
            length, width, height = (round(max(0.5, float(value)), 1) for value in dims)
        return PackagingScenario(
            label=label, packaging_state=state, packaging_method=method,
            length_cm=length, width_cm=width, height_cm=height,
            weight_g=round(float(weight), 1) if weight else None,
            reasoning_summary=reason, confidence=confidence,
            needs_review=needs_review, default_fields_used=list(defaults or []),
        )

    def _match_rule(self, rule: dict[str, Any], observation: AIObservation) -> bool:
        match = rule.get("match") or {}
        text = self._text(observation)
        terms = [str(value).lower() for value in match.get("any_terms") or []]
        if terms and not any(term in text for term in terms):
            return False
        materials = [str(value).lower() for value in match.get("materials") or []]
        if materials and not any(term in str(observation.material or "").lower() for term in materials):
            return False
        for field in ("rigidity", "foldability", "compressibility"):
            allowed = match.get(field)
            if allowed and getattr(observation, field, "unknown") not in allowed:
                return False
        if match.get("forbid_hard_structure"):
            hard, _ = self._hard_state(observation)
            if hard:
                return False
        expected_shape = match.get("requires_shape_retention")
        if expected_shape is not None and observation.requires_shape_retention is not expected_shape:
            return False
        guard = rule.get("guard") or {}
        if guard:
            hard, _ = self._hard_state(observation)
            guard_hit = bool(guard.get("any_hard_structure_or_shape_retention") and (hard or observation.requires_shape_retention is True))
            if observation.foldability in guard.get("foldability_not", []):
                guard_hit = False
            if not guard_hit and hard is False and observation.foldability == "good":
                return False
        return True

    @staticmethod
    def _cal_compatibility_observation(observation: AIObservation) -> AIObservation:
        """Map only already-recognised aliases to the legacy CAL vocabulary."""
        product_type = observation.product_type
        if product_type in {"", "unknown"} and observation.product_type_code not in {"", "unknown"}:
            product_type = observation.product_type_code
        product_family = observation.product_family
        if product_family in {"", "unknown"} and observation.product_family_code not in {"", "unknown"}:
            product_family = observation.product_family_code
        material = observation.material
        if material in {"", "unknown"} and observation.material_family not in {"", "unknown"}:
            material = observation.material_family
        return replace(observation, product_type=product_type, product_family=product_family, material=material)

    @staticmethod
    def _sample_reference_dimensions(rule: dict[str, Any], sample: dict[str, Any] | None) -> tuple[float, float, float] | None:
        values = rule.get("reference_estimated_package_size_cm")
        if not values and sample:
            values = sample.get("actual_package_size_cm") or sample.get("estimated_package_size_cm")
        if not isinstance(values, (list, tuple)) or len(values) != 3:
            return None
        try:
            dims = tuple(float(value) for value in values)
        except (TypeError, ValueError):
            return None
        return dims if all(value > 0 for value in dims) else None

    @staticmethod
    def _sample_reference_weight_g(sample: dict[str, Any] | None) -> float | None:
        if not sample:
            return None
        for key, multiplier in (("actual_weight_with_pkg_g", 1.0), ("estimated_weight_kg", 1000.0),
                                ("estimated_package_weight_kg", 1000.0)):
            try:
                value = float(sample.get(key))
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value * multiplier
        return None

    def _sample_rule_match(self, rule: dict[str, Any], observation: AIObservation) -> tuple[str | None, list[str], list[str], list[str]]:
        """Use legacy sample vocabulary without inventing a category from a title."""
        type_values = {str(value).lower() for value in (observation.product_type, observation.product_type_code,
                                                         observation.product_family, observation.product_family_code) if value and value != "unknown"}
        material_values = {str(value).lower() for value in (observation.material, observation.material_family,
                                                             observation.material_family_code) if value and value != "unknown"}
        rule_type = str(rule.get("product_type") or "").lower()
        if not rule_type or rule_type not in type_values:
            return None, [], [], ["product_type"]
        matched, missing, conflicting = ["product_type"], [], []
        rule_material = str(rule.get("material") or "").lower()
        if rule_material:
            if material_values and rule_material not in material_values:
                conflicting.append("material")
            elif rule_material in material_values:
                matched.append("material")
            else:
                missing.append("material")
        rule_rigidity = str(rule.get("rigidity") or "").lower()
        if rule_rigidity and rule_rigidity != "unknown":
            if observation.rigidity not in {"", "unknown", rule_rigidity}:
                conflicting.append("rigidity")
            elif observation.rigidity == rule_rigidity:
                matched.append("rigidity")
            else:
                missing.append("rigidity")
        required_shape = rule.get("requires_shape_retention")
        if required_shape is not None:
            if observation.requires_shape_retention is not None and observation.requires_shape_retention is not required_shape:
                conflicting.append("requires_shape_retention")
            elif observation.requires_shape_retention is required_shape:
                matched.append("requires_shape_retention")
            else:
                missing.append("requires_shape_retention")
        if conflicting:
            return None, matched, missing, conflicting
        strength = "strong" if len(matched) >= 2 and not missing else "medium"
        return strength, matched, missing, conflicting

    def _sample_cal_candidate(self, rule: dict[str, Any], observation: AIObservation) -> tuple[PackagingScenario | None, PackagingScenario | None]:
        sample = self.sample_by_id.get(str(rule.get("rule_id")))
        dims = self._sample_reference_dimensions(rule, sample)
        weight = self._sample_reference_weight_g(sample)
        if observation.weight_scope != "packaged_weight" and observation.weight_g and weight is not None:
            weight = max(weight, float(observation.weight_g) + max(20.0, float(observation.weight_g) * 0.08))
        if not dims and weight is None:
            return None, None
        state = self._state(observation)
        normal = self._scenario("正常档", state, f"CAL {rule.get('rule_id')}", dims, weight,
                                "legacy calibration reference", "low", True, [str(rule.get("rule_id"))])
        conservative_dims = tuple(value * 1.08 for value in dims) if dims else None
        conservative_weight = max(weight, weight * 1.12) if weight else None
        conservative = self._scenario("保守档", state, f"CAL {rule.get('rule_id')} (conservative)", conservative_dims,
                                      conservative_weight, "legacy calibration reference", "low", True, [str(rule.get("rule_id"))])
        return normal, conservative

    @staticmethod
    def _scale_smallest(dims: tuple[float, float, float], scale: float, minimum: float) -> tuple[float, float, float]:
        values = list(map(float, dims))
        values[min(range(3), key=values.__getitem__)] = max(minimum, min(values) * scale)
        return tuple(values)

    @staticmethod
    def _add_smallest(dims: tuple[float, float, float], amount: float) -> tuple[float, float, float]:
        values = list(map(float, dims))
        values[min(range(3), key=values.__getitem__)] += amount
        return tuple(values)

    @staticmethod
    def _volume_scale(dims: tuple[float, float, float], ratio: float) -> tuple[float, float, float]:
        factor = max(0.25, min(1.3, ratio)) ** (1 / 3)
        return tuple(float(value) * factor for value in dims)

    @staticmethod
    def _reference_template(current: tuple[float, float, float], action: dict[str, Any], key: str) -> tuple[float, float, float]:
        reference = action["reference_product_size_cm"]
        scale = (math.prod(current) / math.prod(float(value) for value in reference)) ** (1 / 3)
        scale = max(float(action.get("scale_min", 0.5)), min(float(action.get("scale_max", 3.0)), scale))
        return tuple(float(value) * scale for value in action[key])

    def _apply_action(self, dims: tuple[float, float, float], action: dict[str, Any], *, conservative: bool) -> tuple[float, float, float]:
        kind = action.get("type")
        if kind == "smallest_axis_scale":
            return self._scale_smallest(dims, float(action["conservative" if conservative else "normal"]), float(action.get("min_cm", 0.5)))
        if kind == "smallest_axis_add":
            return self._add_smallest(dims, float(action["conservative_cm" if conservative else "normal_cm"]))
        if kind == "volume_ratio":
            return self._volume_scale(dims, float(action["conservative" if conservative else "normal"]))
        if kind == "reference_scaled_template":
            return self._reference_template(dims, action, "conservative_package_size_cm" if conservative else "normal_package_size_cm")
        return dims

    def _state(self, observation: AIObservation) -> PackagingState:
        hint = observation.packaging_state_hint
        if hint != PackagingState.UNKNOWN.value and hint in {item.value for item in PackagingState}:
            return PackagingState(hint)
        actions, constraints = self._actions(observation), self._constraints(observation)
        if observation.requires_shape_retention is True or "retain_shape" in actions or "rigid_outline" in constraints:
            return PackagingState.SHAPE_RETAINED
        if "flat_fold" in actions or observation.overall_form in {"soft_flat", "hard_flat"}:
            return PackagingState.FULL_FLAT_FOLD
        if "compress" in actions or observation.compressibility == "good":
            return PackagingState.STRONG_COMPRESSION
        return PackagingState.MODERATE_COMPRESSION

    def _transport_outline(self, dims: tuple[float, float, float], observation: AIObservation) -> tuple[float, float, float]:
        """Apply a declared packing action before deriving a transport envelope."""
        actions, constraints = self._actions(observation), self._constraints(observation)
        if ("longest_nonfoldable_axis" in constraints or "rigid_outline" in constraints
                or observation.requires_shape_retention is True or "retain_shape" in actions):
            return dims
        longest, middle, shortest = sorted((float(value) for value in dims), reverse=True)
        if "coil" in actions:
            side = max(middle, math.sqrt(longest * middle))
            depth = max(shortest, (longest * middle * shortest) / (side * side))
            return tuple(sorted((side, side, depth), reverse=True))
        if "flat_fold" in actions:
            folded_length = max(middle, longest / 3.0)
            folded_depth = max(shortest, (longest * shortest) / folded_length)
            return tuple(sorted((folded_length, middle, folded_depth), reverse=True))
        if "nest" in actions or "disassemble" in actions:
            return tuple(sorted(self._volume_scale((longest, middle, shortest), 0.8), reverse=True))
        if "compress" in actions:
            return tuple(sorted(self._volume_scale((longest, middle, shortest), 0.75), reverse=True))
        return dims

    def _generic_fallback(self, observation: AIObservation):
        """Last-resort proposal based on physical form, never material hardness alone."""
        identifiable = bool(observation.product_name or observation.product_type or observation.product_family_code != "unknown")
        if not identifiable:
            return None
        form = observation.overall_form
        actions, constraints = self._actions(observation), self._constraints(observation)
        if observation.requires_shape_retention is True or "retain_shape" in actions or "rigid_outline" in constraints:
            return (20.0, 15.0, 8.0), (23.0, 18.0, 11.0), 250.0, 320.0, PackagingState.SHAPE_RETAINED, "explicit_shape_retained"
        if form in {"soft_flat", "hard_flat"} or "flat_fold" in actions:
            return (25.0, 15.0, 2.0), (27.0, 17.0, 4.0), 60.0, 90.0, PackagingState.FULL_FLAT_FOLD, "flat_form"
        if form == "flexible_chain" or "coil" in actions:
            return (20.0, 15.0, 2.0), (23.0, 18.0, 4.0), 80.0, 120.0, PackagingState.MODERATE_COMPRESSION, "flexible_coiled"
        if form == "hard_long":
            return (25.0, 8.0, 4.0), (28.0, 10.0, 6.0), 180.0, 240.0, PackagingState.MODERATE_COMPRESSION, "hard_long_protected"
        if form == "soft_bulky":
            return (28.0, 20.0, 8.0), (31.0, 23.0, 11.0), 180.0, 250.0, PackagingState.MODERATE_COMPRESSION, "soft_bulky_protected"
        if observation.compressibility == "good" and observation.foldability == "good":
            return (25.0, 15.0, 2.0), (27.0, 17.0, 4.0), 60.0, 90.0, PackagingState.FULL_FLAT_FOLD, "soft_foldable"
        return (25.0, 18.0, 5.0), (28.0, 21.0, 8.0), 120.0, 180.0, PackagingState.MODERATE_COMPRESSION, "unknown_identifiable_product"

    @staticmethod
    def _monotonic(normal: PackagingScenario, conservative: PackagingScenario) -> bool:
        return all(float(getattr(conservative, key) or 0) >= float(getattr(normal, key) or 0)
                   for key in ("length_cm", "width_cm", "height_cm", "weight_g"))

    def _validate_candidate(self, normal: PackagingScenario, conservative: PackagingScenario,
                            observation: AIObservation) -> list[str]:
        reasons: list[str] = []
        if not normal.is_complete() or not conservative.is_complete():
            reasons.append("missing_or_nonpositive_dimensions_or_weight")
        if not self._monotonic(normal, conservative):
            reasons.append("conservative_below_normal")
        constraints = self._constraints(observation)
        compressed = {PackagingState.FULL_FLAT_FOLD, PackagingState.STRONG_COMPRESSION}
        if "do_not_compress" in constraints and normal.packaging_state in compressed:
            reasons.append("violates_do_not_compress")
        if "longest_nonfoldable_axis" in constraints and observation.length_cm and normal.length_cm and normal.length_cm < observation.length_cm:
            reasons.append("shorter_than_nonfoldable_axis")
        if "rigid_outline" in constraints and normal.packaging_state == PackagingState.FULL_FLAT_FOLD:
            reasons.append("violates_rigid_outline")
        if observation.weight_scope != "packaged_weight" and observation.weight_g and normal.weight_g:
            if float(normal.weight_g) < float(observation.weight_g):
                reasons.append("packaged_weight_below_confirmed_net_weight")
        raw_dims = (observation.length_cm, observation.width_cm, observation.height_cm)
        if observation.dimension_scope == "product_size" and self._complete(raw_dims):
            transport_dims = self._transport_outline(tuple(float(value) for value in raw_dims), observation)
            declared_reduction = normal.packaging_state in {
                PackagingState.FULL_FLAT_FOLD, PackagingState.STRONG_COMPRESSION,
            }
            if transport_dims != tuple(float(value) for value in raw_dims) or declared_reduction:
                if max(float(normal.length_cm or 0), float(normal.width_cm or 0), float(normal.height_cm or 0)) >= max(raw_dims):
                    reasons.append("packing_action_not_reflected_in_outline")
        return reasons

    @staticmethod
    def _evidence_text(observation: AIObservation) -> str:
        evidence = observation.raw_payload.get("field_evidence", {}) if observation.raw_payload else {}
        try:
            return json.dumps(evidence, ensure_ascii=False).lower()
        except (TypeError, ValueError):
            return ""

    def _validate_ai_semantics(self, normal: PackagingScenario, conservative: PackagingScenario,
                               observation: AIObservation) -> list[str]:
        """Reject only semantically impossible AI proposals before arbitration."""
        reasons: list[str] = []
        if observation.raw_payload.get("dimension_semantic_issue") == "dimension_evidence_not_outer_dimensions":
            reasons.append("dimension_evidence_not_outer_dimensions")

        evidence_text = self._evidence_text(observation)
        box_words = ("纸盒", "纸箱", "礼盒", "carton", "box")
        method = " ".join((normal.packaging_method, conservative.packaging_method)).lower()
        individual_evidence = (
            observation.retail_box_visible is True
            or any(token in evidence_text for token in ("单件", "每件", "独立", "原盒", "包装盒", "individual package", "each item"))
        )
        if any(word in method for word in box_words) and not individual_evidence:
            reasons.append("unsupported_individual_package_type")

        bare_weight = observation.weight_g
        if (observation.weight_scope != "packaged_weight" and bare_weight and normal.weight_g
                and any(word in method for word in box_words)
                and float(normal.weight_g) <= float(bare_weight)):
            reasons.append("packaged_weight_has_no_material_increment")

        hard_structure, _ = self._hard_state(observation)
        unsupported_shape = (
            normal.packaging_state == PackagingState.SHAPE_RETAINED
            and observation.requires_shape_retention is not True
            and "retain_shape" not in self._actions(observation)
            and not hard_structure
            and (observation.overall_form in {"soft_flat", "flexible_chain"} or observation.foldability == "good")
        )
        if unsupported_shape:
            reasons.append("unsupported_shape_retention")
        return reasons

    def _remove_unsupported_shape_retention(self, observation: AIObservation) -> tuple[AIObservation, list[str]]:
        """Remove only a conflicting shape-retention conclusion, not usable structure facts."""
        actions = self._actions(observation)
        constraints = self._constraints(observation)
        rigid_evidence = any(value is True for value in (
            observation.has_hard_bottom, observation.has_hard_backboard, observation.has_frame,
            observation.has_rigid_insert, observation.has_rigid_parts, observation.retail_box_visible,
            observation.hard_card_visible,
        )) or bool({"rigid_outline", "longest_nonfoldable_axis", "fragile_protrusion"} & constraints)
        flexible = observation.overall_form in {"flexible_chain", "soft_flat"} and (
            observation.foldability == "good" or bool({"coil", "flat_fold"} & actions)
        )
        if not flexible or rigid_evidence or observation.requires_shape_retention is not True:
            return observation, []
        raw_payload = dict(observation.raw_payload)
        raw_payload.setdefault("structural_conflict_adjustments", []).append("unsupported_shape_retention_removed")
        return replace(
            observation,
            requires_shape_retention=None,
            packaging_state_hint="unknown" if observation.packaging_state_hint == PackagingState.SHAPE_RETAINED.value else observation.packaging_state_hint,
            packing_actions=[action for action in observation.packing_actions if action != "retain_shape"],
            raw_payload=raw_payload,
        ), ["unsupported_shape_retention_removed"]

    def _local_completion_candidate(self, observation: AIObservation,
                                    base_dims: tuple[float, float, float] | None,
                                    base_weight: float | None) -> tuple[PackagingScenario | None, PackagingScenario | None, str | None]:
        fallback = self._generic_fallback(observation)
        if not fallback:
            return None, None, None
        normal_dims, conservative_dims, normal_weight, conservative_weight, state, fallback_id = fallback
        if base_dims and base_weight is not None:
            normal, conservative = self._proposal_from_dims(
                observation, source="local", dims=base_dims, weight=base_weight,
                method="local structural completion", confidence="low", ids=["GENERIC-OBSERVED-STRUCTURE"],
            )
            return normal, conservative, "observed_structure"
        if observation.weight_scope != "packaged_weight" and observation.weight_g and observation.weight_g > 0:
            normal_weight = max(normal_weight, float(observation.weight_g) + max(20.0, float(observation.weight_g) * 0.08))
            conservative_weight = max(conservative_weight, normal_weight)
        normal = self._scenario("正常档", state, f"generic fallback: {fallback_id}", normal_dims, normal_weight,
                                "missing fields completed from observed structure", "low", True, [f"GENERIC-{fallback_id.upper()}"])
        conservative = self._scenario("保守档", state, f"generic fallback: {fallback_id} (conservative)", conservative_dims,
                                      conservative_weight, "missing fields completed from observed structure", "low", True,
                                      [f"GENERIC-{fallback_id.upper()}"])
        return normal, conservative, fallback_id

    def _salvage_ai_candidate(self, normal: PackagingScenario, conservative: PackagingScenario,
                              observation: AIObservation, reasons: list[str],
                              local_normal: PackagingScenario | None,
                              local_conservative: PackagingScenario | None) -> tuple[PackagingScenario | None, PackagingScenario | None, dict[str, list[str]]]:
        """Preserve reliable AI fields and complete only rejected or missing fields locally."""
        diagnostic = {"user_confirmed": ["weight_g"] if observation.weight_scope == "net_weight" else [],
                      "ai_preserved": [], "ai_rejected": [], "local_completed": [], "cal_adjusted": []}
        if not local_normal or not local_conservative:
            return None, None, diagnostic
        rejected = set(reasons)
        dimension_rejected = bool(rejected & {"dimension_evidence_not_outer_dimensions", "packing_action_not_reflected_in_outline", "unsupported_shape_retention"})
        weight_rejected = bool(rejected & {"packaged_weight_below_confirmed_net_weight", "packaged_weight_has_no_material_increment", "unsupported_individual_package_type"})
        method_rejected = "unsupported_individual_package_type" in rejected
        state_rejected = "unsupported_shape_retention" in rejected

        def merge(source: PackagingScenario, local: PackagingScenario) -> PackagingScenario:
            dims_valid = self._complete((source.length_cm, source.width_cm, source.height_cm)) and not dimension_rejected
            weight_valid = source.weight_g is not None and float(source.weight_g) > 0 and not weight_rejected
            if weight_valid and observation.weight_scope != "packaged_weight" and observation.weight_g:
                weight_valid = float(source.weight_g) >= float(observation.weight_g)
            method_valid = bool(source.packaging_method) and not method_rejected
            state_valid = not state_rejected
            if dims_valid:
                diagnostic["ai_preserved"].extend(["length_cm", "width_cm", "height_cm"])
            else:
                diagnostic["ai_rejected"].append("package_dimensions")
                diagnostic["local_completed"].extend(["length_cm", "width_cm", "height_cm"])
            if weight_valid:
                diagnostic["ai_preserved"].append("packaged_weight_g")
            else:
                diagnostic["ai_rejected"].append("packaged_weight_g")
                diagnostic["local_completed"].append("packaging_increment_g")
            if method_valid:
                diagnostic["ai_preserved"].append("packaging_method")
            else:
                diagnostic["ai_rejected"].append("packaging_method")
                diagnostic["local_completed"].append("packaging_method")
            if state_valid:
                diagnostic["ai_preserved"].append("packaging_state")
            else:
                diagnostic["ai_rejected"].append("packaging_state")
                diagnostic["local_completed"].append("packaging_state")
            return replace(
                source,
                packaging_state=source.packaging_state if state_valid else local.packaging_state,
                packaging_method=source.packaging_method if method_valid else local.packaging_method,
                length_cm=source.length_cm if dims_valid else local.length_cm,
                width_cm=source.width_cm if dims_valid else local.width_cm,
                height_cm=source.height_cm if dims_valid else local.height_cm,
                weight_g=source.weight_g if weight_valid else local.weight_g,
                confidence=source.confidence if source.confidence in {"low", "medium", "high"} else local.confidence,
                needs_review=True,
            )

        merged_normal, merged_conservative = merge(normal, local_normal), merge(conservative, local_conservative)
        for field in ("length_cm", "width_cm", "height_cm", "weight_g"):
            if float(getattr(merged_conservative, field) or 0) < float(getattr(merged_normal, field) or 0):
                setattr(merged_conservative, field, getattr(merged_normal, field))
                diagnostic["local_completed"].append(field)
        return merged_normal, merged_conservative, {key: list(dict.fromkeys(value)) for key, value in diagnostic.items()}

    def _coordinate_ai_cal_fields(self, ai_normal: PackagingScenario | None, ai_conservative: PackagingScenario | None,
                                  cal_normal: PackagingScenario | None, cal_conservative: PackagingScenario | None,
                                  *, match_strength: str, observation: AIObservation) -> tuple[PackagingScenario | None, PackagingScenario | None, dict[str, Any]]:
        """Apply CAL at field level while preserving explicit facts and reliable AI evidence."""
        trace: dict[str, Any] = {"match_strength": match_strength, "adjusted_fields": {}, "risk_only": False}
        if not ai_normal or not ai_conservative or not cal_normal or not cal_conservative:
            return ai_normal, ai_conservative, trace
        ai_high_confidence = ai_normal.confidence == "high" or observation.confidence == "high"
        if match_strength == "weak" and ai_high_confidence:
            trace["risk_only"] = True
            return ai_normal, ai_conservative, trace

        normal, conservative = replace(ai_normal), replace(ai_conservative)
        for target, cal_target, name in ((normal, cal_normal, "normal"), (conservative, cal_conservative, "conservative")):
            for field in ("length_cm", "width_cm", "height_cm", "weight_g"):
                before, candidate = getattr(target, field), getattr(cal_target, field)
                if candidate is None or float(candidate) <= 0:
                    continue
                missing = before is None or float(before) <= 0
                may_override = match_strength == "strong" and not ai_high_confidence
                if field == "weight_g" and observation.weight_scope != "packaged_weight" and observation.weight_g:
                    if float(candidate) < float(observation.weight_g):
                        continue
                if missing or may_override:
                    if before != candidate:
                        setattr(target, field, candidate)
                        trace["adjusted_fields"][f"{name}.{field}"] = {"before": before, "after": candidate}
        if trace["adjusted_fields"]:
            normal.needs_review = conservative.needs_review = True
        return normal, conservative, trace

    @staticmethod
    def _record(source: str, normal: PackagingScenario | None, conservative: PackagingScenario | None,
                *, confidence: str, evidence: list[str], matched_rule_ids: list[str] | None = None,
                rejection_reasons: list[str] | None = None, adjustments: list[str] | None = None) -> dict[str, Any]:
        return {
            "source": source, "normal": normal.to_dict() if normal else None,
            "conservative": conservative.to_dict() if conservative else None,
            "confidence": confidence, "evidence": evidence,
            "matched_rule_ids": list(matched_rule_ids or []),
            "rejection_reasons": list(rejection_reasons or []), "adjustments": list(adjustments or []),
        }

    def _proposal_from_dims(self, observation: AIObservation, *, source: str,
                            dims: tuple[float, float, float], weight: float,
                            conservative_dims: tuple[float, float, float] | None = None,
                            conservative_weight: float | None = None,
                            method: str = "local protective packaging", confidence: str = "low",
                            ids: list[str] | None = None) -> tuple[PackagingScenario, PackagingScenario]:
        state = self._state(observation)
        conservative_dims = conservative_dims or tuple(value * 1.06 for value in dims)
        conservative_weight = conservative_weight if conservative_weight is not None else max(weight, weight + max(20.0, weight * 0.08))
        normal = self._scenario("正常档", state, method, dims, weight, f"{source} candidate", confidence, True, ids)
        conservative = self._scenario("保守档", state, method + " (conservative)", conservative_dims, conservative_weight,
                                      f"{source} candidate", confidence, True, ids)
        return normal, conservative

    def estimate(self, observation: AIObservation, *, external_proposal: PackagingProposal | None = None) -> PackagingProposal:
        records: dict[str, dict[str, Any]] = {}
        rejected: dict[str, list[str]] = {}
        review: list[str] = []
        applied_ids: list[str] = []
        observation, structural_adjustments = self._remove_unsupported_shape_retention(observation)
        obs_dims = (observation.length_cm, observation.width_cm, observation.height_cm)
        dims_complete = self._complete(obs_dims)
        shipping_dims = observation.dimension_scope == "shipping_package_size" and dims_complete
        shipping_weight = observation.weight_scope == "packaged_weight" and bool(observation.weight_g and observation.weight_g > 0)
        ai_normal = external_proposal.normal if external_proposal else None
        ai_conservative = external_proposal.conservative if external_proposal else None

        # Strong facts are the only unconditional priorities.
        merchant_normal = merchant_conservative = None
        merchant_weight = float(observation.weight_g) if shipping_weight else (
            float(ai_normal.weight_g) if ai_normal and ai_normal.weight_g and ai_normal.weight_g > 0 else None
        )
        if shipping_dims and merchant_weight is not None:
            merchant_normal, merchant_conservative = self._proposal_from_dims(
                observation, source="merchant", dims=tuple(float(value) for value in obs_dims), weight=merchant_weight,
                conservative_dims=tuple(float(value) for value in obs_dims), conservative_weight=merchant_weight if shipping_weight else None,
                method="verified shipping package", confidence="high")
            records["merchant_candidate"] = self._record("merchant_candidate", merchant_normal, merchant_conservative,
                                                           confidence="high", evidence=["merchant_shipping_package"])

        if ai_normal and ai_conservative:
            ai_reasons = self._validate_candidate(ai_normal, ai_conservative, observation)
            ai_reasons.extend(reason for reason in self._validate_ai_semantics(ai_normal, ai_conservative, observation)
                              if reason not in ai_reasons)
            if shipping_dims and ai_normal.is_complete() and tuple(round(float(value), 1) for value in (ai_normal.length_cm, ai_normal.width_cm, ai_normal.height_cm)) != tuple(round(float(value), 1) for value in obs_dims):
                ai_reasons.append("conflicts_with_merchant_shipping_dimensions")
            records["ai_candidate"] = self._record("ai_candidate", ai_normal, ai_conservative,
                                                    confidence=ai_normal.confidence, evidence=["vision_packaging_proposal"],
                                                    matched_rule_ids=external_proposal.applied_profile_ids,
                                                    rejection_reasons=ai_reasons)
            if ai_reasons:
                rejected["ai_candidate"] = ai_reasons

        observed_base_dims = self._transport_outline(tuple(float(value) for value in obs_dims), observation) if dims_complete else None
        observed_base_weight = float(observation.weight_g) if observation.weight_g and observation.weight_g > 0 else None
        if observed_base_weight is not None and not shipping_weight and observation.weight_scope != "packaged_weight":
            observed_base_weight += max(20.0, min(300.0, observed_base_weight * 0.08))
        local_normal, local_conservative, local_fallback_id = self._local_completion_candidate(
            observation, observed_base_dims, observed_base_weight,
        )
        salvaged_normal = salvaged_conservative = None
        salvage_diagnostic: dict[str, list[str]] | None = None
        if ai_normal and ai_conservative and rejected.get("ai_candidate"):
            salvaged_normal, salvaged_conservative, salvage_diagnostic = self._salvage_ai_candidate(
                ai_normal, ai_conservative, observation, rejected["ai_candidate"], local_normal, local_conservative,
            )
            salvaged_reasons = (self._validate_candidate(salvaged_normal, salvaged_conservative, observation)
                                if salvaged_normal and salvaged_conservative else ["no_local_completion_candidate"])
            if salvaged_reasons:
                rejected["salvaged_ai_candidate"] = salvaged_reasons
            records["candidate_field_salvage"] = {
                "source": "candidate_field_salvage", "normal": salvaged_normal.to_dict() if salvaged_normal else None,
                "conservative": salvaged_conservative.to_dict() if salvaged_conservative else None,
                "confidence": salvaged_normal.confidence if salvaged_normal else "low",
                "evidence": ["field_level_candidate_merge"], "matched_rule_ids": [],
                "rejection_reasons": [*rejected["ai_candidate"], *salvaged_reasons],
                "adjustments": [*structural_adjustments], "diagnostic": salvage_diagnostic,
            }
        elif structural_adjustments:
            records["candidate_field_salvage"] = {
                "source": "candidate_field_salvage", "normal": None, "conservative": None, "confidence": "low",
                "evidence": ["structural_conflict_correction"], "matched_rule_ids": [],
                "rejection_reasons": [], "adjustments": structural_adjustments,
                "diagnostic": {"user_confirmed": [], "ai_preserved": ["overall_form", "foldability", "packing_actions"],
                               "ai_rejected": ["requires_shape_retention"], "local_completed": [], "cal_adjusted": []},
            }

        cal_observation = self._cal_compatibility_observation(observation)
        matched = [rule for rule in sorted(self.registry.get("aggregate_rules", []), key=lambda item: int(item.get("priority", 0)), reverse=True)
                   if rule.get("enabled", True) and self._match_rule(rule, cal_observation)]
        selected = matched[0] if matched else None
        sample_matches: list[tuple[dict[str, Any], str, list[str], list[str], list[str]]] = []
        for rule in self.registry.get("sample_rules", []):
            if not rule.get("enabled", True):
                continue
            strength, matched_fields, missing_fields, conflicting_fields = self._sample_rule_match(rule, cal_observation)
            if strength:
                sample_matches.append((rule, strength, matched_fields, missing_fields, conflicting_fields))
        selected_sample = next((item for item in sample_matches if item[1] == "strong" and item[0].get("role") != "guard_only"), None)
        if selected_sample is None and selected is None:
            selected_sample = next((item for item in sample_matches if item[0].get("role") != "guard_only"), None)
        records["cal_match_audit"] = {
            "source": "cal_compatibility_adapter",
            "aggregate_rule_ids": [str(rule.get("rule_id")) for rule in matched],
            "sample_matches": [{"rule_id": str(rule.get("rule_id")), "match_strength": strength,
                                "matched_fields": fields, "missing_fields": missing, "conflicting_fields": conflicts,
                                "role": rule.get("role")} for rule, strength, fields, missing, conflicts in sample_matches],
        }
        valid_ai_candidate = ai_normal and ai_conservative and "ai_candidate" not in rejected
        usable_ai_normal = ai_normal if valid_ai_candidate else salvaged_normal
        usable_ai_conservative = ai_conservative if valid_ai_candidate else salvaged_conservative
        base_dims = observed_base_dims
        base_weight = observed_base_weight
        if not base_dims and usable_ai_normal and usable_ai_normal.is_complete():
            base_dims = (float(usable_ai_normal.length_cm), float(usable_ai_normal.width_cm), float(usable_ai_normal.height_cm))
        if base_weight is None and usable_ai_normal and usable_ai_normal.weight_g:
            base_weight = float(usable_ai_normal.weight_g)

        cal_normal = cal_conservative = None
        cal_strength = "weak"
        cal_rule_ids: list[str] = []
        cal_matched_fields: list[str] = []
        cal_missing_fields: list[str] = []
        cal_conflicting_fields: list[str] = []
        if selected_sample:
            sample_rule, cal_strength, matched_fields, missing_fields, conflicting_fields = selected_sample
            cal_rule_ids = [str(sample_rule.get("rule_id"))]
            cal_matched_fields, cal_missing_fields, cal_conflicting_fields = matched_fields, missing_fields, conflicting_fields
            cal_normal, cal_conservative = self._sample_cal_candidate(sample_rule, observation)
            records["cal_candidate"] = self._record("cal_candidate", cal_normal, cal_conservative,
                                                     confidence="medium" if cal_strength == "strong" else "low",
                                                     evidence=["legacy_sample_calibration", *matched_fields],
                                                     matched_rule_ids=cal_rule_ids,
                                                     rejection_reasons=[] if cal_normal or cal_conservative else ["no_executable_cal_fields"])
        elif selected and base_dims and base_weight is not None:
            ids = list(dict.fromkeys([*selected.get("source_cal_ids", []), str(selected["rule_id"])]))
            cal_rule_ids, cal_strength = ids, "strong" if len((selected.get("match") or {})) > 1 else "medium"
            cal_matched_fields = list((selected.get("match") or {}).keys())
            normal_dims = self._apply_action(base_dims, selected.get("action") or {}, conservative=False)
            conservative_dims = self._apply_action(base_dims, selected.get("action") or {}, conservative=True)
            cal_normal, cal_conservative = self._proposal_from_dims(
                observation, source="cal", dims=normal_dims, weight=base_weight,
                conservative_dims=conservative_dims, method=str(selected["name"]),
                confidence=str(selected.get("confidence") or "low"), ids=ids)
            cal_reasons = self._validate_candidate(cal_normal, cal_conservative, observation)
            records["cal_candidate"] = self._record("cal_candidate", cal_normal, cal_conservative,
                                                     confidence=cal_normal.confidence, evidence=["compatible_cal_rule"],
                                                     matched_rule_ids=ids, rejection_reasons=cal_reasons)
            if cal_reasons:
                rejected["cal_candidate"] = cal_reasons
        elif selected:
            cal_rule_ids, cal_strength = [str(selected["rule_id"])], "medium"
            cal_matched_fields = list((selected.get("match") or {}).keys())
            records["cal_candidate"] = self._record("cal_candidate", None, None, confidence="low",
                                                     evidence=["compatible_cal_rule"], matched_rule_ids=[str(selected["rule_id"])],
                                                     rejection_reasons=["missing_base_dimensions_or_weight"])
            rejected["cal_candidate"] = ["missing_base_dimensions_or_weight"]

        coordinated_normal, coordinated_conservative, cal_trace = self._coordinate_ai_cal_fields(
            usable_ai_normal, usable_ai_conservative, cal_normal, cal_conservative,
            match_strength=cal_strength, observation=observation,
        )
        if cal_normal or cal_conservative:
            records["cal_coordination"] = {
                "source": "cal_field_arbitration", "rule_id": cal_rule_ids,
                "match_strength": cal_strength, "matched_fields": cal_matched_fields,
                "missing_fields": cal_missing_fields, "conflicting_fields": cal_conflicting_fields,
                "adjusted_fields": cal_trace["adjusted_fields"],
                "risk_only": cal_trace["risk_only"],
            }
        if cal_trace["adjusted_fields"]:
            applied_ids.extend(cal_rule_ids)

        generic_normal, generic_conservative, generic_fallback_id = self._local_completion_candidate(
            observation, base_dims, base_weight,
        )
        if generic_normal and generic_conservative:
            generic_reasons = self._validate_candidate(generic_normal, generic_conservative, observation)
            reliable_fields = bool(observation.weight_g or self._complete(obs_dims) or observation.overall_form != "unknown" or self._actions(observation))
            generic_adjustments = [] if reliable_fields else ["full_generic_fallback_no_reliable_fields"]
            records["generic_candidate"] = self._record("generic_candidate", generic_normal, generic_conservative,
                                                         confidence="low", evidence=["physical_form_fallback"],
                                                         rejection_reasons=generic_reasons, adjustments=generic_adjustments)
            if generic_reasons:
                rejected["generic_candidate"] = generic_reasons

        # A partial legacy reference may still correct its supported fields after
        # local completion supplies only the fields the reference does not have.
        if (not usable_ai_normal or not usable_ai_conservative) and generic_normal and generic_conservative and (cal_normal or cal_conservative):
            completed_normal, completed_conservative, completion_trace = self._coordinate_ai_cal_fields(
                generic_normal, generic_conservative, cal_normal, cal_conservative,
                match_strength=cal_strength, observation=observation,
            )
            if completion_trace["adjusted_fields"]:
                coordinated_normal, coordinated_conservative = completed_normal, completed_conservative
                cal_trace["adjusted_fields"].update(completion_trace["adjusted_fields"])
                cal_trace["risk_only"] = cal_trace["risk_only"] and completion_trace["risk_only"]
                applied_ids.extend(cal_rule_ids)
                if "cal_coordination" in records:
                    records["cal_coordination"]["adjusted_fields"] = cal_trace["adjusted_fields"]

        # The selected output stays a single PackagingProposal for UI, logistics and history.
        if merchant_normal and merchant_conservative:
            source, normal, conservative = "merchant_candidate", merchant_normal, merchant_conservative
            review.append("merchant shipping package facts adopted")
        elif cal_trace["adjusted_fields"] and coordinated_normal and coordinated_conservative:
            source = "ai_cal_coordinated" if usable_ai_normal and usable_ai_conservative else "cal_candidate_completed"
            normal, conservative = coordinated_normal, coordinated_conservative
            review.append(f"{cal_strength} CAL match adjusted selected packaging fields")
        elif ai_normal and ai_conservative and "ai_candidate" not in rejected:
            source, normal, conservative = "ai_candidate", ai_normal, ai_conservative
            review.append("complete AI packaging candidate adopted after local validation")
        elif salvaged_normal and salvaged_conservative and "salvaged_ai_candidate" not in rejected:
            source, normal, conservative = "ai_candidate_salvaged", salvaged_normal, salvaged_conservative
            review.append("reliable AI candidate fields preserved; missing fields completed locally")
        elif cal_normal and cal_conservative and cal_normal.is_complete() and cal_conservative.is_complete() and "cal_candidate" not in rejected:
            source, normal, conservative = "cal_candidate", cal_normal, cal_conservative
            review.append("AI candidate unavailable or invalid; compatible CAL candidate adopted")
            applied_ids.extend(cal_rule_ids)
        elif generic_normal and generic_conservative and "generic_candidate" not in rejected:
            source, normal, conservative = "generic_candidate", generic_normal, generic_conservative
            review.append("AI and CAL could not form a valid candidate; generic physical-form fallback adopted")
            if records.get("generic_candidate", {}).get("adjustments"):
                review.append("full generic fallback used because no reliable fields were available")
            applied_ids.append("GENERIC")
        else:
            source = "no_valid_candidate"
            normal = self._scenario("正常档", PackagingState.UNKNOWN, "", None, None, "no valid candidate", "low", True)
            conservative = self._scenario("保守档", PackagingState.UNKNOWN, "", None, None, "no valid candidate", "low", True)
            review.append("no complete packaging candidate could be generated")

        if rejected:
            review.extend(f"{source} rejected: {', '.join(reasons)}" for source, reasons in rejected.items())
        original = {"normal": ai_normal.to_dict(), "conservative": ai_conservative.to_dict()} if ai_normal and ai_conservative else {}
        local = {"normal": normal.to_dict(), "conservative": conservative.to_dict()}
        return PackagingProposal(
            normal=normal, conservative=conservative, proposal_source=source,
            needs_review=True, review_reasons=review, original_scenarios=original,
            local_proposed_scenarios=local, adjusted_scenarios=local,
            conflicts=[reason for reasons in rejected.values() for reason in reasons],
            applied_profile_ids=list(dict.fromkeys(applied_ids)), candidate_records=records,
            rejected_candidates=rejected, adjustments=structural_adjustments, engine_version=self.ENGINE_VERSION,
            calibration_version=self.calibration_version,
        )
