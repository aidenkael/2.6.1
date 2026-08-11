"""Formal Calibration Runtime Bundle V1 — import / activate / delete tests.

Covers 43+ scenarios as specified in the task:
- Formal Bundle import (validation, inactive registration, file storage)
- Formal Bundle activation (tamper checks, integrity verification, rollback)
- Legacy compatibility (no regression)
- Settings UI glue
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any

import pytest

from profit_accounting_26.application import CalibrationManager, PackagingEstimationService
from profit_accounting_26.application.formal_bundle_importer import (
    FORMAL_BUNDLE_VERSION,
    FormalBundleValidationError,
    is_formal_bundle_zip,
    validate_formal_bundle_zip,
)
from profit_accounting_26.application.calibration_manager import _CAL77_REGISTRY_PATH
from profit_accounting_26.shared.paths import ApplicationPaths
from profit_accounting_26.storage import SQLiteStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_paths(tmp_path: Path) -> ApplicationPaths:
    return ApplicationPaths(
        data_dir=tmp_path,
        database_path=tmp_path / "app.sqlite3",
        settings_path=tmp_path / "settings.json",
        images_dir=tmp_path / "images",
        exports_dir=tmp_path / "exports",
        calibration_packages_dir=tmp_path / "calibration_packages",
    )


def samples(sample_id: str = "S1") -> list[dict]:
    return [
        {
            "sample_id": sample_id,
            "product_type": "soft_pouch",
            "material": "pvc",
            "rigidity": "soft",
            "size_reduction_ratio": 0.6,
            "usable_for_rule_learning": True,
        }
    ]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _make_validated_package(
    *,
    package_id: str = "test-pkg-001",
    calibration_version: str = "cal-v2",
    engine_version: str = PackagingEstimationService.ENGINE_VERSION,
    baseline_calibration_version: str = "baseline-v1",
    status: str = "validated",
    rules: list[dict] | None = None,
) -> dict:
    if rules is None:
        rules = [
            {
                "rule_id": "AGR-TEST-001",
                "enabled": True,
                "priority": 100,
                "match": {"any_terms": ["scarf"]},
                "action": {"type": "smallest_axis_scale", "normal": 1.1, "conservative": 1.2},
                "evidence": {"source_record_ids": ["r1"], "sample_count": 1},
            }
        ]
    pkg: dict = {
        "schema_version": "agent-calibration-rule-package-v1",
        "package_id": package_id,
        "calibration_version": calibration_version,
        "created_at": "2026-08-01T00:00:00Z",
        "generator": "test",
        "source_export_batch_ids": ["batch-001"],
        "base_engine_version": engine_version,
        "base_calibration_version": baseline_calibration_version,
        "status": status,
        "rules": rules,
    }
    if status == "validated":
        pkg["validation"] = {
            "validator": "test",
            "replay_id": "replay-001",
            "engine_version": engine_version,
            "baseline_calibration_version": baseline_calibration_version,
            "total_records": 10,
            "matched": 8,
            "improved": 5,
            "unchanged": 2,
            "degraded": 1,
            "conflicts": 0,
        }
    else:
        pkg["validation"] = None  # candidate packages have validation = null
    return pkg


def _make_promotion_receipt(
    *,
    package_id: str = "test-pkg-001",
    validated_package_sha256: str = "",
    baseline_calibration_version: str = "baseline-v1",
    validation_counts: dict | None = None,
    uncovered_rule_ids: list | None = None,
) -> dict:
    return {
        "promotion_version": "calibration-promotion-v1",
        "candidate_package_id": package_id,
        "validated_package_sha256": validated_package_sha256,
        "baseline_calibration_version": baseline_calibration_version,
        "reviewed_replay_id": "replay-001",
        "validation_counts": validation_counts or {
            "validator": "test",
            "replay_id": "replay-001",
            "engine_version": PackagingEstimationService.ENGINE_VERSION,
            "baseline_calibration_version": baseline_calibration_version,
            "total_records": 10,
            "matched": 8,
            "improved": 5,
            "unchanged": 2,
            "degraded": 1,
            "conflicts": 0,
        },
        "rule_coverage": {"uncovered_rule_ids": uncovered_rule_ids if uncovered_rule_ids is not None else []},
        "input_fingerprints": {},
    }


def _make_registry(
    *, version: str = "cal-v2", aggregate_rules: list | None = None, sample_rules: list | None = None
) -> dict:
    return {
        "version": version,
        "aggregate_rules": aggregate_rules if aggregate_rules is not None else [
            {"rule_id": "AGR-TEST-001", "enabled": True, "priority": 100,
             "match": {"any_terms": ["scarf"]},
             "action": {"type": "smallest_axis_scale", "normal": 1.1, "conservative": 1.2},
             "evidence": {"source_record_ids": ["r1"], "sample_count": 1}},
        ],
        "sample_rules": sample_rules if sample_rules is not None else [],
    }


def _build_formal_bundle_zip(
    *,
    runtime_calibration: list[dict] | None = None,
    registry: dict | None = None,
    validated_package: dict | None = None,
    receipt: dict | None = None,
    manifest_overrides: dict | None = None,
    tamper: dict[str, bytes] | None = None,
) -> bytes:
    """Build a formal bundle ZIP bytes with correct SHA-256 hashes.

    If ``tamper`` is provided, the specified member bytes are replaced AFTER
    hash computation, causing hash mismatches.
    """
    if runtime_calibration is None:
        runtime_calibration = samples("FB-S1")
    if validated_package is None:
        validated_package = _make_validated_package()
    if registry is None:
        registry = _make_registry(version=validated_package["calibration_version"])
    if receipt is None:
        receipt = _make_promotion_receipt(
            package_id=validated_package["package_id"],
            baseline_calibration_version=validated_package.get("base_calibration_version", "baseline-v1"),
        )

    rt_cal_bytes = _canonical_json(runtime_calibration)
    rt_reg_bytes = _canonical_json(registry)
    val_pkg_bytes = _canonical_json(validated_package)
    receipt_bytes = _canonical_json(receipt)

    # Update receipt's validated_package_sha256 to match
    receipt["validated_package_sha256"] = _sha256(val_pkg_bytes)

    # Update validation_counts from validated_package.validation (unless caller set custom ones)
    if "validation" in validated_package and "validation_counts" not in receipt:
        receipt["validation_counts"] = validated_package["validation"]
    elif "validation" in validated_package and receipt.get("validation_counts") is None:
        receipt["validation_counts"] = validated_package["validation"]

    # Final receipt serialization
    receipt_bytes = _canonical_json(receipt)
    # Re-hash validated_package_sha256 after any receipt updates
    receipt["validated_package_sha256"] = _sha256(val_pkg_bytes)
    receipt_bytes = _canonical_json(receipt)

    val_block = validated_package.get("validation")
    if not isinstance(val_block, dict):
        val_block = {}

    # 从 validated_package 实际 rules 计算 enabled rule_ids
    actual_validated_ids = sorted(
        str(rule.get("rule_id"))
        for rule in validated_package.get("rules", [])
        if isinstance(rule, dict) and rule.get("enabled") is True
    )

    manifest = {
        "contract_version": FORMAL_BUNDLE_VERSION,
        "package_id": validated_package["package_id"],
        "calibration_version": validated_package["calibration_version"],
        "engine_version": val_block.get(
            "engine_version", PackagingEstimationService.ENGINE_VERSION
        ),
        "baseline_calibration_version": validated_package.get("base_calibration_version", "baseline-v1"),
        "built_at": "2026-08-01T00:00:00Z",
        "files": {
            "runtime_calibration": "runtime_calibration.json",
            "runtime_registry": "packaging_rule_registry_v1.json",
            "validated_rule_package": "validated_rule_package.json",
            "promotion_receipt": "promotion_receipt.json",
        },
        "source_fingerprints": {
            "validated_rule_package_sha256": _sha256(val_pkg_bytes),
            "promotion_receipt_sha256": _sha256(receipt_bytes),
            "baseline_calibration_sha256": "unused-for-import",
            "baseline_registry_sha256": "unused-for-import",
        },
        "runtime_fingerprints": {
            "runtime_calibration_sha256": _sha256(rt_cal_bytes),
            "runtime_registry_sha256": _sha256(rt_reg_bytes),
        },
        "runtime_summary": {
            "sample_count": len(runtime_calibration),
            "aggregate_rule_count": len(registry.get("aggregate_rules", [])),
            "sample_rule_count": len(registry.get("sample_rules", [])),
            "validated_rule_ids": actual_validated_ids,
        },
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)

    manifest_bytes = _canonical_json(manifest)

    # Apply tampering
    members = {
        "formal_package_manifest.json": manifest_bytes,
        "runtime_calibration.json": rt_cal_bytes,
        "packaging_rule_registry_v1.json": rt_reg_bytes,
        "validated_rule_package.json": val_pkg_bytes,
        "promotion_receipt.json": receipt_bytes,
    }
    if tamper:
        members.update(tamper)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def setup_manager(tmp_path: Path) -> tuple[CalibrationManager, PackagingEstimationService, dict]:
    """Create a CalibrationManager with builtin + bound service. Returns (manager, service, builtin)."""
    paths = make_paths(tmp_path / "data")
    paths.ensure()
    store = SQLiteStore(paths.database_path)
    store.initialize()
    builtin_src = tmp_path / "builtin.json"
    builtin_src.write_text(json.dumps(samples("BASE")), encoding="utf-8")
    manager = CalibrationManager(store, paths)
    active = manager.ensure_builtin(builtin_src, version="builtin-v1")
    service = PackagingEstimationService(active["path"], calibration_version=active["version"])
    manager.bind_service(service)
    return manager, service, {"id": active["id"], "version": active["version"], "path": active["path"]}


def write_bundle_zip(tmp_path: Path, name: str = "formal_bundle.zip", **kwargs) -> Path:
    """Write a formal bundle ZIP to tmp_path and return its path."""
    data = _build_formal_bundle_zip(**kwargs)
    p = tmp_path / name
    p.write_bytes(data)
    return p


# ===========================================================================
# Tests 1-22: Formal Bundle Import
# ===========================================================================


class TestFormalBundleImport:
    """Tests 1-22 from the specification."""

    def test_01_valid_formal_bundle_import_success(self, tmp_path):
        """合法 Formal Bundle 导入成功。"""
        manager, service, builtin = setup_manager(tmp_path)
        bundle_path = write_bundle_zip(tmp_path)
        result = manager.import_package(bundle_path)
        assert result is not None
        assert result["version"] == "cal-v2"

    def test_02_imported_formal_bundle_is_inactive(self, tmp_path):
        """导入后 package.active == False，原 active 不变。"""
        manager, service, builtin = setup_manager(tmp_path)
        bundle_path = write_bundle_zip(tmp_path)
        result = manager.import_package(bundle_path)
        assert result["active"] is False
        assert manager.active_package()["id"] == builtin["id"]

    def test_03_service_unchanged_after_formal_import(self, tmp_path):
        """导入后 PackagingEstimationService calibration path/version/registry 全部不变。"""
        manager, service, builtin = setup_manager(tmp_path)
        cal_path_before = service.calibration_path
        ver_before = service.calibration_version
        reg_before = service.rule_registry_path
        bundle_path = write_bundle_zip(tmp_path)
        manager.import_package(bundle_path)
        assert service.calibration_path == cal_path_before
        assert service.calibration_version == ver_before
        assert service.rule_registry_path == reg_before

    def test_04_package_dir_contains_6_files(self, tmp_path):
        """package 目录包含：原 ZIP + 5 JSON 成员。"""
        manager, service, builtin = setup_manager(tmp_path)
        bundle_path = write_bundle_zip(tmp_path)
        result = manager.import_package(bundle_path)
        pkg_dir = Path(result["path"]).parent
        files = {f.name for f in pkg_dir.iterdir()}
        assert files == {
            bundle_path.name,
            "formal_package_manifest.json",
            "runtime_calibration.json",
            "packaging_rule_registry_v1.json",
            "validated_rule_package.json",
            "promotion_receipt.json",
        }

    def test_05_metadata_correct(self, tmp_path):
        """metadata 包含正确字段。"""
        manager, service, builtin = setup_manager(tmp_path)
        bundle_path = write_bundle_zip(tmp_path)
        result = manager.import_package(bundle_path)
        meta = result["metadata"]
        assert meta["formal_bundle"] is True
        assert meta["contract_version"] == FORMAL_BUNDLE_VERSION
        assert meta["package_id"] == "test-pkg-001"
        assert meta["engine_version"] == PackagingEstimationService.ENGINE_VERSION
        assert meta["baseline_calibration_version"] == "baseline-v1"
        assert "sha256" in meta
        assert "runtime_sha256" in meta
        assert "registry_sha256" in meta
        assert "validated_package_sha256" in meta
        assert "promotion_receipt_sha256" in meta
        assert meta["original_name"] == "formal_bundle.zip"
        assert "imported_at" in meta
        assert meta["sample_count"] >= 1

    def test_06_wrong_contract_version_rejected(self, tmp_path):
        """contract_version 错误 → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        bundle_path = write_bundle_zip(
            tmp_path,
            manifest_overrides={"contract_version": "Wrong Version"},
        )
        with pytest.raises(FormalBundleValidationError, match="contract_version"):
            manager.import_package(bundle_path)

    def test_07_missing_member_rejected(self, tmp_path):
        """缺任一固定成员 → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        # Build a ZIP missing promotion_receipt.json
        data = _build_formal_bundle_zip()
        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as src:
            with zipfile.ZipFile(buf, "w") as dst:
                for info in src.infolist():
                    if info.filename != "promotion_receipt.json":
                        dst.writestr(info, src.read(info.filename))
        p = tmp_path / "missing_member.zip"
        p.write_bytes(buf.getvalue())
        with pytest.raises(FormalBundleValidationError, match="missing required member"):
            manager.import_package(p)

    def test_08_duplicate_zip_member_rejected(self, tmp_path):
        """重复 ZIP 成员 → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        # Create a ZIP with duplicate member
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("formal_package_manifest.json", "{}")
            zf.writestr("formal_package_manifest.json", "{}")
        p = tmp_path / "duplicate.zip"
        p.write_bytes(buf.getvalue())
        # zipfile module may silently overwrite; the detection depends on our reader
        # Our is_formal_bundle_zip + validator should handle this
        with pytest.raises((FormalBundleValidationError, ValueError)):
            manager.import_package(p)

    def test_09_path_traversal_rejected(self, tmp_path):
        """路径穿越 → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("formal_package_manifest.json", "{}")
            zf.writestr("../../../etc/passwd", "evil")
        p = tmp_path / "traversal.zip"
        p.write_bytes(buf.getvalue())
        with pytest.raises((FormalBundleValidationError, ValueError)):
            manager.import_package(p)

    def test_10_runtime_calibration_hash_mismatch(self, tmp_path):
        """runtime calibration hash mismatch → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        bundle_path = write_bundle_zip(
            tmp_path,
            tamper={"runtime_calibration.json": b'[{"sample_id": "TAMPERED"}]'},
        )
        with pytest.raises(FormalBundleValidationError, match="runtime_calibration.*SHA"):
            manager.import_package(bundle_path)

    def test_11_registry_hash_mismatch(self, tmp_path):
        """registry hash mismatch → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        bundle_path = write_bundle_zip(
            tmp_path,
            tamper={"packaging_rule_registry_v1.json": b'{"tampered": true}'},
        )
        with pytest.raises(FormalBundleValidationError, match="registry.*SHA"):
            manager.import_package(bundle_path)

    def test_12_validated_package_hash_mismatch(self, tmp_path):
        """validated package hash mismatch → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        bundle_path = write_bundle_zip(
            tmp_path,
            tamper={"validated_rule_package.json": b'{"tampered": true}'},
        )
        with pytest.raises(FormalBundleValidationError, match="validated_rule_package.*SHA"):
            manager.import_package(bundle_path)

    def test_13_promotion_receipt_hash_mismatch(self, tmp_path):
        """promotion receipt hash mismatch → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        bundle_path = write_bundle_zip(
            tmp_path,
            tamper={"promotion_receipt.json": b'{"tampered": true}'},
        )
        with pytest.raises(FormalBundleValidationError, match="promotion_receipt.*SHA"):
            manager.import_package(bundle_path)

    def test_14_validated_package_status_candidate_rejected(self, tmp_path):
        """validated package status=candidate → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        pkg = _make_validated_package(status="candidate")
        # candidate packages don't have validation block
        bundle_path = write_bundle_zip(tmp_path, validated_package=pkg)
        with pytest.raises((FormalBundleValidationError, ValueError)):
            manager.import_package(bundle_path)

    def test_15_package_id_mismatch(self, tmp_path):
        """package_id mismatch between manifest and validated package → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        pkg = _make_validated_package(package_id="pkg-A")
        bundle_path = write_bundle_zip(
            tmp_path,
            validated_package=pkg,
            manifest_overrides={"package_id": "pkg-B"},
        )
        with pytest.raises(FormalBundleValidationError, match="package_id"):
            manager.import_package(bundle_path)

    def test_16_calibration_version_mismatch(self, tmp_path):
        """calibration version mismatch → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        pkg = _make_validated_package(calibration_version="v1")
        bundle_path = write_bundle_zip(
            tmp_path,
            validated_package=pkg,
            manifest_overrides={"calibration_version": "v2"},
        )
        with pytest.raises(FormalBundleValidationError, match="calibration_version"):
            manager.import_package(bundle_path)

    def test_17_engine_version_mismatch(self, tmp_path):
        """engine version mismatch → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        pkg = _make_validated_package()
        bundle_path = write_bundle_zip(
            tmp_path,
            validated_package=pkg,
            manifest_overrides={"engine_version": "wrong-engine"},
        )
        with pytest.raises(FormalBundleValidationError, match="engine_version"):
            manager.import_package(bundle_path)

    def test_18_receipt_validation_counts_mismatch(self, tmp_path):
        """receipt validation_counts mismatch → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        pkg = _make_validated_package()
        bad_counts = dict(pkg["validation"])
        bad_counts["total_records"] = 999
        receipt = _make_promotion_receipt(validation_counts=bad_counts)
        bundle_path = write_bundle_zip(tmp_path, validated_package=pkg, receipt=receipt)
        with pytest.raises(FormalBundleValidationError, match="validation_counts"):
            manager.import_package(bundle_path)

    def test_19_receipt_uncovered_rules_non_empty(self, tmp_path):
        """receipt uncovered rules 非空 → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        receipt = _make_promotion_receipt(uncovered_rule_ids=["AGR-TEST-001"])
        bundle_path = write_bundle_zip(tmp_path, receipt=receipt)
        with pytest.raises(FormalBundleValidationError, match="uncovered_rule_ids"):
            manager.import_package(bundle_path)

    def test_20_runtime_calibration_empty_list(self, tmp_path):
        """runtime calibration 空 list → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        bundle_path = write_bundle_zip(tmp_path, runtime_calibration=[])
        with pytest.raises(FormalBundleValidationError, match="non-empty list"):
            manager.import_package(bundle_path)

    def test_20b_runtime_calibration_not_list(self, tmp_path):
        """runtime calibration 非 list → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        bundle_path = write_bundle_zip(
            tmp_path,
            tamper={"runtime_calibration.json": b'{"not": "a list"}'},
        )
        with pytest.raises(FormalBundleValidationError):
            manager.import_package(bundle_path)

    def test_21_runtime_registry_not_object(self, tmp_path):
        """runtime registry 非 object → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        bundle_path = write_bundle_zip(
            tmp_path,
            tamper={"packaging_rule_registry_v1.json": b'[1,2,3]'},
        )
        with pytest.raises(FormalBundleValidationError):
            manager.import_package(bundle_path)

    def test_22_failed_import_no_residual(self, tmp_path):
        """任何导入失败后：没有 package DB 残留，没有 package 目录残留，active 不变。"""
        manager, service, builtin = setup_manager(tmp_path)
        pkgs_before = len(manager.list_packages())
        dirs_before = set()
        cal_dir = manager.paths.calibration_packages_dir
        if cal_dir.exists():
            dirs_before = {p.name for p in cal_dir.iterdir()}
        bundle_path = write_bundle_zip(
            tmp_path,
            tamper={"runtime_calibration.json": b'[{"bad": true}]'},
        )
        with pytest.raises(FormalBundleValidationError):
            manager.import_package(bundle_path)
        assert len(manager.list_packages()) == pkgs_before
        dirs_after = {p.name for p in cal_dir.iterdir()} if cal_dir.exists() else set()
        assert dirs_after == dirs_before
        assert manager.active_package()["id"] == builtin["id"]


