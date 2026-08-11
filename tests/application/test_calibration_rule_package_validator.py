from __future__ import annotations

import copy
import json
from pathlib import Path

from profit_accounting_26.application.calibration_rule_package_validator import (
    AgentCalibrationRulePackageValidator,
)
from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService


REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = REPO_ROOT / "docs" / "contracts" / "agent_calibration_rule_package_v1.example.json"


def _candidate() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def _codes(result) -> set[str]:
    return set(result.codes)


class TestCandidateValidation:
    def test_frozen_example_is_valid(self):
        result = AgentCalibrationRulePackageValidator().validate(_candidate())
        assert result.is_valid, result.issues

    def test_validate_file_reads_example(self):
        result = AgentCalibrationRulePackageValidator().validate_file(EXAMPLE)
        assert result.is_valid, result.issues

    def test_wrong_schema_and_engine_are_rejected(self):
        payload = _candidate()
        payload["schema_version"] = "future-v9"
        payload["base_engine_version"] = "wrong-engine"
        result = AgentCalibrationRulePackageValidator().validate(payload)
        assert {"schema_version", "engine_version_mismatch"} <= _codes(result)

    def test_unknown_top_level_field_is_rejected(self):
        payload = _candidate()
        payload["unexpected"] = True
        assert "unknown_field" in _codes(AgentCalibrationRulePackageValidator().validate(payload))

    def test_candidate_cannot_claim_validation(self):
        payload = _candidate()
        payload["validation"] = {"fake": True}
        assert "candidate_has_validation" in _codes(AgentCalibrationRulePackageValidator().validate(payload))

    def test_require_validated_rejects_candidate(self):
        result = AgentCalibrationRulePackageValidator().validate(_candidate(), require_validated=True)
        assert "validated_required" in _codes(result)

    def test_empty_match_and_unknown_match_field_are_rejected(self):
        payload = _candidate()
        payload["rules"][0]["match"] = {}
        result = AgentCalibrationRulePackageValidator().validate(payload)
        assert "empty_match" in _codes(result)

        payload = _candidate()
        payload["rules"][0]["match"]["invented_condition"] = ["x"]
        result = AgentCalibrationRulePackageValidator().validate(payload)
        assert "unknown_field" in _codes(result)

    def test_duplicate_rule_id_is_rejected(self):
        payload = _candidate()
        second = copy.deepcopy(payload["rules"][0])
        second["match"]["any_terms"] = ["bag"]
        payload["rules"].append(second)
        assert "duplicate_rule_id" in _codes(AgentCalibrationRulePackageValidator().validate(payload))

    def test_evidence_sample_count_cannot_undercount_ids(self):
        payload = _candidate()
        payload["rules"][0]["evidence"]["sample_count"] = 1
        result = AgentCalibrationRulePackageValidator().validate(payload)
        assert "sample_count_mismatch" in _codes(result)


class TestActionValidation:
    def test_smallest_axis_add_conservative_must_not_be_lower(self):
        payload = _candidate()
        payload["rules"][0]["action"] = {
            "type": "smallest_axis_add", "normal_cm": 3.0, "conservative_cm": 2.0,
        }
        result = AgentCalibrationRulePackageValidator().validate(payload)
        assert "conservative_below_normal" in _codes(result)

    def test_scale_and_volume_require_positive_finite_numbers(self):
        for action in (
            {"type": "smallest_axis_scale", "normal": 1.0, "conservative": 0.0},
            {"type": "volume_ratio", "normal": 0.8, "conservative": float("nan")},
        ):
            payload = _candidate()
            payload["rules"][0]["action"] = action
            result = AgentCalibrationRulePackageValidator().validate(payload)
            assert not result.is_valid
            assert _codes(result) & {"number_positive", "number_finite"}

    def test_reference_template_checks_bounds_and_conservative_dimensions(self):
        payload = _candidate()
        payload["rules"][0]["action"] = {
            "type": "reference_scaled_template",
            "reference_product_size_cm": [20, 10, 5],
            "normal_package_size_cm": [22, 12, 7],
            "conservative_package_size_cm": [21, 13, 8],
            "scale_min": 2.0,
            "scale_max": 1.0,
        }
        result = AgentCalibrationRulePackageValidator().validate(payload)
        assert {"scale_bounds", "conservative_below_normal"} <= _codes(result)

    def test_unknown_action_type_and_field_are_rejected(self):
        payload = _candidate()
        payload["rules"][0]["action"] = {"type": "change_height", "value_cm": 2}
        assert "action_type" in _codes(AgentCalibrationRulePackageValidator().validate(payload))

        payload = _candidate()
        payload["rules"][0]["action"]["axis"] = "height"
        assert "unknown_field" in _codes(AgentCalibrationRulePackageValidator().validate(payload))


