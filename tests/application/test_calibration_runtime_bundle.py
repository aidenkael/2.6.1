from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from profit_accounting_26.application.calibration_rule_package_validator import (
    AgentCalibrationRulePackageValidator,
)
from profit_accounting_26.application.calibration_rule_promotion import PROMOTION_VERSION
from profit_accounting_26.application.calibration_runtime_bundle import (
    FORMAL_BUNDLE_VERSION,
    CalibrationRuntimeBundleBuilder,
    RuntimeBundlePrecheckError,
)
from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService

BASELINE_VERSION = "baseline-cal-v1"


def _json_bytes(payload) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _validated_package() -> dict:
    return {
        "schema_version": "agent-calibration-rule-package-v1",
        "package_id": "cal-formal-test-001",
        "calibration_version": "agent-formal-v1-r001",
        "created_at": "2026-08-11T00:00:00Z",
        "generator": "offline-agent",
        "source_export_batch_ids": ["batch-001"],
        "base_engine_version": PackagingEstimationService.ENGINE_VERSION,
        "base_calibration_version": BASELINE_VERSION,
        "status": "validated",
        "rules": [
            {
                "rule_id": "AGR-FORMAL-001",
                "enabled": True,
                "priority": 110,
                "description": "formal bundle test rule",
                "match": {"any_terms": ["scarf"], "rigidity": ["soft"]},
                "action": {
                    "type": "smallest_axis_add",
                    "normal_cm": 1.0,
                    "conservative_cm": 2.0,
                },
                "evidence": {
                    "source_record_ids": ["record-1"],
                    "sample_count": 1,
                    "rationale": "test",
                },
            }
        ],
        "validation": {
            "validator": PROMOTION_VERSION,
            "replay_id": "replay-formal-001",
            "engine_version": PackagingEstimationService.ENGINE_VERSION,
            "baseline_calibration_version": BASELINE_VERSION,
            "total_records": 2,
            "matched": 1,
            "improved": 1,
            "unchanged": 0,
            "degraded": 0,
            "conflicts": 0,
        },
    }


def _baseline_registry() -> dict:
    return {
        "version": "baseline-registry-v1",
        "policy": {"conservative_must_not_be_lower_than_normal": True},
        "aggregate_rules": [
            {
                "rule_id": "AGR-BASE-001",
                "enabled": True,
                "priority": 80,
                "name": "base",
                "match": {"any_terms": ["box"]},
                "action": {
                    "type": "smallest_axis_add",
                    "normal_cm": 1.0,
                    "conservative_cm": 2.0,
                },
            }
        ],
        "sample_rules": [
            {
                "rule_id": "CAL-SAMPLE-001",
                "enabled": True,
                "role": "reference",
            }
        ],
    }