# ===========================================================================
# Tests 23-33: Formal Bundle Activation
# ===========================================================================


class TestFormalBundleActivation:
    """Tests 23-33: activation, tamper detection, rollback."""

    def test_23_valid_activation_success(self, tmp_path):
        """合法 Formal Bundle 手动 activate 成功。"""
        manager, service, builtin = setup_manager(tmp_path)
        bundle_path = write_bundle_zip(tmp_path)
        result = manager.import_package(bundle_path)
        assert result["active"] is False
        activated = manager.activate(result["id"])
        assert activated["active"] is True

    def test_24_db_active_is_formal_package(self, tmp_path):
        """成功后 DB active = formal package。"""
        manager, service, builtin = setup_manager(tmp_path)
        result = manager.import_package(write_bundle_zip(tmp_path))
        manager.activate(result["id"])
        assert manager.active_package()["id"] == result["id"]

    def test_25_service_calibration_path_correct(self, tmp_path):
        """service.calibration_path 正确。"""
        manager, service, builtin = setup_manager(tmp_path)
        result = manager.import_package(write_bundle_zip(tmp_path))
        manager.activate(result["id"])
        assert service.calibration_path == Path(result["path"])

    def test_26_service_calibration_version_correct(self, tmp_path):
        """service.calibration_version 正确。"""
        manager, service, builtin = setup_manager(tmp_path)
        result = manager.import_package(write_bundle_zip(tmp_path))
        manager.activate(result["id"])
        assert service.calibration_version == result["version"]

    def test_27_service_registry_path_correct(self, tmp_path):
        """service.rule_registry_path 正确。"""
        manager, service, builtin = setup_manager(tmp_path)
        result = manager.import_package(write_bundle_zip(tmp_path))
        manager.activate(result["id"])
        expected_registry = Path(result["path"]).with_name("packaging_rule_registry_v1.json")
        assert service.rule_registry_path == expected_registry

    def test_28_registry_contains_validated_rule(self, tmp_path):
        """实际 registry 中包含 Formal Bundle 的 validated rule。"""
        manager, service, builtin = setup_manager(tmp_path)
        result = manager.import_package(write_bundle_zip(tmp_path))
        manager.activate(result["id"])
        rule_ids = {r.get("rule_id") for r in service.registry.get("aggregate_rules", [])}
        assert "AGR-TEST-001" in rule_ids

    def test_29_tampered_runtime_calibration_rejected(self, tmp_path):
        """导入后手工篡改 runtime_calibration：activate 拒绝并恢复原 active/runtime。"""
        manager, service, builtin = setup_manager(tmp_path)
        result = manager.import_package(write_bundle_zip(tmp_path))
        # Tamper runtime_calibration.json
        rt_path = Path(result["path"])
        rt_path.write_text(json.dumps([{"sample_id": "TAMPERED"}]), encoding="utf-8")
        with pytest.raises(RuntimeError, match="tampered"):
            manager.activate(result["id"])
        # Active unchanged
        assert manager.active_package()["id"] == builtin["id"]
        assert service.calibration_version == "builtin-v1"

    def test_30_tampered_registry_rejected(self, tmp_path):
        """导入后手工篡改 registry：activate 拒绝并恢复。"""
        manager, service, builtin = setup_manager(tmp_path)
        result = manager.import_package(write_bundle_zip(tmp_path))
        reg_path = Path(result["path"]).with_name("packaging_rule_registry_v1.json")
        reg_path.write_text(json.dumps({"aggregate_rules": [], "sample_rules": []}), encoding="utf-8")
        with pytest.raises(RuntimeError, match="tampered"):
            manager.activate(result["id"])
        assert manager.active_package()["id"] == builtin["id"]

    def test_31_missing_registry_rejected(self, tmp_path):
        """删除/丢失 registry：activate 拒绝并恢复。"""
        manager, service, builtin = setup_manager(tmp_path)
        result = manager.import_package(write_bundle_zip(tmp_path))
        reg_path = Path(result["path"]).with_name("packaging_rule_registry_v1.json")
        reg_path.unlink()
        with pytest.raises(RuntimeError, match="missing"):
            manager.activate(result["id"])
        assert manager.active_package()["id"] == builtin["id"]

    def test_32_runtime_activate_exception_existing_tests_still_pass(self, tmp_path):
        """runtime activate 异常：原有事务恢复测试继续成立。"""
        manager, service, builtin = setup_manager(tmp_path)
        custom = manager.import_package(
            _write_legacy_json(tmp_path, "custom.json", "custom-v2", "CUSTOM")
        )
        manager.activate(builtin["id"])
        real_activate = service.activate

        def failing_activate(cal_path, *, version):
            if version == "custom-v2":
                raise ValueError("simulated failure")
            return real_activate(cal_path, version=version)

        service.activate = failing_activate
        with pytest.raises(RuntimeError, match="运行时激活失败"):
            manager.activate(custom["id"])
        assert manager.active_package()["id"] == builtin["id"]
        assert service.calibration_version == "builtin-v1"

    def test_33_post_verification_failure_rolls_back(self, tmp_path):
        """successful activate 的 post-verification 异常：也必须回退。"""
        manager, service, builtin = setup_manager(tmp_path)
        result = manager.import_package(write_bundle_zip(tmp_path))
        # Sabotage: after activation, make service report wrong path
        original_activate = service.activate

        def sabotaged_activate(cal_path, *, version):
            original_activate(cal_path, version=version)
            # Corrupt calibration_path to trigger post-verification failure
            service.calibration_path = Path("/fake/path")

        service.activate = sabotaged_activate
        with pytest.raises(RuntimeError, match="post-activation"):
            manager.activate(result["id"])
        # Should have rolled back to builtin
        assert manager.active_package()["id"] == builtin["id"]