class TestConflicts:
    def test_same_priority_overlapping_rules_are_rejected(self):
        payload = _candidate()
        second = copy.deepcopy(payload["rules"][0])
        second["rule_id"] = "AGR-SOFT-TEXTILE-002"
        second["match"]["any_terms"] = ["scarf"]
        payload["rules"].append(second)
        result = AgentCalibrationRulePackageValidator().validate(payload)
        assert "same_priority_overlap" in _codes(result)

    def test_same_priority_disjoint_terms_are_not_flagged_as_overlap(self):
        payload = _candidate()
        second = copy.deepcopy(payload["rules"][0])
        second["rule_id"] = "AGR-HARD-BOX-001"
        second["match"] = {
            "any_terms": ["storage box"],
            "materials": ["plastic"],
            "rigidity": ["hard"],
        }
        payload["rules"].append(second)
        result = AgentCalibrationRulePackageValidator().validate(payload)
        assert "same_priority_overlap" not in _codes(result)


class TestValidatedPackage:
    def test_valid_software_side_validation_is_accepted(self):
        payload = _candidate()
        payload["status"] = "validated"
        payload["validation"] = {
            "validator": "offline-replay-v1",
            "replay_id": "replay-001",
            "engine_version": PackagingEstimationService.ENGINE_VERSION,
            "baseline_calibration_version": "local-calibration-v3-77-samples-rules-v1",
            "total_records": 10,
            "matched": 4,
            "improved": 3,
            "unchanged": 1,
            "degraded": 0,
            "conflicts": 0,
        }
        result = AgentCalibrationRulePackageValidator().validate(payload, require_validated=True)
        assert result.is_valid, result.issues

    def test_validated_requires_replay_metadata(self):
        payload = _candidate()
        payload["status"] = "validated"
        payload["validation"] = None
        assert "validated_missing_validation" in _codes(AgentCalibrationRulePackageValidator().validate(payload))

    def test_validation_counts_must_reconcile(self):
        payload = _candidate()
        payload["status"] = "validated"
        payload["validation"] = {
            "validator": "offline-replay-v1",
            "replay_id": "replay-001",
            "engine_version": PackagingEstimationService.ENGINE_VERSION,
            "total_records": 3,
            "matched": 4,
            "improved": 1,
            "unchanged": 1,
            "degraded": 0,
            "conflicts": 0,
        }
        result = AgentCalibrationRulePackageValidator().validate(payload)
        assert "validation_counts" in _codes(result)

    def test_validation_engine_must_match_runtime_engine(self):
        payload = _candidate()
        payload["status"] = "validated"
        payload["validation"] = {
            "validator": "offline-replay-v1",
            "replay_id": "replay-001",
            "engine_version": "wrong-engine",
            "total_records": 1,
            "matched": 1,
            "improved": 1,
            "unchanged": 0,
            "degraded": 0,
            "conflicts": 0,
        }
        result = AgentCalibrationRulePackageValidator().validate(payload)
        assert "validation_engine_version_mismatch" in _codes(result)


def test_malformed_json_returns_read_error(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    result = AgentCalibrationRulePackageValidator().validate_file(path)
    assert result.codes == ("json_read_error",)
