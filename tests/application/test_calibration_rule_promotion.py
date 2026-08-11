from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from profit_accounting_26.application.calibration_offline_replay import OfflineCalibrationReplay
from profit_accounting_26.application.calibration_rule_package_validator import (
    AgentCalibrationRulePackageValidator,
)
from profit_accounting_26.application.calibration_rule_promotion import (
    PROMOTION_VERSION,
    CalibrationRulePackagePromoter,
    PromotionPrecheckError,
)
from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService

BASELINE_VERSION = "test-calibration-v1"
BATCH_ID = "batch-promotion-001"


def _rule(
    rule_id: str = "AGR-PROMO-SCARF-001",
    *,
    match: dict | None = None,
    action: dict | None = None,
    priority: int = 95,
) -> dict:
    return {
        "rule_id": rule_id,
        "enabled": True,
        "priority": priority,
        "description": f"{rule_id} test rule",
        "match": match
        or {
            "any_terms": ["scarf"],
            "rigidity": ["soft"],
            "foldability": ["good"],
            "forbid_hard_structure": True,
        },
        "action": action
        or {
            "type": "smallest_axis_scale",
            "normal": 0.6,
            "conservative": 0.75,
            "min_cm": 1.0,
        },
        "evidence": {
            "source_record_ids": ["record-1"],
            "sample_count": 1,
            "rationale": "promotion test",
        },
    }


def _candidate(rules: list[dict] | None = None) -> dict:
    return {
        "schema_version": "agent-calibration-rule-package-v1",
        "package_id": "cal-promotion-test-001",
        "calibration_version": "agent-promotion-test-v1",
        "created_at": "2026-08-11T00:00:00Z",
        "generator": "offline-agent",
        "source_export_batch_ids": [BATCH_ID],
        "base_engine_version": PackagingEstimationService.ENGINE_VERSION,
        "base_calibration_version": BASELINE_VERSION,
        "status": "candidate",
        "rules": rules or [_rule()],
        "validation": None,
    }


def _observation(**overrides) -> dict:
    payload = {
        "product_name": "scarf 围巾",
        "product_type": "scarf",
        "material": "cotton",
        "rigidity": "soft",
        "foldability": "good",
        "compressibility": "good",
        "length_cm": 30,
        "width_cm": 30,
        "height_cm": 10,
        "weight_g": 300,
        "dimension_scope": "product_size",
        "weight_scope": "net_weight",
        "packaging_state_hint": "moderate_compression",
        "confidence": "low",
    }
    payload.update(overrides)
    return payload


def _scenario(dims: tuple[float, float, float], weight: float) -> dict:
    return {
        "packaging_state": "moderate_compression",
        "packaging_method": "袋装",
        "length_cm": dims[0],
        "width_cm": dims[1],
        "height_cm": dims[2],
        "weight_g": weight,
        "reasoning_summary": "ai",
        "confidence": "low",
        "needs_review": True,
        "default_fields_used": [],
    }


def _ai_initial(observation: dict | None = None) -> dict:
    return {
        "observation": observation or _observation(),
        "packaging_proposal": {
            "source_kind": "external_ai_packaging_proposal",
            "normal": _scenario((32, 30, 8), 320),
            "conservative": _scenario((33, 31, 9), 340),
            "engine_version": PackagingEstimationService.ENGINE_VERSION,
            "calibration_version": BASELINE_VERSION,
        },
    }


def _feedback(actual: dict | None) -> dict:
    return {
        "feedback_id": "feedback-1",
        "feedback_schema_version": "calibration-feedback-v1",
        "source": "user",
        "created_at": "2026-08-11T00:00:00Z",
        "updated_at": "2026-08-11T00:00:00Z",
        "structure": {},
        "suggested_package": None,
        "actual_logistics": actual,
        "user_note": None,
    }


def _actual(
    *,
    dimensions: dict | None = None,
    weight_g: float | None = None,
) -> dict:
    payload: dict = {}
    if dimensions is not None:
        payload["actual_package_dimensions"] = dimensions
    if weight_g is not None:
        payload["actual_package_weight_g"] = weight_g
    return payload


def _record(
    record_id: str,
    *,
    observation: dict | None = None,
    actual: dict | None = None,
) -> dict:
    return {
        "sequence": 1,
        "record_id": record_id,
        "product_short_name": "test",
        "product_link": "",
        "main_image": "",
        "images": [],
        "ai_initial_shipment": "",
        "user_calibration": "",
        "actual_first_mile": "",
        "machine_facts": {
            "ai_initial": _ai_initial(observation),
            "user_feedback": _feedback(actual),
        },
    }


def _default_actual() -> dict:
    return _actual(
        dimensions={"length_cm": 30, "width_cm": 29, "height_cm": 6},
        weight_g=300,
    )