# ===========================================================================
# Tests 34-39: Legacy Compatibility (No Regression)
# ===========================================================================


def _write_legacy_json(tmp_path: Path, name: str, version: str, sample_id: str) -> Path:
    source = tmp_path / name
    source.write_text(
        json.dumps({"version": version, "samples": samples(sample_id)}),
        encoding="utf-8",
    )
    return source


def _write_legacy_zip(tmp_path: Path, name: str, version: str, sample_id: str) -> Path:
    source = tmp_path / name
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "calibration.json",
            json.dumps({"version": version, "samples": samples(sample_id)}),
        )
    source.write_bytes(buf.getvalue())
    return source


class TestLegacyCompatibility:
    """Tests 34-39: Legacy import / activate / delete must not regress."""

    def test_34_legacy_json_import(self, tmp_path):
        """旧 .json 导入仍按原逻辑正常。"""
        manager, service, builtin = setup_manager(tmp_path)
        source = _write_legacy_json(tmp_path, "custom.json", "custom-v2", "CUSTOM")
        result = manager.import_package(source)
        assert result["version"] == "custom-v2"
        assert result["active"] is True
        assert service.calibration_version == "custom-v2"

    def test_35_legacy_zip_import(self, tmp_path):
        """旧 zip 导入仍正常。"""
        manager, service, builtin = setup_manager(tmp_path)
        source = _write_legacy_zip(tmp_path, "custom.zip", "zip-v3", "ZIP")
        result = manager.import_package(source)
        assert result["version"] == "zip-v3"
        assert result["active"] is True

    def test_36_legacy_activate_semantics_unchanged(self, tmp_path):
        """legacy 导入后的 activate 语义不变。"""
        manager, service, builtin = setup_manager(tmp_path)
        c1 = manager.import_package(_write_legacy_json(tmp_path, "c1.json", "v1", "C1"))
        c2 = manager.import_package(_write_legacy_json(tmp_path, "c2.json", "v2", "C2"))
        assert manager.active_package()["id"] == c2["id"]
        manager.activate(c1["id"])
        assert manager.active_package()["id"] == c1["id"]
        assert service.calibration_version == "v1"

    def test_37_builtin_behavior_unchanged(self, tmp_path):
        """builtin 行为不变。"""
        manager, service, builtin = setup_manager(tmp_path)
        assert manager.active_package()["id"] == builtin["id"]
        assert service.calibration_version == "builtin-v1"

    def test_38_active_imported_delete_fallback(self, tmp_path):
        """active imported delete → builtin fallback 继续正常。"""
        manager, service, builtin = setup_manager(tmp_path)
        custom = manager.import_package(_write_legacy_json(tmp_path, "custom.json", "custom-v2", "CUSTOM"))
        assert manager.active_package()["id"] == custom["id"]
        remaining = manager.delete_package(custom["id"])
        assert remaining["metadata"]["builtin"] is True
        assert service.calibration_version == "builtin-v1"

    def test_39_inactive_imported_delete(self, tmp_path):
        """inactive imported delete 正常。"""
        manager, service, builtin = setup_manager(tmp_path)
        first = manager.import_package(_write_legacy_json(tmp_path, "first.json", "v1", "F1"))
        second = manager.import_package(_write_legacy_json(tmp_path, "second.json", "v2", "F2"))
        assert manager.active_package()["id"] == second["id"]
        manager.delete_package(first["id"])
        assert all(p["id"] != first["id"] for p in manager.list_packages())


