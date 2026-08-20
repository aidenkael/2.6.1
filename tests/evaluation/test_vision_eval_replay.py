"""Offline replay tests: production chain, four layers, no network."""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.evaluation.vision_packaging.harness import case_io  # noqa: E402
from tests.evaluation.vision_packaging.harness.replay import (  # noqa: E402
    build_baseline_service,
    dimension_journey,
    replay_case,
)


@pytest.fixture(scope="module")
def baseline_service():
    return build_baseline_service()


@pytest.fixture(scope="module")
def synthetic_cases():
    return {case.case_id: case for case in case_io.discover_synthetic_cases()}


def _case(synthetic_cases, case_id):
    assert case_id in synthetic_cases, f"缺少 synthetic 案例 {case_id}"
    return synthetic_cases[case_id]


def test_replay_records_all_four_layers(baseline_service, synthetic_cases):
    replay = replay_case(_case(synthetic_cases, "syn_01_acrylic_coaster"), baseline_service)
    assert replay.ok
    layers = replay.to_dict()["layers"]
    assert set(layers) == {"AI_RAW", "PARSED", "NORMALIZED", "FINAL"}
    assert layers["AI_RAW"]["observation"]["length_cm"] == 12
    assert layers["PARSED"]["observation"]["length_cm"] == 12.0
    assert layers["NORMALIZED"]["observation"]["length_cm"] == 12.0
    assert layers["FINAL"]["normal"]["length_cm"] == 13.0


def test_replay_trace_records_required_fields(baseline_service, synthetic_cases):
    replay = replay_case(_case(synthetic_cases, "syn_01_acrylic_coaster"), baseline_service)
    trace = replay.trace
    for key in ("proposal_source", "final_candidate", "candidate_records", "rejected_candidates",
                "cal_adjustments", "salvage_adjustments", "structural_adjustments"):
        assert key in trace
    assert trace["cal_adjustments"]["adjusted_fields"] == {}


def test_syn01_complete_ai_candidate_is_adopted(baseline_service, synthetic_cases):
    replay = replay_case(_case(synthetic_cases, "syn_01_acrylic_coaster"), baseline_service)
    assert replay.ok
    assert replay.trace["proposal_source"] == "ai_candidate"
    assert "ai_candidate" not in replay.trace["rejected_candidates"]


def test_syn02_dimension_semantic_issue_keeps_ai_and_marks_review(baseline_service, synthetic_cases):
    replay = replay_case(_case(synthetic_cases, "syn_02_adjustable_leash"), baseline_service)
    assert replay.ok
    # 页面硬事实（维度证据非外廓）→ 本地不自行创造数值，保留 AI shipment + needs_review
    assert replay.trace["proposal_source"] == "ai_candidate_hard_facts"
    assert "dimension_evidence_not_outer_dimensions" in replay.trace["rejected_candidates"]["ai_candidate"]
    assert replay.final["normal"]["length_cm"] == 18.0
    assert replay.final["normal"]["needs_review"] is True
    # observation 层尺寸被 parser 清空（NORMALIZED 层事实）
    assert replay.normalized_observation["length_cm"] is None
    assert replay.normalized_observation.get("dimension_semantic_issue") is None  # 只存在于 raw_payload
    assert replay.normalized_observation["raw_payload"]["dimension_semantic_issue"] == (
        "dimension_evidence_not_outer_dimensions"
    )


def test_syn03_merchant_shipping_facts_win(baseline_service, synthetic_cases):
    replay = replay_case(_case(synthetic_cases, "syn_03_merchant_shipping_facts"), baseline_service)
    assert replay.ok
    assert replay.trace["proposal_source"] == "merchant_candidate"
    normal = replay.final["normal"]
    assert (normal["length_cm"], normal["width_cm"], normal["height_cm"], normal["weight_g"]) == (20.0, 15.0, 8.0, 350.0)


def test_replay_never_opens_socket(baseline_service, synthetic_cases, monkeypatch):
    def _refuse(*_args, **_kwargs):
        raise RuntimeError("评测重放不允许任何网络访问")

    monkeypatch.setattr(socket, "socket", _refuse)
    for case in synthetic_cases.values():
        replay = replay_case(case, baseline_service)
        assert replay.ok, replay.error


def test_dimension_journey_tracks_every_layer(baseline_service, synthetic_cases):
    replay = replay_case(_case(synthetic_cases, "syn_02_adjustable_leash"), baseline_service)
    journey = dimension_journey(replay)
    for field_name in ("length_cm", "width_cm", "height_cm", "weight_g"):
        assert set(journey[field_name]) == {"AI_RAW", "PARSED", "NORMALIZED", "FINAL"}
    # 尺寸在 NORMALIZED 层被语义门清空；FINAL 层保留 AI shipment（本地不创造数值）
    assert journey["length_cm"]["AI_RAW"] is None
    assert journey["length_cm"]["NORMALIZED"] is None
    assert journey["length_cm"]["FINAL"] == 18.0


def test_broken_raw_response_is_reported_not_raised(baseline_service, synthetic_cases):
    broken = case_io.EvalCase(
        case_id="broken", path=Path("broken"),
        metadata={"case_id": "broken"},
        raw_response={"choices": [{"message": {"content": "不是JSON{"}}]},
    )
    replay = replay_case(broken, baseline_service)
    assert not replay.ok
    assert replay.error
