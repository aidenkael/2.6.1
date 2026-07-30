from copy import deepcopy

import pytest

from profit_accounting_26.adapters.logistics_v2 import (
    PINNED_LOGISTICS_COMMIT,
    AiBoundaryError,
    CriticalDefaultError,
    UpstreamCompatibilityError,
    adapt_upstream_result,
    validate_ai_proposal,
)
from profit_accounting_26.domain.models import Forwarder, PackageSpec


def upstream_result() -> dict:
    return {
        "source_commit": PINNED_LOGISTICS_COMMIT,
        "normal": {
            "packaged_size_cm": [10, 8, 4],
            "packaged_weight_kg": 0.2,
            "method": "OPP袋",
            "reason": "AI正常档候选",
            "confidence": "medium",
            "needs_review": False,
        },
        "conservative": {
            "packaged_size_cm": [12, 10, 5],
            "packaged_weight_kg": 0.25,
            "method": "稍大外袋",
            "reason": "AI保守档候选",
            "confidence": "medium",
            "needs_review": True,
        },
        "needs_review": True,
        "review_reasons": ["外部 AI 与本地校准候选不一致"],
        "ai_meta": {
            "proposal_source": "external_ai",
            "default_fields_used": [],
        },
        "packaging_calibration": {
            "needs_review": True,
            "warnings": [],
            "conflicts": ["AI包装候选与本地校准区间不一致；已保留AI原始候选，未静默覆盖"],
            "original_scenarios": {
                "normal": {"packaged_size_cm": [10, 8, 4]},
                "conservative": {"packaged_size_cm": [12, 10, 5]},
            },
            "local_proposed_scenarios": {
                "normal": {"packaged_size_cm": [9, 8, 3]},
                "conservative": {"packaged_size_cm": [11, 9, 4]},
            },
            "adjusted_scenarios": {
                "normal": {"packaged_size_cm": [10, 8, 4]},
                "conservative": {"packaged_size_cm": [12, 10, 5]},
            },
            "proposed_rule_ids": ["moderate_compression"],
            "proposed_rule_details": [
                {
                    "rule_id": "moderate_compression",
                    "rule_group": "tentative",
                }
            ],
        },
    }


def test_ai_can_propose_packaging_but_cannot_provide_fee_authority():
    validate_ai_proposal(
        {
            "product_type": "soft_pouch",
            "ai_package_size_cm": [10, 8, 4],
            "conservative_package_size_cm": [12, 10, 5],
            "reasoning_summary": "柔软可折叠",
        }
    )
    with pytest.raises(AiBoundaryError, match="确定性费用字段"):
        validate_ai_proposal(
            {
                "product_type": "soft_pouch",
                "ai_package_size_cm": [10, 8, 4],
                "estimated_total_cost": 99,
            }
        )


def test_adapter_uses_dynamic_forwarder_and_injected_tail_fee():
    result = adapt_upstream_result(
        upstream_result(),
        forwarder=Forwarder("custom", "第三家货代", 73, 8, 7000),
        tail_fee_rmb=35,
    )
    assert result.quote.actual_weight_kg == pytest.approx(0.2)
    assert result.quote.volume_weight_kg == pytest.approx(10 * 8 * 4 / 7000)
    assert result.quote.weight_fee_rmb == pytest.approx(14.6)
    assert result.quote.total_logistics_rmb == pytest.approx(57.6)
    assert result.source_commit == PINNED_LOGISTICS_COMMIT


def test_normal_and_conservative_are_both_supported():
    forwarder = Forwarder("sz", "深圳", 80, 10, 8000)
    normal = adapt_upstream_result(
        upstream_result(), forwarder=forwarder, tail_fee_rmb=40, mode="normal"
    )
    conservative = adapt_upstream_result(
        upstream_result(), forwarder=forwarder, tail_fee_rmb=40, mode="conservative"
    )
    assert normal.package == PackageSpec(10, 8, 4, 200)
    assert conservative.package == PackageSpec(12, 10, 5, 250)
    assert conservative.quote.total_logistics_rmb > normal.quote.total_logistics_rmb


def test_manual_package_overrides_adopted_value_without_mutating_ai_raw():
    raw = upstream_result()
    original = deepcopy(raw)
    manual = PackageSpec(20, 10, 10, 100)
    result = adapt_upstream_result(
        raw,
        forwarder=Forwarder("sz", "深圳", 80, 10, 8000),
        tail_fee_rmb=40,
        manual_package=manual,
    )
    assert result.package == manual
    assert result.user_override_used is True
    assert result.quote.volume_weight_kg == pytest.approx(0.25)
    assert result.quote.total_logistics_rmb == pytest.approx(70)
    assert raw == original
    assert result.upstream_raw["normal"]["packaged_size_cm"] == [10, 8, 4]


def test_critical_compatibility_defaults_block_production_adoption():
    raw = upstream_result()
    raw["ai_meta"]["default_fields_used"] = ["ai_package_size_cm"]
    with pytest.raises(CriticalDefaultError, match="必须由用户补充"):
        adapt_upstream_result(
            raw,
            forwarder=Forwarder("sz", "深圳", 80, 10, 8000),
            tail_fee_rmb=40,
        )


def test_manual_package_can_replace_critical_compatibility_defaults():
    raw = upstream_result()
    raw["ai_meta"]["default_fields_used"] = [
        "ai_package_size_cm",
        "ai_package_weight_kg",
    ]
    result = adapt_upstream_result(
        raw,
        forwarder=Forwarder("yw", "义乌", 100, 6, 8000),
        tail_fee_rmb=40,
        manual_package=PackageSpec(10, 10, 10, 200),
    )
    assert result.user_override_used is True
    assert result.needs_review is True
    assert "上游使用了兼容默认值，已由用户包装值覆盖" in result.review_reasons


def test_source_commit_mismatch_is_rejected():
    raw = upstream_result()
    raw["source_commit"] = "15ce7ddd2fc3a9879bd919eb972319905e75604b"
    with pytest.raises(UpstreamCompatibilityError, match="来源 Commit 不匹配"):
        adapt_upstream_result(
            raw,
            forwarder=Forwarder("sz", "深圳", 80, 10, 8000),
            tail_fee_rmb=40,
        )


def test_external_ai_conflict_audit_is_preserved_without_reinterpretation():
    raw = upstream_result()
    result = adapt_upstream_result(
        raw,
        forwarder=Forwarder("sz", "深圳", 80, 10, 8000),
        tail_fee_rmb=40,
    )
    audit = result.calibration_audit
    assert result.proposal_source == "external_ai"
    assert audit["original_scenarios"]["normal"]["packaged_size_cm"] == [10, 8, 4]
    assert audit["local_proposed_scenarios"]["normal"]["packaged_size_cm"] == [9, 8, 3]
    assert audit["adjusted_scenarios"]["normal"]["packaged_size_cm"] == [10, 8, 4]
    assert audit["proposed_rule_ids"] == ["moderate_compression"]


def test_missing_packaging_mode_is_rejected():
    raw = upstream_result()
    raw.pop("conservative")
    with pytest.raises(UpstreamCompatibilityError, match="缺少 conservative"):
        adapt_upstream_result(
            raw,
            forwarder=Forwarder("sz", "深圳", 80, 10, 8000),
            tail_fee_rmb=40,
        )