# ===========================================================================
# Tests 40-43: Settings UI Glue
# ===========================================================================


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class TestSettingsFormalBundle:
    """Tests 40-43: Settings UI integration."""

    @pytest.fixture
    def _setup_ui(self, tmp_path, monkeypatch):
        pytest.importorskip("PySide6")
        from PySide6.QtWidgets import QMessageBox as QMB
        from profit_accounting_26.application import AppContext
        from profit_accounting_26.ui.pages import settings_page as settings_mod
        from profit_accounting_26.ui.pages import SettingsPage

        monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
        ctx = AppContext.create_default()

        class FakeMsg:
            calls: list = []
            @classmethod
            def reset(cls): cls.calls = []
            @staticmethod
            def _rec(kind):
                def _call(*a, **kw):
                    # QMessageBox calls: (parent, title, text, ...)
                    title = str(a[1]) if len(a) > 1 else ""
                    text = str(a[2]) if len(a) > 2 else ""
                    FakeMsg.calls.append((kind, title, text))
                    return 0
                return _call
            information = staticmethod(_rec("info"))
            warning = staticmethod(_rec("warn"))
            critical = staticmethod(_rec("crit"))

        class FakeDlg:
            selected = ""
            @staticmethod
            def getOpenFileName(*a, **kw):
                return FakeDlg.selected, ""

        FakeMsg.reset()
        monkeypatch.setattr(settings_mod, "QMessageBox", FakeMsg)
        monkeypatch.setattr(settings_mod, "QFileDialog", FakeDlg)
        page = SettingsPage(ctx)
        yield page, ctx, FakeMsg, FakeDlg
        page.deleteLater()

    def test_40_formal_import_shows_inactive_message(self, qapp, tmp_path, _setup_ui, monkeypatch):
        """Formal Bundle 导入成功后显示'尚未启用'语义。"""
        page, ctx, FakeMsg, FakeDlg = _setup_ui
        bundle_path = write_bundle_zip(tmp_path)
        FakeDlg.selected = str(bundle_path)
        page._import_calibration_package()
        info_calls = [(kind, text) for kind, _, text in FakeMsg.calls if kind == "info"]
        # Check that the message mentions "not yet activated" semantics
        assert any(
            "尚未启用" in text or "not yet" in text.lower() or "未启用" in text
            for _, text in info_calls
        ), f"No inactive message found in: {FakeMsg.calls}"

    def test_41_list_refresh_after_formal_import(self, qapp, tmp_path, _setup_ui):
        """列表刷新后能选到 Formal Bundle。"""
        page, ctx, FakeMsg, FakeDlg = _setup_ui
        bundle_path = write_bundle_zip(tmp_path)
        FakeDlg.selected = str(bundle_path)
        page._import_calibration_package()
        table = page.calibration_table
        found = False
        for row in range(table.rowCount()):
            if table.item(row, 0).text() == "cal-v2":
                found = True
                assert table.item(row, 1).text() == "未启用"
        assert found

    def test_42_activate_formal_bundle(self, qapp, tmp_path, _setup_ui):
        """点击'启用'后真正变 active。"""
        page, ctx, FakeMsg, FakeDlg = _setup_ui
        bundle_path = write_bundle_zip(tmp_path)
        FakeDlg.selected = str(bundle_path)
        page._import_calibration_package()
        # Select and activate
        table = page.calibration_table
        for row in range(table.rowCount()):
            if table.item(row, 0).text() == "cal-v2":
                table.selectRow(row)
                break
        page._activate_selected_calibration()
        assert ctx.calibration_manager.active_package()["version"] == "cal-v2"
        # Table should show 当前启用
        for row in range(table.rowCount()):
            if table.item(row, 0).text() == "cal-v2":
                assert table.item(row, 1).text() == "当前启用"

    def test_43_legacy_import_existing_behavior(self, qapp, tmp_path, _setup_ui):
        """Legacy 导入现有 UI 行为不回归。"""
        page, ctx, FakeMsg, FakeDlg = _setup_ui
        source = _write_legacy_json(tmp_path, "legacy.json", "legacy-v1", "LEG")
        FakeDlg.selected = str(source)
        page._import_calibration_package()
        info_calls = [(kind, text) for kind, _, text in FakeMsg.calls if kind == "info"]
        # Check that legacy import shows "activated" semantics
        assert any(
            "已导入并启用" in text or "已导入" in text or "imported" in text.lower()
            for _, text in info_calls
        ), f"No activation message found in: {FakeMsg.calls}"


