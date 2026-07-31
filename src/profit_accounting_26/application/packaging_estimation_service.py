from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from profit_accounting_26.domain.models import AIObservation, PackagingProposal, PackagingScenario, PackagingState


class PackagingEstimationService:
    """CAL-77 authoritative packaging engine.

    External AI candidates are retained for audit and fallback only. Matching
    local rules produce the adopted normal/conservative scenarios. All 77 CAL
    records have a runtime role through the versioned registry.
    """

    ENGINE_VERSION = "packaging-estimation-v2-cal77-authoritative"
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
        values = [
            observation.product_name, observation.product_type,
            getattr(observation, "product_family", ""), observation.material,
            getattr(observation, "material_family", ""),
        ]
        return " ".join(str(value or "").lower() for value in values)

    @staticmethod
    def _complete(values: tuple[float | None, ...]) -> bool:
        return all(value is not None and float(value) > 0 for value in values)

    @staticmethod
    def _hard_state(observation: AIObservation) -> tuple[bool, bool]:
        values = [
            observation.has_hard_bottom, observation.has_hard_backboard,
            observation.has_frame, observation.has_rigid_insert,
            observation.has_rigid_parts, observation.retail_box_visible,
            observation.hard_card_visible, observation.requires_shape_retention,
        ]
        return any(value is True for value in values), any(value is None for value in values)

    @staticmethod
    def _scenario(label: str, state: PackagingState, method: str,
                  dims: tuple[float, float, float] | None, weight: float | None,
                  reason: str, confidence: str, needs_review: bool,
                  defaults: list[str] | None = None) -> PackagingScenario:
        length = width = height = None
        if dims:
            length, width, height = (round(max(0.5, float(v)), 1) for v in dims)
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
        terms = [str(v).lower() for v in match.get("any_terms") or []]
        if terms and not any(term in text for term in terms):
            return False
        materials = [str(v).lower() for v in match.get("materials") or []]
        if materials and not any(term in str(observation.material or "").lower() for term in materials):
            return False
        for field in ("rigidity", "foldability", "compressibility"):
            allowed = match.get(field)
            if allowed and getattr(observation, field, "unknown") not in allowed:
                return False
        if match.get("forbid_hard_structure"):
            hard, unknown = self._hard_state(observation)
            if hard or unknown:
                return False
        expected_shape = match.get("requires_shape_retention")
        if expected_shape is not None and observation.requires_shape_retention is not expected_shape:
            return False
        guard = rule.get("guard") or {}
        if guard:
            hard, _ = self._hard_state(observation)
            fold = observation.foldability
            guard_hit = bool(guard.get("any_hard_structure_or_shape_retention") and (hard or observation.requires_shape_retention is True))
            if fold in guard.get("foldability_not", []):
                guard_hit = False
            if not guard_hit and hard is False and fold == "good":
                return False
        return True

    @staticmethod
    def _scale_smallest(dims: tuple[float, float, float], scale: float, minimum: float) -> tuple[float, float, float]:
        values = list(map(float, dims))
        idx = min(range(3), key=values.__getitem__)
        values[idx] = max(minimum, values[idx] * scale)
        return tuple(values)

    @staticmethod
    def _add_smallest(dims: tuple[float, float, float], amount: float) -> tuple[float, float, float]:
        values = list(map(float, dims))
        idx = min(range(3), key=values.__getitem__)
        values[idx] += amount
        return tuple(values)

    @staticmethod
    def _volume_scale(dims: tuple[float, float, float], ratio: float) -> tuple[float, float, float]:
        factor = max(0.25, min(1.3, ratio)) ** (1 / 3)
        return tuple(float(v) * factor for v in dims)

    @staticmethod
    def _reference_template(current: tuple[float, float, float], action: dict[str, Any], key: str) -> tuple[float, float, float]:
        ref = action["reference_product_size_cm"]
        template = action[key]
        current_volume = math.prod(current)
        ref_volume = math.prod(float(v) for v in ref)
        scale = (current_volume / ref_volume) ** (1 / 3) if ref_volume > 0 else 1.0
        scale = max(float(action.get("scale_min", 0.5)), min(float(action.get("scale_max", 3.0)), scale))
        return tuple(float(v) * scale for v in template)

    def _apply_action(self, dims: tuple[float, float, float], action: dict[str, Any], *, conservative: bool) -> tuple[float, float, float]:
        kind = action.get("type")
        if kind == "smallest_axis_scale":
            scale = float(action["conservative" if conservative else "normal"])
            return self._scale_smallest(dims, scale, float(action.get("min_cm", 0.5)))
        if kind == "smallest_axis_add":
            amount = float(action["conservative_cm" if conservative else "normal_cm"])
            return self._add_smallest(dims, amount)
        if kind == "volume_ratio":
            ratio = float(action["conservative" if conservative else "normal"])
            return self._volume_scale(dims, ratio)
        if kind == "reference_scaled_template":
            key = "conservative_package_size_cm" if conservative else "normal_package_size_cm"
            return self._reference_template(dims, action, key)
        return dims

    def _sample_matches(self, observation: AIObservation) -> list[dict[str, Any]]:
        text = self._text(observation)
        material = str(observation.material or "").lower()
        ranked: list[tuple[int, dict[str, Any]]] = []
        for rule in self.registry.get("sample_rules", []):
            score = 0
            for term in rule.get("match_terms") or []:
                term = str(term).lower().strip()
                if len(term) >= 2 and term in text:
                    score += 2
            rule_material = str(rule.get("material") or "").lower()
            if rule_material and rule_material in material:
                score += 3
            if rule.get("rigidity") == observation.rigidity and observation.rigidity != "unknown":
                score += 2
            if score >= 3:
                ranked.append((score, rule))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [rule for _, rule in ranked[:8]]

    def estimate(self, observation: AIObservation, *, external_proposal: PackagingProposal | None = None) -> PackagingProposal:
        obs_dims = (observation.length_cm, observation.width_cm, observation.height_cm)
        dims_complete = self._complete(obs_dims)
        hard, hard_unknown = self._hard_state(observation)
        shipping_dims_authoritative = observation.dimension_scope == "shipping_package_size" and dims_complete
        packaged_weight_authoritative = observation.weight_scope == "packaged_weight" and observation.weight_g and observation.weight_g > 0

        external_normal = external_proposal.normal if external_proposal else None
        if shipping_dims_authoritative:
            base_dims = tuple(float(v) for v in obs_dims if v is not None)
        elif dims_complete:
            base_dims = tuple(float(v) for v in obs_dims if v is not None)
        elif external_normal and external_normal.is_complete():
            base_dims = (float(external_normal.length_cm), float(external_normal.width_cm), float(external_normal.height_cm))
        else:
            base_dims = None

        if packaged_weight_authoritative:
            base_weight = float(observation.weight_g)
        elif external_normal and external_normal.weight_g and external_normal.weight_g > 0:
            base_weight = float(external_normal.weight_g)
        elif observation.weight_g and observation.weight_g > 0:
            addition = max(20.0, min(300.0, float(observation.weight_g) * 0.08))
            base_weight = float(observation.weight_g) + addition
        else:
            base_weight = None

        review: list[str] = []
        conflicts: list[str] = []
        applied_ids: list[str] = []
        matched_aggregate = [
            rule for rule in sorted(self.registry.get("aggregate_rules", []), key=lambda r: int(r.get("priority", 0)), reverse=True)
            if rule.get("enabled", True) and self._match_rule(rule, observation)
        ]
        selected = matched_aggregate[0] if matched_aggregate else None
        sample_matches = self._sample_matches(observation)
        applied_ids.extend(str(rule.get("rule_id")) for rule in sample_matches)

        if selected:
            applied_ids = list(dict.fromkeys(selected.get("source_cal_ids", []) + [selected["rule_id"]] + applied_ids))
            review.append(f"命中本地规则：{selected['rule_id']}（{selected['name']}）")
        elif sample_matches:
            review.append("命中历史CAL相似记录，但无专用动作规则；采用样本体积比例中位数。")
        else:
            review.append("未命中专用CAL规则，采用通用保护性候选。")

        normal_dims = conservative_dims = base_dims
        state = PackagingState.UNKNOWN
        method_normal, method_conservative = "常规包装", "保护性包装"
        confidence = "low"

        if shipping_dims_authoritative:
            state = PackagingState.SHAPE_RETAINED if hard else PackagingState.UNKNOWN
            method_normal = "已验证运输包装尺寸"
            method_conservative = "已验证运输包装尺寸"
            review.append("运输包装尺寸为高优先级事实，本地规则未覆盖。")
        elif base_dims and selected:
            normal_dims = self._apply_action(base_dims, selected.get("action") or {}, conservative=False)
            conservative_dims = self._apply_action(base_dims, selected.get("action") or {}, conservative=True)
            hint = getattr(observation, "packaging_state_hint", "unknown")
            if hint in {item.value for item in PackagingState}:
                state = PackagingState(hint)
            elif hard:
                state = PackagingState.SHAPE_RETAINED
            elif observation.compressibility == "good":
                state = PackagingState.STRONG_COMPRESSION
            else:
                state = PackagingState.MODERATE_COMPRESSION
            method_normal = selected["name"]
            method_conservative = selected["name"] + "（保守）"
            confidence = str(selected.get("confidence") or "low")
        elif base_dims and sample_matches:
            ratios = [float(rule["volume_ratio"]) for rule in sample_matches if isinstance(rule.get("volume_ratio"), (int, float)) and 0.05 <= float(rule["volume_ratio"]) <= 1.35]
            if ratios:
                ratios.sort()
                ratio = ratios[len(ratios)//2]
                normal_dims = self._volume_scale(base_dims, ratio)
                conservative_dims = self._volume_scale(base_dims, min(1.0, (ratio + 1.0) / 2.0))
                state = PackagingState.MODERATE_COMPRESSION
                method_normal = "CAL相似样本比例修正"
                method_conservative = "CAL相似样本保护性修正"
        elif base_dims:
            if hard or hard_unknown:
                normal_dims = tuple(v * 1.02 for v in base_dims)
                conservative_dims = tuple(v * 1.08 for v in base_dims)
                state = PackagingState.SHAPE_RETAINED
                method_normal, method_conservative = "保形包装", "加固保形包装"
            else:
                conservative_dims = tuple(v * 1.06 for v in base_dims)

        if normal_dims and conservative_dims:
            conservative_dims = tuple(max(n, c) for n, c in zip(normal_dims, conservative_dims))

        normal_weight = base_weight
        conservative_weight = base_weight
        if base_weight is not None and not packaged_weight_authoritative:
            conservative_weight = max(base_weight, base_weight + max(20.0, base_weight * 0.08))
        if packaged_weight_authoritative:
            review.append("包装重量为高优先级事实，本地规则未覆盖。")

        if external_proposal:
            conflicts.append("外部AI包装候选已保留用于审计；页面采用本地CAL输出。")
        reason = selected.get("reason", "由本地CAL规则和当前结构化事实生成。") if selected else review[-1]
        needs_review = True  # conservative档本身承担风险提示；单样本立即启用仍保留低置信标记
        normal = self._scenario("正常档", state, method_normal, normal_dims, normal_weight, reason, confidence, needs_review, applied_ids)
        conservative = self._scenario("保守档", state, method_conservative, conservative_dims, conservative_weight, "在正常档基础上减少压缩并保留保护余量。", confidence, needs_review, applied_ids)

        local_map = {"normal": normal.to_dict(), "conservative": conservative.to_dict()}
        original = {}
        if external_proposal:
            original = {"normal": external_proposal.normal.to_dict(), "conservative": external_proposal.conservative.to_dict()}
        return PackagingProposal(
            normal=normal, conservative=conservative,
            proposal_source="local_calibration_authoritative",
            needs_review=needs_review,
            review_reasons=list(dict.fromkeys(review)),
            original_scenarios=original,
            local_proposed_scenarios=local_map,
            adjusted_scenarios=local_map,
            conflicts=conflicts,
            applied_profile_ids=list(dict.fromkeys(applied_ids)),
            engine_version=self.ENGINE_VERSION,
            calibration_version=self.calibration_version,
        )
