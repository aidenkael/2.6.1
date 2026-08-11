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
    # calibration_all_cleaned_v3.json stays byte-identical after the conservative migration.
    assert hashlib.sha256(CALIBRATION.read_bytes()).hexdigest() == "ae10226731d006a4ad540e6c6d9fc5224067823140cfbc34e408984529d6ad0d"
    # Registry hash tracks packaging-rules-v2-cal77-conservative.
    assert hashlib.sha256(REGISTRY.read_bytes()).hexdigest() == "ab291a936949020b0458e609f48bd3996139e444966b47ebe32e016be5b87874"
    assert len(json.loads(CALIBRATION.read_text(encoding="utf-8"))) == 77
    assert len(registry["aggregate_rules"]) == 9
    assert len(registry["sample_rules"]) == 77
    # Conservative contract: all legacy samples archived, only thin textile stays numeric.
    assert all(item["enabled"] is False for item in registry["sample_rules"])
    enabled_aggregates = [item["rule_id"] for item in registry["aggregate_rules"] if item["enabled"]]
    assert enabled_aggregates == ["AGR-THIN-TEXTILE-001"]


def test_no_legacy_sample_rule_is_reachable_through_compatibility_adapter():
    # After the conservative migration every sample rule is disabled,
    # so none of them may enter runtime sample matching.
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    runtime = service()
    for rule in registry["sample_rules"]:
        observation = AIObservation(product_type=rule["product_type"], material=rule.get("material") or "",
                                    rigidity=rule.get("rigidity") or "unknown",
                                    requires_shape_retention=rule.get("requires_shape_retention"))
        result = runtime.estimate(observation)
        matches = result.candidate_records["cal_match_audit"]["sample_matches"]
        assert matches == [], rule["rule_id"]


def thin_textile_observation(**overrides) -> AIObservation:
    values = dict(product_name="薄款袜", product_type="socks", material="thin_knit",
                  rigidity="soft", foldability="good", compressibility="good",
                  length_cm=30, width_cm=20, height_cm=8, weight_g=120,
                  weight_scope="packaged_weight", requires_shape_retention=False)
    values.update(overrides)
    return AIObservation(**values)


def test_strong_cal_corrects_low_confidence_ai_estimate_at_field_level():
    # After the conservative migration the only surviving legacy numeric rule
    # is AGR-THIN-TEXTILE-001; it still arbitrates at field level.
    result = service().estimate(thin_textile_observation(), external_proposal=proposal())
    assert result.proposal_source == "ai_cal_coordinated"
    assert result.normal.height_cm == 6.0  # smallest axis 8 × 0.75
    assert result.normal.length_cm == 30
    trace = result.candidate_records["cal_coordination"]
    assert trace["match_strength"] == "strong"
    assert "normal.height_cm" in trace["adjusted_fields"]
    assert "AGR-THIN-TEXTILE-001" in result.applied_profile_ids


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


def test_cal_candidate_runs_before_generic_fallback_when_legacy_aggregate_available():
    result = service().estimate(thin_textile_observation())
    assert result.proposal_source == "cal_candidate_completed"
    assert "AGR-THIN-TEXTILE-001" in result.applied_profile_ids


def test_no_cal_match_preserves_complete_ai_candidate():
    observation = AIObservation(product_type="unmatched_type", material="unmatched", rigidity="soft")
    result = service().estimate(observation, external_proposal=proposal())
    assert result.proposal_source == "ai_candidate"
    assert result.candidate_records["cal_match_audit"]["sample_matches"] == []


def test_cal_structure_risk_challenges_unsupported_shape_without_overriding_confirmed_weight():
    # The surviving thin-textile rule still provides structure-risk lessons:
    # an unsupported shape-retention claim on socks requires rigid evidence.
    observation = AIObservation(
        product_name="薄袜", product_type="socks", material="thin_knit",
        rigidity="soft", foldability="good", compressibility="good",
        requires_shape_retention=True, length_cm=20, width_cm=10, height_cm=4,
        weight_g=30, weight_scope="net_weight",
    )
    ai = PackagingProposal(
        PackagingScenario("normal", PackagingState.SHAPE_RETAINED, "AI estimate", 22, 12, 6, 40),
        PackagingScenario("conservative", PackagingState.SHAPE_RETAINED, "AI estimate", 24, 14, 8, 50),
        proposal_source="vision_api",
    )
    result = service().estimate(observation, external_proposal=ai)
    assert "cal_structure_conflict_requires_evidence" in result.rejected_candidates["ai_candidate"]
    risk_ids = result.candidate_records["cal_structure_risk"]["matched_rule_ids"]
    assert "AGR-THIN-TEXTILE-001" in risk_ids
    assert result.normal.weight_g >= 30