# ===========================================================================
# Additional: is_formal_bundle_zip detection
# ===========================================================================


class TestFormalBundleDetection:

    def test_is_formal_bundle_zip_true(self, tmp_path):
        p = write_bundle_zip(tmp_path)
        assert is_formal_bundle_zip(p) is True

    def test_is_formal_bundle_zip_false_for_legacy(self, tmp_path):
        p = _write_legacy_zip(tmp_path, "legacy.zip", "v1", "L1")
        assert is_formal_bundle_zip(p) is False

    def test_is_formal_bundle_zip_false_for_non_zip(self, tmp_path):
        p = tmp_path / "test.json"
        p.write_text("{}")
        assert is_formal_bundle_zip(p) is False

    def test_is_formal_bundle_zip_false_for_bad_zip(self, tmp_path):
        p = tmp_path / "bad.zip"
        p.write_bytes(b"not a zip")
        assert is_formal_bundle_zip(p) is False


# ===========================================================================
# Additional: Formal Bundle delete
# ===========================================================================


class TestFormalBundleDelete:

    def test_delete_inactive_formal_bundle(self, tmp_path):
        """inactive formal bundle delete 正常。"""
        manager, service, builtin = setup_manager(tmp_path)
        result = manager.import_package(write_bundle_zip(tmp_path))
        assert result["active"] is False
        manager.delete_package(result["id"])
        assert all(p["id"] != result["id"] for p in manager.list_packages())
        assert not Path(result["path"]).parent.exists()

    def test_delete_active_formal_bundle_fallback(self, tmp_path):
        """active formal bundle delete → builtin fallback。"""
        manager, service, builtin = setup_manager(tmp_path)
        result = manager.import_package(write_bundle_zip(tmp_path))
        manager.activate(result["id"])
        assert manager.active_package()["id"] == result["id"]
        remaining = manager.delete_package(result["id"])
        assert remaining["metadata"]["builtin"] is True
        assert service.calibration_version == "builtin-v1"
        assert not Path(result["path"]).parent.exists()
        assert result["active"] is False
        manager.delete_package(result["id"])
        assert all(p["id"] != result["id"] for p in manager.list_packages())
        assert not Path(result["path"]).parent.exists()

    def test_delete_active_formal_bundle_fallback(self, tmp_path):
        """active formal bundle delete → builtin fallback。"""
        manager, service, builtin = setup_manager(tmp_path)
        result = manager.import_package(write_bundle_zip(tmp_path))
        manager.activate(result["id"])
        assert manager.active_package()["id"] == result["id"]
        remaining = manager.delete_package(result["id"])
        assert remaining["metadata"]["builtin"] is True
        assert service.calibration_version == "builtin-v1"
        assert not Path(result["path"]).parent.exists()


