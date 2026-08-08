"""Experiment strategy tests: interface, behavior deltas, production isolation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService  # noqa: E402
from profit_accounting_26.domain.models import AIObservation, PackagingScenario, PackagingState  # noqa: E402
from tests.evaluation.vision_packaging.harness.experiments import EXPERIMENTS, get_strategy  # noqa: E402
from tests.evaluation.vision_packaging.harness.replay import build_baseline_service  # noqa: E402


@pytest.fixture(scope="module")
def baseline_service():
    return build_baseline_service()


def test_registry_contains_baseline_and_three_hypotheses():
    assert set(EXPERIMENTS) == {
        "baseline",
        "expA_relaxed_outline_check",
        "expB_independent_packaging_candidate",
        "expC_cal_risk_only_for_complete_ai",
    }
    assert EXPERIMENTS["baseline"].is_production_baseline is True
    assert all(not strategy.is_production_baseline for key, strategy in EXPERIMENTS.items() if key != "baseline")
    assert all(strategy.data_requirements for key, strategy in EXPERIMENTS.items() if key != "baseline")


def test_unknown_experiment_rejected():
    with pytest.raises(ValueError):
        get_strategy("does_not_exist")


def test_baseline_returns_same_service_instance(baseline_service):
    assert EXPERIMENTS["baseline"].build_service(baseline_service) is baseline_service


def test_experiments_keep_calibration_state(baseline_service):
    for experiment_id in ("expA_relaxed_outline_check", "expB_independent_packaging_candidate",
                          "expC_cal_risk_only_for_complete_ai"):
        service = get_strategy(experiment_id).build_service(baseline_service)
        assert isinstance(service, PackagingEstimationService)
        assert service.samples is baseline_service.samples
        assert service.registry is baseline_service.registry


def _outline_observation() -> AIObservation:
    return AIObservation(
        product_name="软垫", overall_form="soft_flat", rigidity="soft",
        foldability="good", packing_actions=["flat_fold"],
        length_cm=30, width_cm=20, height_cm=4, weight_g=200,
        dimension_scope="product_size", weight_scope="net_weight",
    )


def _scenario(length, width, height, weight, method="平折袋装") -> PackagingScenario:
    return PackagingScenario(label="正常档", packaging_state=PackagingState.FULL_FLAT_FOLD,
                             packaging_method=method, length_cm=length, width_cm=width,
                             height_cm=height, weight_g=weight)


def test_expA_removes_only_outline_rejection_reason(baseline_service):
    observation = _outline_observation()
    normal = _scenario(32, 20, 4, 240)
    conservative = _scenario(34, 22, 5, 260)
    baseline_reasons = baseline_service._validate_candidate(normal, conservative, observation)
    assert "packing_action_not_reflected_in_outline" in baseline_reasons
    experiment = get_strategy("expA_relaxed_outline_check").build_service(baseline_service)
    assert "packing_action_not_reflected_in_outline" not in experiment._validate_candidate(
        normal, conservative, observation)
    # 其余校验理由不被实验误删
    incomplete = _scenario(None, 20, 4, 240)
    assert "missing_or_nonpositive_dimensions_or_weight" in experiment._validate_candidate(
        incomplete, conservative, observation)


def test_expB_stops_dimension_semantic_guilt_by_association(baseline_service):
    observation = _outline_observation()
    observation.raw_payload = {"dimension_semantic_issue": "dimension_evidence_not_outer_dimensions"}
    normal = _scenario(18, 12, 4, 240)
    conservative = _scenario(20, 14, 5, 260)
    baseline_reasons = baseline_service._validate_ai_semantics(normal, conservative, observation)
    assert "dimension_evidence_not_outer_dimensions" in baseline_reasons
    experiment = get_strategy("expB_independent_packaging_candidate").build_service(baseline_service)
    assert "dimension_evidence_not_outer_dimensions" not in experiment._validate_ai_semantics(
        normal, conservative, observation)


def test_expC_forces_risk_only_when_ai_candidate_complete(baseline_service):
    observation = AIObservation(product_name="袜子", product_type="袜", confidence="low")
    ai_normal = _scenario(12, 9, 2, 80)
    ai_conservative = _scenario(13, 10, 3, 90)
    cal_normal = _scenario(15, 12, 4, 500)
    cal_conservative = _scenario(16, 13, 5, 540)
    # baseline：strong 匹配且 AI 非 high 置信 -> CAL 改写数值
    _, _, baseline_trace = baseline_service._coordinate_ai_cal_fields(
        ai_normal, ai_conservative, cal_normal, cal_conservative,
        match_strength="strong", observation=observation)
    assert baseline_trace["adjusted_fields"]
    # expC：AI 候选完整 -> risk-only，数值不变
    experiment = get_strategy("expC_cal_risk_only_for_complete_ai").build_service(baseline_service)
    out_normal, out_conservative, exp_trace = experiment._coordinate_ai_cal_fields(
        ai_normal, ai_conservative, cal_normal, cal_conservative,
        match_strength="strong", observation=observation)
    assert exp_trace["risk_only"] is True
    assert exp_trace["adjusted_fields"] == {}
    assert out_normal is ai_normal and out_conservative is ai_conservative


def test_production_source_never_references_evaluation_code():
    forbidden = ("tests.evaluation", "vision_packaging.harness", "evaluate_vision_packaging")
    offenders: list[str] = []
    for path in (ROOT / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(f"{path.relative_to(ROOT)}: {token}")
    assert offenders == []
