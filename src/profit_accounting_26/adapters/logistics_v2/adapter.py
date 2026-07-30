from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal, Mapping

from profit_accounting_26.domain.models import Forwarder, LogisticsQuote, PackageSpec
from profit_accounting_26.engines.logistics import calculate_logistics

from .contracts import (
    ADAPTER_VERSION,
    CRITICAL_COMPATIBILITY_DEFAULTS,
    PINNED_LOGISTICS_COMMIT,
    PINNED_LOGISTICS_PATH,
    PINNED_LOGISTICS_REPOSITORY,
    CriticalDefaultError,
    UpstreamCompatibilityError,
    UpstreamScenario,
    validate_pinned_commit,
)

PackagingMode = Literal["normal", "conservative"]


@dataclass(frozen=True, slots=True)
class AdaptedLogisticsResult:
    mode: PackagingMode
    package: PackageSpec
    quote: LogisticsQuote
    source_repository: str
    source_path: str
    source_commit: str
    adapter_version: str
    proposal_source: str
    needs_review: bool
    review_reasons: tuple[str, ...]
    user_override_used: bool
    default_fields_used: tuple[str, ...]
    calibration_audit: dict[str, Any]
    upstream_raw: dict[str, Any]


def _unique_text(values: list[Any]) -> tuple[str, ...]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return tuple(output)


def _read_scenarios(upstream_result: Mapping[str, Any]) -> dict[PackagingMode, UpstreamScenario]:
    scenarios: dict[PackagingMode, UpstreamScenario] = {}
    for mode in ("normal", "conservative"):
        raw = upstream_result.get(mode)
        if not isinstance(raw, Mapping):
            raise UpstreamCompatibilityError(f"缺少 {mode} 包装方案")
        scenarios[mode] = UpstreamScenario.from_mapping(raw, label=mode)
    return scenarios


def _to_package(scenario: UpstreamScenario) -> PackageSpec:
    return PackageSpec(
        length_cm=scenario.length_cm,
        width_cm=scenario.width_cm,
        height_cm=scenario.height_cm,
        weight_g=scenario.packaged_weight_kg * 1000.0,
    )


def adapt_upstream_result(
    upstream_result: Mapping[str, Any],
    *,
    forwarder: Forwarder,
    tail_fee_rmb: float,
    mode: PackagingMode = "normal",
    manual_package: PackageSpec | None = None,
    declared_source_commit: str | None = None,
) -> AdaptedLogisticsResult:
    """Bridge pinned logistics 2.0 output into the deterministic 2.6 engine.

    The adapter never runs packaging calibration and never trusts money values
    returned by upstream or AI. It selects an adopted package and delegates all
    fee math to ``calculate_logistics``.
    """

    if mode not in ("normal", "conservative"):
        raise UpstreamCompatibilityError(f"未知包装档: {mode}")

    source_commit = validate_pinned_commit(
        upstream_result,
        declared_source_commit=declared_source_commit,
    )
    scenarios = _read_scenarios(upstream_result)

    ai_meta_raw = upstream_result.get("ai_meta")
    ai_meta = dict(ai_meta_raw) if isinstance(ai_meta_raw, Mapping) else {}
    default_fields_used = tuple(str(value) for value in (ai_meta.get("default_fields_used") or []))
    critical_defaults = sorted(CRITICAL_COMPATIBILITY_DEFAULTS.intersection(default_fields_used))
    if critical_defaults and manual_package is None:
        raise CriticalDefaultError(
            "关键包装值来自兼容默认值，必须由用户补充后才能正式计算: "
            + ", ".join(critical_defaults)
        )

    selected = scenarios[mode]
    package = manual_package or _to_package(selected)
    package.validate()
    quote = calculate_logistics(package, forwarder, tail_fee_rmb=tail_fee_rmb)

    calibration_raw = upstream_result.get("packaging_calibration")
    calibration = deepcopy(dict(calibration_raw)) if isinstance(calibration_raw, Mapping) else {}

    review_items: list[Any] = list(upstream_result.get("review_reasons") or [])
    review_items.extend(calibration.get("warnings") or [])
    review_items.extend(calibration.get("conflicts") or [])
    if selected.needs_review:
        review_items.append(f"{mode} 包装方案要求复核")
    if critical_defaults:
        review_items.append("上游使用了兼容默认值，已由用户包装值覆盖")

    needs_review = bool(
        upstream_result.get("needs_review")
        or selected.needs_review
        or calibration.get("needs_review")
        or critical_defaults
    )

    return AdaptedLogisticsResult(
        mode=mode,
        package=package,
        quote=quote,
        source_repository=PINNED_LOGISTICS_REPOSITORY,
        source_path=PINNED_LOGISTICS_PATH,
        source_commit=source_commit or PINNED_LOGISTICS_COMMIT,
        adapter_version=ADAPTER_VERSION,
        proposal_source=str(ai_meta.get("proposal_source") or "unknown"),
        needs_review=needs_review,
        review_reasons=_unique_text(review_items),
        user_override_used=manual_package is not None,
        default_fields_used=default_fields_used,
        calibration_audit=calibration,
        upstream_raw=deepcopy(dict(upstream_result)),
    )