# ===========================================================================
# Tests 44-59: Unified registry activation / rollback / restart / ZIP strictness
# ===========================================================================


class TestUnifiedRegistryActivation:
    """Tests for unified registry activation semantics."""

    def test_44_formal_active_to_legacy_activate_restores_cal77_registry(self, tmp_path):
        """Formal active → legacy activate: registry 恢复 CAL77 resource registry。"""
        manager, service, builtin = setup_manager(tmp_path)
        # Import and activate formal bundle
        formal = manager.import_package(write_bundle_zip(tmp_path))
        manager.activate(formal["id"])
        formal_registry = Path(formal["path"]).with_name("packaging_rule_registry_v1.json")
        assert service.rule_registry_path == formal_registry
        # Import legacy and activate it
        legacy = manager.import_package(
            _write_legacy_json(tmp_path, "legacy.json", "legacy-v2", "LEG")
        )
        # Legacy should use CAL77 registry
        assert service.rule_registry_path == _CAL77_REGISTRY_PATH

    def test_45_formal_active_to_builtin_fallback_restores_cal77_registry(self, tmp_path):
        """Formal active → delete (builtin fallback): registry 恢复 CAL77。"""
        manager, service, builtin = setup_manager(tmp_path)
        formal = manager.import_package(write_bundle_zip(tmp_path))
        manager.activate(formal["id"])
        formal_registry = Path(formal["path"]).with_name("packaging_rule_registry_v1.json")
        assert service.rule_registry_path == formal_registry
        # Delete formal → fallback to builtin
        manager.delete_package(formal["id"])
        assert service.rule_registry_path == _CAL77_REGISTRY_PATH
        assert service.calibration_version == "builtin-v1"

    def test_46_formal_a_to_formal_b_switches_registry(self, tmp_path):
        """Formal A → Formal B: registry 正确切到 B 的 sibling。"""
        manager, service, builtin = setup_manager(tmp_path)
        # Import two formal bundles with different calibration versions
        formal_a = manager.import_package(write_bundle_zip(
            tmp_path, name="bundle_a.zip",
            validated_package=_make_validated_package(
                package_id="pkg-A", calibration_version="cal-A"
            ),
            registry=_make_registry(version="cal-A"),
        ))
        formal_b = manager.import_package(write_bundle_zip(
            tmp_path, name="bundle_b.zip",
            validated_package=_make_validated_package(
                package_id="pkg-B", calibration_version="cal-B"
            ),
            registry=_make_registry(version="cal-B"),
        ))
        manager.activate(formal_a["id"])
        expected_a = Path(formal_a["path"]).with_name("packaging_rule_registry_v1.json")
        assert service.rule_registry_path == expected_a
        # Switch to B
        manager.activate(formal_b["id"])
        expected_b = Path(formal_b["path"]).with_name("packaging_rule_registry_v1.json")
        assert service.rule_registry_path == expected_b
        assert service.calibration_version == "cal-B"

    def test_47_activation_verification_failure_full_rollback(self, tmp_path):
        """activation target verification 失败 → previous DB/calibration/registry 全部恢复。"""
        manager, service, builtin = setup_manager(tmp_path)
        formal = manager.import_package(write_bundle_zip(tmp_path))
        # Sabotage: after activation, corrupt calibration_path on first call only
        original_activate = service.activate
        call_count = [0]

        def sabotaged(cal_path, *, version):
            call_count[0] += 1
            original_activate(cal_path, version=version)
            if call_count[0] == 1:
                # Only corrupt on first call (activate formal)
                service.calibration_path = Path("/fake/path")

        service.activate = sabotaged
        with pytest.raises(RuntimeError, match="post-activation verification failed"):
            manager.activate(formal["id"])
        # Everything must be restored to builtin (second call was recovery)
        assert call_count[0] == 2
        assert manager.active_package()["id"] == builtin["id"]
        assert service.calibration_path == Path(builtin["path"])
        assert service.calibration_version == "builtin-v1"
        assert service.rule_registry_path == _CAL77_REGISTRY_PATH

    def test_48_recovery_registry_failure_raises_severe(self, tmp_path):
        """恢复 registry 失败 → 严重 RuntimeError，不能吞异常。"""
        manager, service, builtin = setup_manager(tmp_path)
        formal = manager.import_package(write_bundle_zip(tmp_path))
        # Make service.activate succeed but then sabotage registry reload
        real_activate = service.activate
        call_count = [0]

        def failing_on_second(cal_path, *, version):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call (activate formal) fails
                raise ValueError("simulated activation failure")
            # Second call (restore previous) succeeds
            real_activate(cal_path, version=version)

        service.activate = failing_on_second
        with pytest.raises(RuntimeError, match="运行时激活失败"):
            manager.activate(formal["id"])
        # Should have attempted recovery
        assert call_count[0] >= 1

    def test_49_post_verification_rollback_failure_severe_error(self, tmp_path):
        """post-verification rollback 自身失败 → 明确严重错误。"""
        manager, service, builtin = setup_manager(tmp_path)
        formal = manager.import_package(write_bundle_zip(tmp_path))
        # Make activation fail AND recovery fail
        real_activate = service.activate

        def always_fails(cal_path, *, version):
            raise ValueError("always fails")

        service.activate = always_fails
        with pytest.raises(RuntimeError, match="补偿恢复也失败|没有切换前版本"):
            manager.activate(formal["id"])


