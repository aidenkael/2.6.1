from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

from profit_accounting_26.domain.models import (
    AIObservation,
    PackagingProposal,
    PackagingScenario,
    PackagingState,
)


class PackagingEstimationService:
    """Generate auditable packaging candidates from structured facts.

    The imported local calibration dataset is used as a versioned suggestion
    source.  It never calculates freight money and never silently overwrites an
    external AI proposal.
    """

    ENGINE_VERSION = "packaging-estimation-v1"
    CALIBRATION_VERSION = "local-calibration-v3-77-samples"

    def __init__(
        self,
        calibration_path: str | Path | None = None,
        *,
        calibration_version: str | None = None,
    ) -> None:
        self.calibration_path = Path(calibration_path) if calibration_path else None
        self.calibration_version = calibration_version or self.CALIBRATION_VERSION
        self.samples = self._load_samples(self.calibration_path)

    def activate(self, calibration_path: str | Path, *, version: str) -> None:
        """Activate a validated calibration dataset without changing fee formulas."""
        path = Path(calibration_path)
        samples = self._load_samples(path)
        if not samples:
            raise ValueError("校准数据为空或格式无效")
        self.calibration_path = path
        self.calibration_version = version
        self.samples = samples

    @staticmethod
    def _load_samples(path: Path | None) -> list[dict[str, Any]]:
        if not path or not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    @staticmethod
    def _text_tokens(value: str) -> set[str]:
        cleaned = (
            value.lower()
            .replace("-", "_")
            .replace("/", "_")
            .replace(" ", "_")
        )
        return {token for token in cleaned.split("_") if len(token) >= 2}

    def _profile_candidates(self, observation: AIObservation) -> list[tuple[int, dict[str, Any]]]:
        product_tokens = self._text_tokens(observation.product_type or observation.product_name)
        material_tokens = self._text_tokens(observation.material)
        candidates: list[tuple[int, dict[str, Any]]] = []
        for sample in self.samples:
            if not sample.get("usable_for_rule_learning", False):
                continue
            score = 0
            sample_product_tokens = self._text_tokens(str(sample.get("product_type") or ""))
            sample_material_tokens = self._text_tokens(str(sample.get("material") or ""))
            if product_tokens and sample_product_tokens:
                overlap = product_tokens & sample_product_tokens
                score += min(6, len(overlap) * 3)
                if observation.product_type and observation.product_type == sample.get("product_type"):
                    score += 6
            if material_tokens and sample_material_tokens:
                score += min(4, len(material_tokens & sample_material_tokens) * 2)
            if observation.rigidity != "unknown" and observation.rigidity == sample.get("rigidity"):
                score += 3
            if observation.foldability != "unknown" and observation.foldability == sample.get("foldability"):
                score += 2
            if observation.compressibility != "unknown" and observation.compressibility == sample.get("compressibility"):
                score += 2
            sample_hard = any(
                sample.get(key) is True
                for key in (
                    "has_hard_bottom", "has_hard_backboard", "has_frame",
                    "has_rigid_insert", "has_rigid_parts", "requires_shape_retention",
                )
            )
            observed_hard, observed_unknown = self._hard_structure_state(observation)
            if not observed_unknown and observed_hard == sample_hard:
                score += 3
            if score >= 4:
                candidates.append((score, sample))
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[:8]

    @staticmethod
    def _hard_structure_state(observation: AIObservation) -> tuple[bool, bool]:
        values = [
            observation.has_hard_bottom,
            observation.has_hard_backboard,
            observation.has_frame,
            observation.has_rigid_insert,
            observation.has_rigid_parts,
            observation.retail_box_visible,
            observation.hard_card_visible,
            observation.requires_shape_retention,
        ]
        return any(value is True for value in values), any(value is None for value in values)

    @staticmethod
    def _round_dimension(value: float) -> float:
        return round(max(0.5, value), 1)

    @staticmethod
    def _scenario(
        *,
        label: str,
        state: PackagingState,
        method: str,
        dimensions: tuple[float, float, float] | None,
        weight_g: float | None,
        reason: str,
        confidence: str,
        needs_review: bool,
        defaults: list[str] | None = None,
    ) -> PackagingScenario:
        length = width = height = None
        if dimensions is not None:
            length, width, height = dimensions
        return PackagingScenario(
            label=label,
            packaging_state=state,
            packaging_method=method,
            length_cm=length,
            width_cm=width,
            height_cm=height,
            weight_g=weight_g,
            reasoning_summary=reason,
            confidence=confidence,
            needs_review=needs_review,
            default_fields_used=list(defaults or []),
        )

    def estimate(
        self,
        observation: AIObservation,
        *,
        external_proposal: PackagingProposal | None = None,
    ) -> PackagingProposal:
        dims = (observation.length_cm, observation.width_cm, observation.height_cm)
        dims_complete = all(value is not None and float(value) > 0 for value in dims)
        weight_complete = observation.weight_g is not None and observation.weight_g > 0
        hard_present, hard_unknown = self._hard_structure_state(observation)

        review_reasons: list[str] = []
        defaults: list[str] = []
        profile_ids: list[str] = []
        conflicts: list[str] = []

        if not dims_complete:
            review_reasons.append("裸件尺寸不足，包装尺寸暂不生成")
        if not weight_complete:
            review_reasons.append("裸重不足，包装重量暂不生成")

        candidates = self._profile_candidates(observation)
        ratios: list[float] = []
        for _, sample in candidates:
            profile_ids.append(str(sample.get("sample_id") or ""))
            raw_ratio = sample.get("size_reduction_ratio")
            if isinstance(raw_ratio, (int, float)) and 0.15 <= float(raw_ratio) <= 1.35:
                ratio = float(raw_ratio)
                ratios.append(ratio)

        ratio: float | None = statistics.median(ratios) if ratios else None
        ratio = min(1.15, max(0.3, ratio)) if ratio is not None else None

        if hard_present or observation.rigidity == "hard":
            state = PackagingState.SHAPE_RETAINED
            normal_scale, conservative_scale = 1.02, 1.08
            method_normal, method_conservative = "保形包装", "加固保形包装"
            confidence = "medium" if dims_complete and weight_complete else "low"
            reason = "检测到硬结构或保形需求，禁止激进压缩"
        elif hard_unknown:
            state = PackagingState.UNKNOWN
            normal_scale, conservative_scale = 1.02, 1.08
            method_normal, method_conservative = "待确认结构后包装", "保护性包装"
            confidence = "low"
            review_reasons.append("关键硬结构字段未知，按保护性方案处理")
            reason = "硬结构信息不完整，未按可压缩商品处理"
        elif observation.rigidity == "soft" and observation.foldability in {"good", "yes"}:
            state = PackagingState.MODERATE_COMPRESSION
            if ratio is None:
                normal_scale, conservative_scale = 1.0, 1.05
                method_normal, method_conservative = "待人工确认折叠包装", "轻折叠保护袋装"
                confidence = "low"
                review_reasons.append("未找到足够匹配的校准样本，未自动压缩尺寸")
                reason = "缺少相似样本，保留接近裸件的保护性候选"
            else:
                normal_scale = ratio ** (1 / 3)
                conservative_ratio = min(1.0, (ratio + 1.0) / 2.0)
                conservative_scale = conservative_ratio ** (1 / 3)
                method_normal, method_conservative = "折叠袋装", "轻折叠保护袋装"
                confidence = "medium" if len(ratios) >= 2 else "low"
                reason = "按结构字段和版本化校准样本生成候选"
        else:
            state = PackagingState.UNKNOWN
            normal_scale, conservative_scale = 1.0, 1.08
            method_normal, method_conservative = "常规包装", "保护性包装"
            confidence = "low"
            review_reasons.append("压缩与折叠条件不明确，未使用激进压缩")
            reason = "结构信息不足，采用接近裸件尺寸的保护性候选"

        normal_dims: tuple[float, float, float] | None = None
        conservative_dims: tuple[float, float, float] | None = None
        if dims_complete:
            raw_dims = tuple(float(value) for value in dims if value is not None)
            normal_dims = tuple(self._round_dimension(value * normal_scale) for value in raw_dims)
            conservative_dims = tuple(
                self._round_dimension(value * conservative_scale) for value in raw_dims
            )

        normal_weight: float | None = None
        conservative_weight: float | None = None
        if weight_complete:
            base_weight = float(observation.weight_g)
            size_allowance = 0.0
            if dims_complete:
                length, width, height = (float(value) for value in dims if value is not None)
                size_allowance = (length * width + length * height + width * height) / 220.0
            ratio_allowance = base_weight * (0.06 if state is PackagingState.MODERATE_COMPRESSION else 0.1)
            packaging_addition = min(300.0, max(20.0, ratio_allowance, size_allowance))
            conservative_addition = min(450.0, max(packaging_addition * 1.5, packaging_addition + 20.0))
            normal_weight = round(base_weight + packaging_addition, 1)
            conservative_weight = round(base_weight + conservative_addition, 1)
            defaults.append("size_weight_based_packaging_allowance")
            review_reasons.append("包装增重按裸重与尺寸生成候选，保存前应人工核对")

        local_normal = self._scenario(
            label="正常档",
            state=state,
            method=method_normal,
            dimensions=normal_dims,
            weight_g=normal_weight,
            reason=reason,
            confidence=confidence,
            needs_review=bool(review_reasons),
            defaults=defaults,
        )
        local_conservative = self._scenario(
            label="保守档",
            state=PackagingState.SHAPE_RETAINED if state is PackagingState.UNKNOWN else state,
            method=method_conservative,
            dimensions=conservative_dims,
            weight_g=conservative_weight,
            reason="在正常档基础上保留更多保护余量",
            confidence=confidence,
            needs_review=bool(review_reasons),
            defaults=defaults,
        )

        local_map = {
            "normal": local_normal.to_dict(),
            "conservative": local_conservative.to_dict(),
        }

        if external_proposal is not None:
            original = external_proposal.to_dict()
            if original.get("normal") != local_map["normal"] or original.get("conservative") != local_map["conservative"]:
                conflicts.append("外部AI包装候选与本地校准候选不一致；保留外部原始候选，等待人工采用")
            return PackagingProposal(
                normal=external_proposal.normal,
                conservative=external_proposal.conservative,
                proposal_source=external_proposal.proposal_source,
                needs_review=True,
                review_reasons=list(dict.fromkeys(external_proposal.review_reasons + review_reasons + conflicts)),
                original_scenarios={
                    "normal": external_proposal.normal.to_dict(),
                    "conservative": external_proposal.conservative.to_dict(),
                },
                local_proposed_scenarios=local_map,
                adjusted_scenarios={
                    "normal": external_proposal.normal.to_dict(),
                    "conservative": external_proposal.conservative.to_dict(),
                },
                conflicts=conflicts,
                applied_profile_ids=profile_ids,
                engine_version=self.ENGINE_VERSION,
                calibration_version=self.calibration_version,
            )

        return PackagingProposal(
            normal=local_normal,
            conservative=local_conservative,
            proposal_source="local_calibration",
            needs_review=bool(review_reasons),
            review_reasons=list(dict.fromkeys(review_reasons)),
            original_scenarios={},
            local_proposed_scenarios=local_map,
            adjusted_scenarios=local_map,
            conflicts=conflicts,
            applied_profile_ids=profile_ids,
            engine_version=self.ENGINE_VERSION,
            calibration_version=self.calibration_version,
        )