def _write_inputs(tmp_path: Path) -> dict[str, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    package = _validated_package()
    package_bytes = _json_bytes(package)
    package_path = tmp_path / "validated.json"
    package_path.write_bytes(package_bytes)

    calibration_path = tmp_path / "baseline_calibration.json"
    calibration_path.write_text(
        json.dumps([{"sample_id": "S1"}, {"sample_id": "S2"}], ensure_ascii=False),
        encoding="utf-8",
    )
    registry_path = tmp_path / "baseline_registry.json"
    registry_path.write_text(
        json.dumps(_baseline_registry(), ensure_ascii=False), encoding="utf-8"
    )

    validation = package["validation"]
    receipt = {
        "promotion_version": PROMOTION_VERSION,
        "promoted_at": "2026-08-11T00:10:00Z",
        "approved_by": "user",
        "approval_note": "reviewed",
        "allow_degraded": False,
        "candidate_package_id": package["package_id"],
        "reviewed_replay_id": validation["replay_id"],
        "candidate_package_sha256": "1" * 64,
        "reviewed_replay_sha256": "2" * 64,
        "validated_package_sha256": hashlib.sha256(package_bytes).hexdigest(),
        "input_fingerprints": {
            "feedback_manifest_sha256": "3" * 64,
            "candidate_package_sha256": "1" * 64,
            "baseline_calibration_sha256": hashlib.sha256(
                calibration_path.read_bytes()
            ).hexdigest(),
            "baseline_registry_sha256": hashlib.sha256(
                registry_path.read_bytes()
            ).hexdigest(),
        },
        "baseline_calibration_version": BASELINE_VERSION,
        "validation_counts": validation,
        "rule_coverage": {
            "enabled_rule_ids": ["AGR-FORMAL-001"],
            "covered_rule_ids": ["AGR-FORMAL-001"],
            "uncovered_rule_ids": [],
        },
        "warnings": [],
    }
    receipt_path = tmp_path / "promotion_receipt.json"
    receipt_path.write_bytes(_json_bytes(receipt))
    return {
        "package": package_path,
        "receipt": receipt_path,
        "calibration": calibration_path,
        "registry": registry_path,
    }


def _build(paths: dict[str, Path]):
    return CalibrationRuntimeBundleBuilder().build(
        validated_package=paths["package"],
        promotion_receipt=paths["receipt"],
        baseline_calibration=paths["calibration"],
        baseline_registry=paths["registry"],
        baseline_calibration_version=BASELINE_VERSION,
    )


class TestRuntimeBundleHappyPath:
    def test_builds_exact_formal_bundle_files(self, tmp_path):
        paths = _write_inputs(tmp_path)
        bundle = _build(paths)
        with zipfile.ZipFile(io.BytesIO(bundle.bundle_bytes)) as archive:
            assert set(archive.namelist()) == {
                "formal_package_manifest.json",
                "runtime_calibration.json",
                "packaging_rule_registry_v1.json",
                "validated_rule_package.json",
                "promotion_receipt.json",
            }
            manifest = json.loads(archive.read("formal_package_manifest.json"))
            assert manifest["contract_version"] == FORMAL_BUNDLE_VERSION
            assert manifest["package_id"] == "cal-formal-test-001"
            assert manifest["calibration_version"] == "agent-formal-v1-r001"

    def test_runtime_registry_preserves_baseline_and_adds_validated_rules(self, tmp_path):
        paths = _write_inputs(tmp_path)
        bundle = _build(paths)
        aggregate_ids = [rule["rule_id"] for rule in bundle.runtime_registry["aggregate_rules"]]
        assert aggregate_ids == ["AGR-BASE-001", "AGR-FORMAL-001"]
        assert bundle.runtime_registry["sample_rules"] == _baseline_registry()["sample_rules"]
        assert bundle.runtime_registry["policy"] == _baseline_registry()["policy"]
        assert bundle.runtime_registry["version"] == "agent-formal-v1-r001"
        compiled = bundle.runtime_registry["aggregate_rules"][1]
        assert compiled["name"] == "formal bundle test rule"

    def test_manifest_runtime_hashes_match_zip_payloads(self, tmp_path):
        paths = _write_inputs(tmp_path)
        bundle = _build(paths)
        with zipfile.ZipFile(io.BytesIO(bundle.bundle_bytes)) as archive:
            runtime_calibration = archive.read("runtime_calibration.json")
            runtime_registry = archive.read("packaging_rule_registry_v1.json")
        fingerprints = bundle.manifest["runtime_fingerprints"]
        assert fingerprints["runtime_calibration_sha256"] == hashlib.sha256(
            runtime_calibration
        ).hexdigest()
        assert fingerprints["runtime_registry_sha256"] == hashlib.sha256(
            runtime_registry
        ).hexdigest()
        assert bundle.manifest["runtime_summary"]["sample_count"] == 2
        assert bundle.manifest["runtime_summary"]["validated_rule_ids"] == [
            "AGR-FORMAL-001"
        ]

    def test_source_files_are_not_modified(self, tmp_path):
        paths = _write_inputs(tmp_path)
        before = {key: path.read_bytes() for key, path in paths.items()}
        _build(paths)
        assert {key: path.read_bytes() for key, path in paths.items()} == before


class TestRuntimeBundleIntegrity:
    def test_non_validated_package_is_rejected(self, tmp_path):
        paths = _write_inputs(tmp_path)
        package = json.loads(paths["package"].read_text(encoding="utf-8"))
        package["status"] = "candidate"
        package["validation"] = None
        paths["package"].write_bytes(_json_bytes(package))
        with pytest.raises(RuntimeBundlePrecheckError, match="validated Rule Package"):
            _build(paths)

    def test_validated_package_byte_change_is_rejected_by_receipt_hash(self, tmp_path):
        paths = _write_inputs(tmp_path)
        package = json.loads(paths["package"].read_text(encoding="utf-8"))
        package["rules"][0]["description"] = "changed"
        paths["package"].write_bytes(_json_bytes(package))
        with pytest.raises(RuntimeBundlePrecheckError, match="validated_package_sha256"):
            _build(paths)

    def test_baseline_calibration_change_is_rejected(self, tmp_path):
        paths = _write_inputs(tmp_path)
        paths["calibration"].write_text(
            json.dumps([{"sample_id": "OTHER"}]), encoding="utf-8"
        )
        with pytest.raises(RuntimeBundlePrecheckError, match="calibration bytes differ"):
            _build(paths)

    def test_baseline_registry_change_is_rejected(self, tmp_path):
        paths = _write_inputs(tmp_path)
        registry = json.loads(paths["registry"].read_text(encoding="utf-8"))
        registry["policy"]["changed"] = True
        paths["registry"].write_text(json.dumps(registry), encoding="utf-8")
        with pytest.raises(RuntimeBundlePrecheckError, match="registry bytes differ"):
            _build(paths)

    def test_wrong_baseline_version_is_rejected(self, tmp_path):
        paths = _write_inputs(tmp_path)
        with pytest.raises(RuntimeBundlePrecheckError, match="baseline calibration version"):
            CalibrationRuntimeBundleBuilder().build(
                validated_package=paths["package"],
                promotion_receipt=paths["receipt"],
                baseline_calibration=paths["calibration"],
                baseline_registry=paths["registry"],
                baseline_calibration_version="wrong-version",
            )

    def test_runtime_calibration_requires_top_level_sample_list(self, tmp_path):
        paths = _write_inputs(tmp_path)
        wrapper = {"version": BASELINE_VERSION, "samples": [{"sample_id": "S1"}]}
        paths["calibration"].write_text(json.dumps(wrapper), encoding="utf-8")
        receipt = json.loads(paths["receipt"].read_text(encoding="utf-8"))
        receipt["input_fingerprints"]["baseline_calibration_sha256"] = hashlib.sha256(
            paths["calibration"].read_bytes()
        ).hexdigest()
        paths["receipt"].write_bytes(_json_bytes(receipt))
        with pytest.raises(RuntimeBundlePrecheckError, match="runtime-compatible"):
            _build(paths)


class TestRuntimeBundleCli:
    def test_cli_writes_parseable_zip(self, tmp_path):
        from tools.calibration_build_runtime_bundle_v1 import main

        paths = _write_inputs(tmp_path / "inputs")
        output = tmp_path / "formal_bundle.zip"
        exit_code = main(
            [
                "--validated-package", str(paths["package"]),
                "--promotion-receipt", str(paths["receipt"]),
                "--baseline-calibration", str(paths["calibration"]),
                "--baseline-registry", str(paths["registry"]),
                "--baseline-calibration-version", BASELINE_VERSION,
                "--output", str(output),
            ]
        )
        assert exit_code == 0
        assert output.is_file()
        with zipfile.ZipFile(output) as archive:
            manifest = json.loads(archive.read("formal_package_manifest.json"))
            assert manifest["contract_version"] == FORMAL_BUNDLE_VERSION
            validated = json.loads(archive.read("validated_rule_package.json"))
            assert AgentCalibrationRulePackageValidator().validate(
                validated, require_validated=True
            ).is_valid
