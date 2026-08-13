from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from profit_accounting_26.application import calibration_baseline
from profit_accounting_26.application.calibration_baseline import (
    CURRENT_BASELINE_RESOURCE,
    CURRENT_BASELINE_VERSION,
    CURRENT_REGISTRY_RESOURCE,
    CurrentBaselineCalibrationManager,
    purge_obsolete_bundled_calibration,
)
from profit_accounting_26.application.formal_bundle_importer import FormalBundleValidationError
from profit_accounting_26.shared import ApplicationPaths, resource_path
from profit_accounting_26.storage import SQLiteStore


def _paths(root: Path) -> ApplicationPaths:
    return ApplicationPaths(
        data_dir=root,
        database_path=root / "app.sqlite3",
        settings_path=root / "settings.json",
        images_dir=root / "images",
        exports_dir=root / "exports",
        calibration_packages_dir=root / "calibration_packages",
    )


def test_bundled_baseline_contains_no_runtime_sample_ids():
    payload = json.loads(resource_path(CURRENT_BASELINE_RESOURCE).read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert payload
    assert all("sample_id" not in item for item in payload)


def test_bundled_registry_contains_zero_rules():
    registry = json.loads(resource_path(CURRENT_REGISTRY_RESOURCE).read_text(encoding="utf-8"))
    assert registry["version"] == "runtime-safety-empty-v1"
    assert registry["aggregate_rules"] == []
    assert registry["sample_rules"] == []


def test_local_migration_removes_obsolete_builtin_copy_once(tmp_path):
    paths = _paths(tmp_path)
    paths.ensure()
    store = SQLiteStore(paths.database_path)
    store.initialize()

    old_dir = paths.calibration_packages_dir / "builtin"
    old_dir.mkdir(parents=True)
    old_file = old_dir / "calibration.json"
    old_file.write_text('[{"sample_id":"OLD"}]', encoding="utf-8")
    store.register_calibration_package(
        version="local-calibration-v3-77-samples-rules-v1",
        path=str(old_file),
        metadata={"builtin": True},
        activate=True,
    )

    purge_obsolete_bundled_calibration(store, paths)

    assert store.list_calibration_packages() == []
    assert not old_dir.exists()

    # Idempotent: the second launch does not need another migration.
    purge_obsolete_bundled_calibration(store, paths)
    assert store.list_calibration_packages() == []


def test_local_migration_removes_manually_imported_retired_version(tmp_path):
    paths = _paths(tmp_path)
    paths.ensure()
    store = SQLiteStore(paths.database_path)
    store.initialize()

    old_dir = paths.calibration_packages_dir / "manual-old"
    old_dir.mkdir(parents=True)
    old_file = old_dir / "runtime_calibration.json"
    old_file.write_text('[{"sample_id":"OLD-MANUAL"}]', encoding="utf-8")
    store.register_calibration_package(
        version="local-calibration-v3-77-samples-rules-v1",
        path=str(old_file),
        metadata={"original_name": "old-copy.json"},
        activate=True,
    )

    purge_obsolete_bundled_calibration(store, paths)

    assert store.list_calibration_packages() == []
    assert not old_dir.exists()


def test_current_builtin_can_be_established_after_cleanup(tmp_path):
    paths = _paths(tmp_path)
    paths.ensure()
    store = SQLiteStore(paths.database_path)
    store.initialize()
    manager = CurrentBaselineCalibrationManager(store, paths)

    active = manager.ensure_builtin(
        resource_path(CURRENT_BASELINE_RESOURCE),
        version=CURRENT_BASELINE_VERSION,
    )

    assert active["active"] is True
    assert active["version"] == CURRENT_BASELINE_VERSION
    assert active["metadata"]["builtin"] is True
    assert active["metadata"]["sample_count"] == 0


def test_formal_bundle_from_retired_bundled_baseline_is_rejected(monkeypatch, tmp_path):
    paths = _paths(tmp_path)
    paths.ensure()
    store = SQLiteStore(paths.database_path)
    store.initialize()
    manager = CurrentBaselineCalibrationManager(store, paths)

    monkeypatch.setattr(
        calibration_baseline,
        "validate_formal_bundle_zip",
        lambda _source: SimpleNamespace(
            manifest={
                "baseline_calibration_version": "local-calibration-v3-77-samples-rules-v1"
            }
        ),
    )

    with pytest.raises(FormalBundleValidationError, match="已退役的旧校准基线"):
        manager._import_formal_bundle(
            tmp_path / "old.zip",
            tmp_path / "package",
            "0" * 64,
        )
