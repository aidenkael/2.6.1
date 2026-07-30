from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

PINNED_LOGISTICS_REPOSITORY = "aidenkael/EcommerceSkills"
PINNED_LOGISTICS_PATH = "logistics-cost-skill-2.0/"
PINNED_LOGISTICS_COMMIT = "ddad3b7486c2afc7de0b266defb3f5dd22028d00"
ADAPTER_VERSION = "2.6.1-ddad3b-v1"

# AI may propose packaging, but it must never provide authoritative money results.
FORBIDDEN_AI_FEE_FIELDS = frozenset(
    {
        "volume_weight_kg",
        "chargeable_weight_kg",
        "head_cost_cny",
        "head_cost_rmb",
        "service_fee_cny",
        "service_fee_rmb",
        "tail_fee_cny",
        "tail_fee_rmb",
        "total_head_cost_cny",
        "total_logistics_rmb",
        "system_total_cost_rmb",
        "estimated_head_cost",
        "estimated_total_cost",
        "profit_rmb",
        "profit_rate",
        "recommended_provider",
        "selected_provider",
    }
)

# The upstream keeps these defaults for old replay compatibility. The 2.6 app
# must not silently treat them as real production values.
CRITICAL_COMPATIBILITY_DEFAULTS = frozenset(
    {
        "ai_package_size_cm",
        "ai_package_weight_kg",
        "conservative_package_size_cm",
        "conservative_package_weight_kg",
    }
)


class UpstreamCompatibilityError(ValueError):
    """The pinned upstream result cannot be consumed safely."""


class AiBoundaryError(ValueError):
    """The raw AI payload crossed into deterministic fee authority."""


class CriticalDefaultError(UpstreamCompatibilityError):
    """A production package would depend on a compatibility-only default."""


@dataclass(frozen=True, slots=True)
class UpstreamScenario:
    length_cm: float
    width_cm: float
    height_cm: float
    packaged_weight_kg: float
    method: str = ""
    reason: str = ""
    confidence: str = "low"
    needs_review: bool = False

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], *, label: str) -> "UpstreamScenario":
        dimensions = raw.get("packaged_size_cm")
        if not isinstance(dimensions, (list, tuple)) or len(dimensions) != 3:
            raise UpstreamCompatibilityError(f"{label} 缺少有效 packaged_size_cm")
        try:
            length_cm, width_cm, height_cm = (float(value) for value in dimensions)
            packaged_weight_kg = float(raw.get("packaged_weight_kg"))
        except (TypeError, ValueError) as exc:
            raise UpstreamCompatibilityError(f"{label} 包装尺寸或重量不是数值") from exc
        if min(length_cm, width_cm, height_cm, packaged_weight_kg) <= 0:
            raise UpstreamCompatibilityError(f"{label} 包装尺寸与重量必须大于 0")
        return cls(
            length_cm=length_cm,
            width_cm=width_cm,
            height_cm=height_cm,
            packaged_weight_kg=packaged_weight_kg,
            method=str(raw.get("method") or ""),
            reason=str(raw.get("reason") or ""),
            confidence=str(raw.get("confidence") or "low"),
            needs_review=bool(raw.get("needs_review")),
        )


def validate_ai_proposal(payload: Mapping[str, Any]) -> None:
    """Allow rich recognition and packaging proposals, reject fee authority.

    This validation intentionally does not restrict product-specific descriptive
    fields. It only enforces the authority boundary required by 2.6.1.
    """

    forbidden = sorted(FORBIDDEN_AI_FEE_FIELDS.intersection(payload))
    if forbidden:
        joined = ", ".join(forbidden)
        raise AiBoundaryError(f"AI 输出包含确定性费用字段: {joined}")


def validate_pinned_commit(
    upstream_result: Mapping[str, Any],
    *,
    declared_source_commit: str | None = None,
) -> str:
    candidate = declared_source_commit or upstream_result.get("source_commit")
    if candidate is None:
        return PINNED_LOGISTICS_COMMIT
    candidate_text = str(candidate)
    if candidate_text != PINNED_LOGISTICS_COMMIT:
        raise UpstreamCompatibilityError(
            "物流来源 Commit 不匹配: "
            f"{candidate_text} != {PINNED_LOGISTICS_COMMIT}"
        )
    return candidate_text
