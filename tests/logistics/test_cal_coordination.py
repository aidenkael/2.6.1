from __future__ import annotations

import hashlib
import json
from pathlib import Path

from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService
from profit_accounting_26.domain.models import AIObservation, PackagingProposal, PackagingScenario, PackagingState


ROOT = Path(__file__).resolve().parents[2]
CALIBRATION = ROOT / "calibration/logistics_v2/calibration_all_cleaned_v3.json"
REGISTRY = ROOT / "calibration/logistics_v2/packaging_rule_registry_v1.json"


def service() -> PackagingEstimationService:
    return PackagingEstimationService(CALIBRATION, rule_registry_path=REGISTRY)


def proposal(*, dims=(30, 20, 8), weight=120, confidence="low") -> PackagingProposal:
    normal = PackagingScenario("normal", PackagingState.MODERATE_COMPRESSION, "AI estimate", *dims, weight, confidence=confidence)
    conservative = PackagingScenario("conservative", PackagingState.MODERATE_COMPRESSION, "AI estimate", 32, 22, 10, weight + 20, confidence=confidence)
    return PackagingProposal(normal, conservative, proposal_source="vision_api")


def calibrated_observation(**overrides) -> AIObservation:
    values = dict(product_type="angel_wing_brooch_pair", material="alloy_metal", rigidity="hard",
                  requires_shape_retention=False, weight_g=5, weight_scope="net_weight")
    values.update(overrides)
    return AIObservation(**values)


def test_frozen_cal_assets_keep_expected_hashes_and_counts():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    # CAL asset hashes are computed from the Git-canonical LF file bytes.
    assert hashlib.sha256(CALIBRATION.read_bytes()).hexdigest() == "ae10226731d006a4ad540e6c6d9fc5224067823140cfbc34e408984529d6ad0d"
    assert hashlib.sha256(REGISTRY.read_bytes()).hexdigest() == "a304a05989ffe9cbb4847fa541f20cec195c78aee5a7b9b91eb9b52d041d5e5b"
    assert len(json.loads(CALIBRATION.read_text(encoding="utf-8"))) == 77
    assert len(registry["aggregate_rules"]) == 9
    assert len(registry["sample_rules"]) == 77
    assert all(item.get("enabled", True) for item in registry["aggregate_rules"] + registry["sample_rules"])


def test_every_legacy_sample_rule_is_reachable_through_compatibility_adapter():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    runtime = service()
    unmatched = []
    for rule in registry["sample_rules"]:
        observation = AIObservation(product_type=rule["product_type"], material=rule.get("material") or "",
                                    rigidity=rule.get("rigidity") or "unknown",
                                    requires_shape_retention=rule.get("requires_shape_retention"))
        result = runtime.estimate(observation)
        matches = result.candidate_records["cal_match_audit"]["sample_matches"]
        if not any(item["rule_id"] == rule["rule_id"] for item in matches):
            unmatched.append(rule["rule_id"])
    assert unmatched == []


def test_strong_cal_corrects_low_confidence_ai_estimate_at_field_level():
    result = service().estimate(calibrated_observation(), external_proposal=proposal())
    assert result.proposal_source == "ai_cal_coordinated"
    assert result.normal.length_cm == 9
    assert result.normal.weight_g >= 25
    trace = result.candidate_records["cal_coordination"]
    assert trace["match_strength"] == "strong"
    assert "normal.length_cm" in trace["adjusted_fields"]


def test_confirmed_net_weight_is_not_replaced_by_lower_calibration_weight():
    ai = proposal(weight=150)
    result = service().estimate(calibrated_observation(weight_g=110), external_proposal=ai)
    assert result.normal.weight_g >= 110


def test_high_confidence_ai_beats_weak_cal_reference():
    ai_normal = PackagingScenario("normal", PackagingState.MODERATE_COMPRESSION, "AI evidence", 20, 10, 3, 100, confidence="high")
    ai_conservative = PackagingScenario("conservative", PackagingState.MODERATE_COMPRESSION, "AI evidence", 22, 12, 4, 120, confidence="high")
    cal_normal = PackagingScenario("normal", PackagingState.MODERATE_COMPRESSION, "CAL", 9, 4, 2, 40)
    cal_conservative = PackagingScenario("conservative", PackagingState.MODERATE_COMPRESSION, "CAL", 10, 5, 3, 50)
    normal, conservative, trace = service()._coordinate_ai_cal_fields(
        ai_normal, ai_conservative, cal_normal, cal_conservative,
        match_strength="weak", observation=AIObservation(confidence="high"),
    )
    assert (normal.length_cm, conservative.weight_g) == (20, 120)
    assert trace["risk_only"] is True


def test_cal_candidate_runs_before_generic_fallback_when_legacy_reference_is_available():
    result = service().estimate(calibrated_observation())
    assert result.proposal_source == "cal_candidate_completed"
    assert "CAL-003" in result.applied_profile_ids


def test_no_cal_match_preserves_complete_ai_candidate():
    observation = AIObservation(product_type="unmatched_type", material="unmatched", rigidity="soft")
    result = service().estimate(observation, external_proposal=proposal())
    assert result.proposal_source == "ai_candidate"
    assert result.candidate_records["cal_match_audit"]["sample_matches"] == []


def test_cal_structure_risk_challenges_unsupported_shape_without_overriding_confirmed_weight():
    observation = AIObservation(
        product_type="handbag", product_family="bag", material_family="leather",
        overall_form="hard_3d", rigidity="hard", foldability="none", compressibility="none",
        requires_shape_retention=True, has_frame=True, length_cm=28.5, width_cm=12, height_cm=21,
        weight_g=700, weight_scope="net_weight", dimension_scope="product_size",
    )
    ai = PackagingProposal(
        PackagingScenario("normal", PackagingState.SHAPE_RETAINED, "AI estimate", 30.5, 14, 23, 750),
        PackagingScenario("conservative", PackagingState.SHAPE_RETAINED, "AI estimate", 32.5, 16, 25, 800),
        proposal_source="vision_api",
    )
    result = service().estimate(observation, external_proposal=ai)
    assert "cal_structure_conflict_requires_evidence" in result.rejected_candidates["ai_candidate"]
    assert "CAL-065" in result.candidate_records["cal_structure_risk"]["matched_rule_ids"]
    assert result.normal.weight_g >= 700
