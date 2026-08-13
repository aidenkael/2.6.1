from __future__ import annotations

import json

from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService
from profit_accounting_26.domain.models import (
    AIObservation,
    PackagingProposal,
    PackagingScenario,
    PackagingState,
)


def _service(tmp_path) -> PackagingEstimationService:
    calibration = tmp_path / "calibration.json"
    calibration.write_text(
        json.dumps([{"baseline_id": "synthetic-test"}]),
        encoding="utf-8",
    )
    registry = tmp_path / "packaging_rule_registry_v1.json"
    registry.write_text(
        json.dumps(
            {
                "version": "synthetic-formal-v1",
                "aggregate_rules": [
                    {
                        "rule_id": "FORMAL-TEST-001",
                        "enabled": True,
                        "priority": 100,
                        "name": "synthetic validated rule",
                        "match": {
                            "any_terms": ["synthetic_soft_item"],
                            "rigidity": ["soft"],
                            "foldability": ["good"],
                            "compressibility": ["good"],
                        },
                        "action": {
                            "type": "smallest_axis_add",
                            "normal_cm": 1.0,
                            "conservative_cm": 2.0,
                        },
                        "confidence": "medium",
                    }
                ],
                "sample_rules": [],
            }
        ),
        encoding="utf-8",
    )
    return PackagingEstimationService(
        calibration,
        calibration_version="synthetic-formal-v1",
        rule_registry_path=registry,
    )


def _proposal(confidence="low") -> PackagingProposal:
    return PackagingProposal(
        PackagingScenario(
            "normal",
            PackagingState.MODERATE_COMPRESSION,
            "AI estimate",
            30,
            20,
            8,
            120,
            confidence=confidence,
        ),
        PackagingScenario(
            "conservative",
            PackagingState.MODERATE_COMPRESSION,
            "AI estimate",
            32,
            22,
            10,
            140,
            confidence=confidence,
        ),
        proposal_source="vision_api",
    )


def _observation() -> AIObservation:
    return AIObservation(
        product_name="synthetic_soft_item",
        product_type="synthetic_soft_item",
        material="textile",
        rigidity="soft",
        foldability="good",
        compressibility="good",
        weight_g=100,
        weight_scope="net_weight",
        requires_shape_retention=False,
    )


def test_validated_formal_rule_can_coordinate_low_confidence_ai(tmp_path):
    result = _service(tmp_path).estimate(_observation(), external_proposal=_proposal())

    assert result.proposal_source == "ai_cal_coordinated"
    assert result.normal.height_cm == 9.0
    assert "FORMAL-TEST-001" in result.applied_profile_ids
    trace = result.candidate_records["cal_coordination"]
    assert trace["match_strength"] == "strong"
    assert "normal.height_cm" in trace["adjusted_fields"]


def test_high_confidence_ai_remains_authoritative_against_weak_reference():
    service = PackagingEstimationService(calibration_version="synthetic")
    ai_normal = PackagingScenario(
        "normal", PackagingState.MODERATE_COMPRESSION, "AI evidence", 20, 10, 3, 100, confidence="high"
    )
    ai_conservative = PackagingScenario(
        "conservative", PackagingState.MODERATE_COMPRESSION, "AI evidence", 22, 12, 4, 120, confidence="high"
    )
    cal_normal = PackagingScenario(
        "normal", PackagingState.MODERATE_COMPRESSION, "CAL", 9, 4, 2, 40
    )
    cal_conservative = PackagingScenario(
        "conservative", PackagingState.MODERATE_COMPRESSION, "CAL", 10, 5, 3, 50
    )

    normal, conservative, trace = service._coordinate_ai_cal_fields(
        ai_normal,
        ai_conservative,
        cal_normal,
        cal_conservative,
        match_strength="weak",
        observation=AIObservation(confidence="high"),
    )

    assert (normal.length_cm, conservative.weight_g) == (20, 120)
    assert trace["risk_only"] is True


def test_no_rule_match_preserves_complete_ai_candidate(tmp_path):
    result = _service(tmp_path).estimate(
        AIObservation(product_type="other_item", rigidity="soft"),
        external_proposal=_proposal(),
    )

    assert result.proposal_source == "ai_candidate"
    assert result.applied_profile_ids == []
