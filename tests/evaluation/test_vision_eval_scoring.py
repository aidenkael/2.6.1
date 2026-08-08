"""Scoring metric tests: ranges, method sets, per-layer aggregation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.evaluation.vision_packaging.harness import case_io  # noqa: E402
from tests.evaluation.vision_packaging.harness.replay import build_baseline_service, replay_case  # noqa: E402
from tests.evaluation.vision_packaging.harness.scoring import (  # noqa: E402
    CaseScore,
    CandidateVerdict,
    aggregate_metrics,
    coerce_number,
    grade_method,
    score_case,
    score_packaging_candidate,
)


def _scenario(length=20.0, width=15.0, height=4.0, weight=150.0, method="袋装"):
    return {"length_cm": length, "width_cm": width, "height_cm": height,
            "weight_g": weight, "packaging_method": method}


def test_dimensions_graded_by_range_not_equality():
    truth = {"length_range": [18, 22], "width_range": [10, 16], "height_range": [3, 5],
             "weight_range": [130, 180]}
    verdict = score_packaging_candidate(_scenario(), truth)
    assert verdict.correct is True
    outside = score_packaging_candidate(_scenario(height=2.0), truth)
    assert outside.dimensions is False
    assert outside.correct is False


def test_missing_value_counts_wrong_when_graded():
    truth = {"length_range": [18, 22]}
    verdict = score_packaging_candidate({"length_cm": None}, truth)
    assert verdict.dimensions is False


def test_partial_ground_truth_only_grads_filled_axes():
    truth = {"length_range": [18, 22]}
    verdict = score_packaging_candidate(_scenario(), truth)
    assert verdict.dimensions is True
    assert verdict.weight is None
    assert verdict.method is None
    assert verdict.correct is True


def test_unknown_truth_not_graded():
    assert score_packaging_candidate(_scenario(), {"unknown": True}).correct is None
    assert score_packaging_candidate(_scenario(), None).correct is None
    assert score_packaging_candidate(_scenario(), {}).correct is None


def test_method_matching_is_set_based():
    assert grade_method("气泡袋+纸卡", ["气泡袋"]) is True
    assert grade_method("盘绕后袋装", ["袋装"]) is True
    assert grade_method("运输纸箱", ["袋装"]) is False
    assert grade_method("", ["*"]) is False
    assert grade_method("任何方式", ["*"]) is True
    assert grade_method("袋装", None) is None


def test_coerce_number_handles_units_and_garbage():
    assert coerce_number("22cm") == 22.0
    assert coerce_number(15) == 15.0
    assert coerce_number("约3.5") == 3.5
    assert coerce_number("很大") is None
    assert coerce_number(True) is None


@pytest.fixture(scope="module")
def baseline_service():
    return build_baseline_service()


def _synthetic(case_id):
    for case in case_io.discover_synthetic_cases():
        if case.case_id == case_id:
            return case
    raise AssertionError(f"缺少 {case_id}")


def test_local_effect_classification(baseline_service):
    # syn_01: AI 与 FINAL 均正确 -> unchanged
    case = _synthetic("syn_01_acrylic_coaster")
    score = score_case(replay_case(case, baseline_service), case.ground_truth)
    assert score.local_effect == "unchanged"
    # syn_02: AI 正确但 salvage 后 FINAL 错误 -> degraded（post_ai_degradation 案例）
    case = _synthetic("syn_02_adjustable_leash")
    score = score_case(replay_case(case, baseline_service), case.ground_truth)
    assert score.ai.correct is True
    assert score.final.correct is False
    assert score.local_effect == "degraded"


def test_replay_failure_scores_not_graded():
    broken = case_io.EvalCase(case_id="broken", path=Path("broken"),
                              metadata={"case_id": "broken"}, raw_response={})
    score = score_case(replay_case(broken, build_baseline_service()), {})
    assert score.replay_ok is False
    assert score.local_effect == "not_graded"


def _fixed_score(case_id, ai_correct, final_correct):
    verdict = lambda value: CandidateVerdict(dimensions=value, weight=None, method=None)  # noqa: E731
    if ai_correct and not final_correct:
        effect = "degraded"
    elif final_correct and not ai_correct:
        effect = "improved"
    else:
        effect = "unchanged"
    return CaseScore(case_id, "real", True, verdict(ai_correct), verdict(ai_correct),
                     verdict(final_correct), effect)


def test_post_ai_degradation_rate_computation():
    scores = [
        _fixed_score("c1", True, True),
        _fixed_score("c2", True, False),
        _fixed_score("c3", False, True),
        _fixed_score("c4", False, False),
    ]
    metrics = aggregate_metrics(scores, label="unit")
    assert metrics["ai_candidate_accuracy"] == {"correct": 2, "graded": 4, "rate": 0.5}
    assert metrics["final_accuracy"] == {"correct": 2, "graded": 4, "rate": 0.5}
    degradation = metrics["post_ai_degradation"]
    assert degradation["count"] == 1
    assert degradation["ai_correct_count"] == 2
    assert degradation["post_ai_degradation_rate"] == 0.5
    assert degradation["cases"] == ["c2"]
    local = metrics["local_processing"]
    assert local["improved"] == 1 and local["degraded"] == 1 and local["unchanged"] == 2


def test_empty_suite_reports_none_rates():
    metrics = aggregate_metrics([], label="empty")
    assert metrics["cases_total"] == 0
    assert metrics["final_accuracy"]["rate"] is None
    assert metrics["post_ai_degradation"]["post_ai_degradation_rate"] is None