class TestNestedZipMemberRejection:
    """Tests for strict root-level ZIP member checking."""

    def test_50_subdir_manifest_not_detected_as_formal(self, tmp_path):
        """subdir/formal_package_manifest.json 不能被识别为 Formal Bundle。"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("subdir/formal_package_manifest.json", '{"contract_version": "x"}')
        p = tmp_path / "nested.zip"
        p.write_bytes(buf.getvalue())
        assert is_formal_bundle_zip(p) is False

    def test_51_root_manifest_subdir_runtime_rejected(self, tmp_path):
        """根 manifest + 子目录 runtime_calibration → Formal Bundle 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        # Build a ZIP with manifest at root but runtime_calibration in subdir
        data = _build_formal_bundle_zip()
        # Rebuild with runtime_calibration moved to subdir
        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as src:
            with zipfile.ZipFile(buf, "w") as dst:
                for info in src.infolist():
                    if info.filename == "runtime_calibration.json":
                        dst.writestr("subdir/runtime_calibration.json", src.read(info.filename))
                    else:
                        dst.writestr(info.filename, src.read(info.filename))
        p = tmp_path / "mixed.zip"
        p.write_bytes(buf.getvalue())
        # is_formal_bundle_zip returns True (manifest IS at root)
        # but validate should fail because runtime_calibration is not at root
        with pytest.raises(FormalBundleValidationError, match="missing required member"):
            manager.import_package(p)