def _write_inputs(
    tmp_path: Path,
    *,
    candidate: dict | None = None,
    records: list[dict] | None = None,
) -> dict[str, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(
        json.dumps(candidate or _candidate(), ensure_ascii=False), encoding="utf-8"
    )
    manifest_path = tmp_path / "manifest.json"
    manifest = {
        "contract_version": "Calibration Feedback Export V2",
        "export_batch_id": BATCH_ID,
        "exported_at": "2026-08-11T00:00:00Z",
        "records": records or [_record("record-1", actual=_default_actual())],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    calibration_path = tmp_path / "baseline_calibration.json"
    calibration_path.write_text(json.dumps([{"sample_id": "S1"}]), encoding="utf-8")
    registry_path = tmp_path / "baseline_registry.json"
    registry_path.write_text(
        json.dumps(
            {"version": "v1", "policy": {}, "aggregate_rules": [], "sample_rules": []}
        ),
        encoding="utf-8",
    )
    replay = OfflineCalibrationReplay().run(
        feedback_manifest=manifest_path,
        candidate_package=candidate_path,
        baseline_calibration=calibration_path,
        baseline_registry=registry_path,
        baseline_calibration_version=BASELINE_VERSION,
    )
    replay_path = tmp_path / "reviewed_replay.json"
    replay_path.write_text(json.dumps(replay, ensure_ascii=False), encoding="utf-8")
    return {
        "candidate": candidate_path,
        "manifest": manifest_path,
        "calibration": calibration_path,
        "registry": registry_path,
        "replay": replay_path,
    }


def _promote(paths: dict[str, Path], **overrides):
    kwargs = {
        "candidate_package": paths["candidate"],
        "reviewed_replay": paths["replay"],
        "feedback_manifest": paths["manifest"],
        "baseline_calibration": paths["calibration"],
        "baseline_registry": paths["registry"],
        "baseline_calibration_version": BASELINE_VERSION,
        "approved_by": "user",
        "acknowledge_reviewed_replay": True,
        "allow_degraded": False,
        "approval_note": "reviewed",
    }
    kwargs.update(overrides)
    return CalibrationRulePackagePromoter().promote(**kwargs)


class TestPromotionHappyPath:
    def test_promotes_candidate_without_mutating_candidate(self, tmp_path):
        paths = _write_inputs(tmp_path)
        original_candidate_bytes = paths["candidate"].read_bytes()
        artifacts = _promote(paths)

        assert artifacts.validated_package["status"] == "validated"
        assert artifacts.validated_package["package_id"] == "cal-promotion-test-001"
        assert artifacts.validated_package["validation"]["validator"] == PROMOTION_VERSION
        assert artifacts.validated_package["validation"]["matched"] == 1
        assert paths["candidate"].read_bytes() == original_candidate_bytes

        result = AgentCalibrationRulePackageValidator().validate(
            artifacts.validated_package, require_validated=True
        )
        assert result.is_valid

    def test_receipt_binds_candidate_replay_and_validated_bytes(self, tmp_path):
        paths = _write_inputs(tmp_path)
        artifacts = _promote(paths)
        receipt = artifacts.promotion_receipt

        assert receipt["promotion_version"] == PROMOTION_VERSION
        assert receipt["approved_by"] == "user"
        assert receipt["approval_note"] == "reviewed"
        assert receipt["candidate_package_sha256"] == hashlib.sha256(
            paths["candidate"].read_bytes()
        ).hexdigest()
        assert receipt["reviewed_replay_sha256"] == hashlib.sha256(
            paths["replay"].read_bytes()
        ).hexdigest()
        assert receipt["validated_package_sha256"] == hashlib.sha256(
            artifacts.validated_package_bytes
        ).hexdigest()
        assert receipt["rule_coverage"]["uncovered_rule_ids"] == []

    def test_baseline_files_remain_byte_identical(self, tmp_path):
        paths = _write_inputs(tmp_path)
        before_calibration = paths["calibration"].read_bytes()
        before_registry = paths["registry"].read_bytes()
        _promote(paths)
        assert paths["calibration"].read_bytes() == before_calibration
        assert paths["registry"].read_bytes() == before_registry


class TestPromotionApprovalAndIntegrity:
    def test_explicit_review_acknowledgement_required(self, tmp_path):
        paths = _write_inputs(tmp_path)
        with pytest.raises(PromotionPrecheckError, match="acknowledge"):
            _promote(paths, acknowledge_reviewed_replay=False)

    def test_edited_replay_is_rejected(self, tmp_path):
        paths = _write_inputs(tmp_path)
        payload = json.loads(paths["replay"].read_text(encoding="utf-8"))
        payload["summary"]["improved"] += 1
        paths["replay"].write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(PromotionPrecheckError, match="fresh replay"):
            _promote(paths)

    def test_candidate_bytes_changed_after_review_are_rejected(self, tmp_path):
        paths = _write_inputs(tmp_path)
        candidate = json.loads(paths["candidate"].read_text(encoding="utf-8"))
        candidate["rules"][0]["description"] = "changed after reviewed replay"
        paths["candidate"].write_text(json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(PromotionPrecheckError, match="fresh replay"):
            _promote(paths)


class TestRuleCoverageAndCounts:
    def test_every_enabled_rule_requires_evaluable_applied_coverage(self, tmp_path):
        rule_a = _rule("AGR-A")
        rule_b = _rule("AGR-B", match={"any_terms": ["never-match-product"]})
        paths = _write_inputs(tmp_path, candidate=_candidate([rule_a, rule_b]))
        with pytest.raises(PromotionPrecheckError, match="uncovered"):
            _promote(paths)

    def test_no_evaluable_matched_record_cannot_be_validated(self, tmp_path):
        records = [_record("record-1", actual=None)]
        paths = _write_inputs(tmp_path, records=records)
        with pytest.raises(PromotionPrecheckError, match="no evaluable"):
            _promote(paths)

    def test_validation_counts_exclude_unmatched_evaluable_records(self, tmp_path):
        matching = _record("record-1", actual=_default_actual())
        nonmatching = _record(
            "record-2",
            observation=_observation(
                product_name="cardboard storage box",
                product_type="box",
                rigidity="rigid",
                foldability="none",
            ),
            actual=_default_actual(),
        )
        paths = _write_inputs(tmp_path, records=[matching, nonmatching])
        reviewed = json.loads(paths["replay"].read_text(encoding="utf-8"))
        assert reviewed["summary"]["evaluable_records"] == 2
        assert reviewed["summary"]["unmatched"] >= 1

        artifacts = _promote(paths)
        validation = artifacts.validated_package["validation"]
        assert validation["matched"] == 1
        assert validation["improved"] + validation["unchanged"] + validation["degraded"] == 1


class TestDegradedAcknowledgement:
    def _degraded_paths(self, tmp_path: Path) -> dict[str, Path]:
        degraded_rule = _rule(
            "AGR-DEGRADE",
            action={"type": "smallest_axis_add", "normal_cm": 3.0, "conservative_cm": 4.0},
        )
        paths = _write_inputs(tmp_path, candidate=_candidate([degraded_rule]))
        replay = json.loads(paths["replay"].read_text(encoding="utf-8"))
        assert any(
            item.get("matched") and item.get("status") == "degraded"
            for item in replay["per_record"]
        )
        return paths

    def test_degraded_is_blocked_without_explicit_override(self, tmp_path):
        paths = self._degraded_paths(tmp_path)
        with pytest.raises(PromotionPrecheckError, match="allow_degraded"):
            _promote(paths)

    def test_degraded_can_be_explicitly_accepted(self, tmp_path):
        paths = self._degraded_paths(tmp_path)
        artifacts = _promote(paths, allow_degraded=True)
        assert artifacts.validated_package["validation"]["degraded"] >= 1
        assert "degraded_matched_records_explicitly_accepted" in artifacts.promotion_receipt["warnings"]
        assert artifacts.promotion_receipt["allow_degraded"] is True


class TestPromotionCli:
    def test_cli_requires_explicit_approve_flag(self, tmp_path):
        from tools.calibration_promote_candidate_v1 import main

        paths = _write_inputs(tmp_path / "inputs")
        with pytest.raises(SystemExit):
            main(
                [
                    "--candidate-package", str(paths["candidate"]),
                    "--reviewed-replay", str(paths["replay"]),
                    "--feedback-manifest", str(paths["manifest"]),
                    "--baseline-calibration", str(paths["calibration"]),
                    "--baseline-registry", str(paths["registry"]),
                    "--baseline-calibration-version", BASELINE_VERSION,
                    "--approved-by", "user",
                    "--output-package", str(tmp_path / "validated.json"),
                    "--output-receipt", str(tmp_path / "receipt.json"),
                ]
            )

    def test_cli_writes_validated_package_and_receipt(self, tmp_path):
        from tools.calibration_promote_candidate_v1 import main

        paths = _write_inputs(tmp_path / "inputs")
        output_package = tmp_path / "validated.json"
        output_receipt = tmp_path / "receipt.json"
        exit_code = main(
            [
                "--candidate-package", str(paths["candidate"]),
                "--reviewed-replay", str(paths["replay"]),
                "--feedback-manifest", str(paths["manifest"]),
                "--baseline-calibration", str(paths["calibration"]),
                "--baseline-registry", str(paths["registry"]),
                "--baseline-calibration-version", BASELINE_VERSION,
                "--approved-by", "user",
                "--approval-note", "manual review complete",
                "--approve",
                "--output-package", str(output_package),
                "--output-receipt", str(output_receipt),
            ]
        )
        assert exit_code == 0
        validated = json.loads(output_package.read_text(encoding="utf-8"))
        receipt = json.loads(output_receipt.read_text(encoding="utf-8"))
        assert validated["status"] == "validated"
        assert receipt["validated_package_sha256"] == hashlib.sha256(
            output_package.read_bytes()
        ).hexdigest()
        assert receipt["approved_by"] == "user"
