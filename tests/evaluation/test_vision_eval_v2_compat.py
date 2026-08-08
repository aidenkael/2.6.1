"""V2-compatibility close-out tests for the evaluation framework.

Covers: legacy marking of normal/conservative, estimated_package reservation,
optional structure/actual feedback fields, and business metrics that must
report "unavailable" instead of fabricated numbers.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.evaluation.vision_packaging.harness import case_io  # noqa: E402
from tests.evaluation.vision_packaging.harness.replay import (  # noqa: E402
    build_baseline_service,
    replay_case,
)
from tests.evaluation.vision_packaging.harness.scoring import (  # noqa: E402
    aggregate_metrics,
    score_business_metrics,
    score_case,
)


@pytest.fixture(scope="module")
def baseline_service():
    return build_baseline_service()


@pytest.fixture(scope="module")
def syn_01():
    cases = {case.case_id: case for case in case_io.discover_synthetic_cases()}
    return cases["syn_01_acrylic_coaster"]


# ---------------------------------------------------------------- validation


def _metadata_with(**extra_truth):
    truth = {
        "bare_dimensions": {"unknown": True},
        "bare_weight": {"unknown": True},
    }
    truth.update(extra_truth)
    return {"case_id": "case-v2", "images": [], "ground_truth": truth}


def test_v2_optional_fields_are_accepted():
    metadata = _metadata_with(
        estimated_package={
            "length_range": [12, 14], "width_range": [10, 12], "height_range": [2, 3],
            "weight_range": [90, 120], "acceptable_methods": ["气泡袋"],
        },
        structure_feedback={
            "rigidity": "hard", "shape_retention": "required", "foldability": "none",
            "compressibility": "none", "foldable_parts": [], "coilable_parts": [],
            "detachable_parts": ["handle"], "rigid_parts": [],
            "axis_behavior": {"height": "preserve"},
        },
        actual_feedback={
            "actual_first_mile_fee_rmb": 12.5, "actual_chargeable_weight_kg": 0.2,
            "actual_forwarder": "某货代", "actual_packaging_method": "气泡袋",
            "actual_package_dimensions": {"length_cm": 13, "width_cm": 11, "height_cm": 3},
            "actual_package_weight": 110,
        },
    )
    assert case_io.validate_case_metadata(metadata) == []


def test_v2_fields_all_may_stay_null():
    metadata = _metadata_with(estimated_package=None, structure_feedback=None, actual_feedback=None)
    assert case_io.validate_case_metadata(metadata) == []


def test_v2_field_validation_rejects_bad_values():
    metadata = _metadata_with(
        estimated_package={"length_range": [5, 1]},
        structure_feedback={"foldable_parts": "handle", "invented_key": 1},
        actual_feedback={"actual_chargeable_weight_kg": "heavy", "unknown_key": 2},
    )
    issues = case_io.validate_case_metadata(metadata)
    assert any("estimated_package.length_range" in item for item in issues)
    assert any("structure_feedback.foldable_parts" in item for item in issues)
    assert any("invented_key" in item for item in issues)
    assert any("actual_feedback.actual_chargeable_weight_kg" in item for item in issues)
    assert any("unknown_key" in item for item in issues)


# ---------------------------------------------------------------- replay legacy mark


def test_final_layer_marks_legacy_output_and_estimated_package(baseline_service, syn_01):
    replay = replay_case(syn_01, baseline_service)
    assert replay.ok
    final = replay.to_dict()["layers"]["FINAL"]
    legacy = final["legacy_current_engine_output"]
    assert legacy["normal"]["length_cm"] == 13.0
    assert legacy["conservative"]["packaging_method"] == "气泡袋+硬纸板"
    estimated = final["estimated_package"]
    assert estimated == {
        "length_cm": 13.0, "width_cm": 11.0, "height_cm": 2.5, "weight_g": 100.0,
        "packaging_method": "气泡袋+纸卡", "derived_from": "legacy_current_engine_output.normal",
    }
    # 向后兼容：旧的 normal/conservative 访问路径仍然可用
    assert final["normal"]["length_cm"] == 13.0


# ---------------------------------------------------------------- scoring


def test_estimated_package_ground_truth_is_graded(baseline_service, syn_01):
    truth = dict(syn_01.ground_truth)
    truth["estimated_package"] = {
        "length_range": [12, 14], "weight_range": [90, 120], "acceptable_methods": ["气泡袋"],
    }
    score = score_case(replay_case(syn_01, baseline_service), truth)
    assert score.estimated_package is not None
    assert score.estimated_package.correct is True
    # 未提供 estimated_package 时保持 None（不强制评分）
    assert score_case(replay_case(syn_01, baseline_service), syn_01.ground_truth).estimated_package is None


def test_business_metrics_unavailable_without_actual_feedback(baseline_service, syn_01):
    replay = replay_case(syn_01, baseline_service)
    metrics = score_business_metrics(replay, syn_01.ground_truth)
    assert metrics == {
        "chargeable_weight_error": "unavailable",
        "shipping_cost_error": "unavailable",
        "underestimate": "unavailable",
        "severe_underestimate": "unavailable",
    }


def test_business_metrics_computed_from_real_facts_only(baseline_service, syn_01):
    replay = replay_case(syn_01, baseline_service)  # final normal weight = 100 g = 0.1 kg
    truth = dict(syn_01.ground_truth)
    truth["actual_feedback"] = {"actual_chargeable_weight_kg": 0.2, "actual_first_mile_fee_rmb": 15.0}
    metrics = score_business_metrics(replay, truth)
    assert metrics["chargeable_weight_error"] == pytest.approx(-0.1)
    assert metrics["underestimate"] is True
    assert metrics["severe_underestimate"] is True  # 0.1 < 0.2 * 0.9
    # 重放不运行物流引擎：费用误差不得编造
    assert metrics["shipping_cost_error"] == "unavailable_no_logistics_replay"

    truth["actual_feedback"] = {"actual_chargeable_weight_kg": 0.105}
    metrics = score_business_metrics(replay, truth)
    assert metrics["underestimate"] is True
    assert metrics["severe_underestimate"] is False  # 0.1 >= 0.105 * 0.9


def test_aggregate_business_summary_counts_availability(baseline_service, syn_01):
    truth = dict(syn_01.ground_truth)
    truth["actual_feedback"] = {"actual_chargeable_weight_kg": 0.2}
    scores = [
        score_case(replay_case(syn_01, baseline_service), syn_01.ground_truth),
        score_case(replay_case(syn_01, baseline_service), truth),
    ]
    summary = aggregate_metrics(scores, label="real")["business_metrics"]
    assert summary["available_cases"] == 1
    assert summary["unavailable_cases"] == 1
    assert summary["mean_chargeable_weight_error_kg"] == pytest.approx(-0.1)
    assert summary["underestimate_cases"] == [syn_01.case_id]
    assert summary["severe_underestimate_cases"] == [syn_01.case_id]


def test_synthetic_cases_still_load_with_v2_schema():
    cases = case_io.discover_synthetic_cases()
    assert len(cases) == 3
    assert all(case.origin == "synthetic" for case in cases)
    assert all(case_io.validate_case_metadata(case.metadata) == [] for case in cases)