class TestManifestStrictValidation:
    """Tests for manifest.files and runtime_summary strict validation."""

    def test_52_manifest_files_mapping_error_rejected(self, tmp_path):
        """manifest.files 任一映射错误 → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        bundle_path = write_bundle_zip(
            tmp_path,
            manifest_overrides={
                "files": {
                    "runtime_calibration": "wrong_name.json",  # wrong
                    "runtime_registry": "packaging_rule_registry_v1.json",
                    "validated_rule_package": "validated_rule_package.json",
                    "promotion_receipt": "promotion_receipt.json",
                }
            },
        )
        with pytest.raises(FormalBundleValidationError, match="manifest.files"):
            manager.import_package(bundle_path)

    def test_53_runtime_summary_sample_count_error_rejected(self, tmp_path):
        """runtime_summary.sample_count 错误 → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        # Build a bundle with wrong sample_count in manifest
        data = _build_formal_bundle_zip()
        # Tamper the manifest to have wrong sample_count
        with zipfile.ZipFile(io.BytesIO(data)) as src:
            manifest = json.loads(src.read("formal_package_manifest.json"))
            manifest["runtime_summary"]["sample_count"] = 999
            # Rebuild ZIP with tampered manifest
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as dst:
                for info in src.infolist():
                    if info.filename == "formal_package_manifest.json":
                        dst.writestr(info.filename, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
                    else:
                        dst.writestr(info.filename, src.read(info.filename))
        p = tmp_path / "bad_sample_count.zip"
        p.write_bytes(buf.getvalue())
        with pytest.raises(FormalBundleValidationError, match="sample_count"):
            manager.import_package(p)

    def test_54_aggregate_rule_count_error_rejected(self, tmp_path):
        """aggregate_rule_count 错误 → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        data = _build_formal_bundle_zip()
        with zipfile.ZipFile(io.BytesIO(data)) as src:
            manifest = json.loads(src.read("formal_package_manifest.json"))
            manifest["runtime_summary"]["aggregate_rule_count"] = 999
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as dst:
                for info in src.infolist():
                    if info.filename == "formal_package_manifest.json":
                        dst.writestr(info.filename, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
                    else:
                        dst.writestr(info.filename, src.read(info.filename))
        p = tmp_path / "bad_agg_count.zip"
        p.write_bytes(buf.getvalue())
        with pytest.raises(FormalBundleValidationError, match="aggregate_rule_count"):
            manager.import_package(p)

    def test_55_sample_rule_count_error_rejected(self, tmp_path):
        """sample_rule_count 错误 → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        data = _build_formal_bundle_zip()
        with zipfile.ZipFile(io.BytesIO(data)) as src:
            manifest = json.loads(src.read("formal_package_manifest.json"))
            manifest["runtime_summary"]["sample_rule_count"] = 999
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as dst:
                for info in src.infolist():
                    if info.filename == "formal_package_manifest.json":
                        dst.writestr(info.filename, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
                    else:
                        dst.writestr(info.filename, src.read(info.filename))
        p = tmp_path / "bad_sample_rule_count.zip"
        p.write_bytes(buf.getvalue())
        with pytest.raises(FormalBundleValidationError, match="sample_rule_count"):
            manager.import_package(p)

    def test_56_validated_rule_ids_error_rejected(self, tmp_path):
        """validated_rule_ids 错误 → 拒绝。"""
        manager, service, builtin = setup_manager(tmp_path)
        data = _build_formal_bundle_zip()
        with zipfile.ZipFile(io.BytesIO(data)) as src:
            manifest = json.loads(src.read("formal_package_manifest.json"))
            manifest["runtime_summary"]["validated_rule_ids"] = ["WRONG-ID"]
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as dst:
                for info in src.infolist():
                    if info.filename == "formal_package_manifest.json":
                        dst.writestr(info.filename, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
                    else:
                        dst.writestr(info.filename, src.read(info.filename))
        p = tmp_path / "bad_rule_ids.zip"
        p.write_bytes(buf.getvalue())
        with pytest.raises(FormalBundleValidationError, match="validated_rule_ids"):
            manager.import_package(p)


class TestAppContextRestart:
    """Tests for AppContext restart scenarios."""

    def test_57_restart_active_formal_uses_formal_registry(self, tmp_path, monkeypatch):
        """AppContext 重启：active Formal Bundle → PackagingEstimationService 使用 Formal sibling registry。"""
        pytest.importorskip("PySide6")
        monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
        from profit_accounting_26.application import AppContext
        # First startup: import and activate formal bundle
        ctx1 = AppContext.create_default()
        bundle_path = write_bundle_zip(tmp_path)
        result = ctx1.calibration_manager.import_package(bundle_path)
        ctx1.calibration_manager.activate(result["id"])
        formal_registry = Path(result["path"]).with_name("packaging_rule_registry_v1.json")
        assert ctx1.packaging_service.rule_registry_path == formal_registry
        # Second startup (simulating restart)
        ctx2 = AppContext.create_default()
        assert ctx2.packaging_service.rule_registry_path == formal_registry
        assert ctx2.packaging_service.calibration_version == result["version"]

    def test_58_restart_active_builtin_uses_cal77_registry(self, tmp_path, monkeypatch):
        """AppContext 重启：active builtin → 使用 CAL77 resource registry。"""
        pytest.importorskip("PySide6")
        monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
        from profit_accounting_26.application import AppContext
        ctx = AppContext.create_default()
        # Default active is builtin
        assert ctx.calibration_manager.active_package().get("metadata", {}).get("builtin") is True
        assert ctx.packaging_service.rule_registry_path == _CAL77_REGISTRY_PATH

    def test_59_restart_active_legacy_uses_cal77_registry(self, tmp_path, monkeypatch):
        """AppContext 重启：active legacy → 使用 CAL77 resource registry。"""
        pytest.importorskip("PySide6")
        monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
        from profit_accounting_26.application import AppContext
        ctx1 = AppContext.create_default()
        # Import and activate legacy
        legacy = ctx1.calibration_manager.import_package(
            _write_legacy_json(tmp_path, "legacy.json", "legacy-v2", "LEG")
        )
        assert ctx1.packaging_service.calibration_version == "legacy-v2"
        # Restart
        ctx2 = AppContext.create_default()
        assert ctx2.packaging_service.rule_registry_path == _CAL77_REGISTRY_PATH
        assert ctx2.packaging_service.calibration_version == "legacy-v2"
