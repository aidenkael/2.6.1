from __future__ import annotations

import json
import zipfile
from pathlib import Path

from profit_accounting_26.application import CalibrationManager, PackagingEstimationService
from profit_accounting_26.shared import ApplicationPaths
from profit_accounting_26.storage import SQLiteStore


def make_paths(tmp_path: Path) -> ApplicationPaths:
    return ApplicationPaths(
        data_dir=tmp_path,
        database_path=tmp_path / "app.sqlite3",
        settings_path=tmp_path / "settings.json",
        images_dir=tmp_path / "images",
        exports_dir=tmp_path / "exports",
        calibration_packages_dir=tmp_path / "calibration_packages",
    )


def samples(sample_id: str) -> list[dict]:
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


def test_import_json_activates_runtime_service_and_rollback_restores_builtin(tmp_path: Path):
    paths = make_paths(tmp_path / "data")
    paths.ensure()
    store = SQLiteStore(paths.database_path)
    store.initialize()
    builtin = tmp_path / "builtin.json"
    builtin.write_text(json.dumps(samples("BASE")), encoding="utf-8")
    manager = CalibrationManager(store, paths)
    active = manager.ensure_builtin(builtin, version="builtin-v1")
    service = PackagingEstimationService(active["path"], calibration_version=active["version"])
    manager.bind_service(service)

    imported = tmp_path / "custom.json"
    imported.write_text(
        json.dumps({"version": "custom-v2", "samples": samples("CUSTOM")}),
        encoding="utf-8",
    )
    result = manager.import_package(imported)
    assert result["version"] == "custom-v2"
    assert service.calibration_version == "custom-v2"
    assert service.samples[0]["sample_id"] == "CUSTOM"

    restored = manager.rollback()
    assert restored is not None
    assert restored["version"] == "builtin-v1"
    assert service.calibration_version == "builtin-v1"
    assert service.samples[0]["sample_id"] == "BASE"


def test_import_zip_selects_valid_calibration_json(tmp_path: Path):
    paths = make_paths(tmp_path / "data")
    paths.ensure()
    store = SQLiteStore(paths.database_path)
    store.initialize()
    builtin = tmp_path / "builtin.json"
    builtin.write_text(json.dumps(samples("BASE")), encoding="utf-8")
    manager = CalibrationManager(store, paths)
    active = manager.ensure_builtin(builtin, version="builtin-v1")
    service = PackagingEstimationService(active["path"], calibration_version=active["version"])
    manager.bind_service(service)

    package = tmp_path / "package.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("notes.json", json.dumps({"description": "not samples"}))
        archive.writestr(
            "data/calibration_v3.json",
            json.dumps({"calibration_version": "zip-v3", "samples": samples("ZIP")}),
        )
    result = manager.import_package(package)
    assert result["version"] == "zip-v3"
    assert result["metadata"]["source_member"] == "data/calibration_v3.json"
    assert service.samples[0]["sample_id"] == "ZIP"
