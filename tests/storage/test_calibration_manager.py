from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

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


def test_import_json_activates_runtime_service_and_activate_restores_builtin(tmp_path: Path):
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

    # Stage 4：rollback 已删除，改用任意版本启用切回 builtin
    restored = manager.activate(active["id"])
    assert restored is not None
    assert restored["version"] == "builtin-v1"
    assert service.calibration_version == "builtin-v1"
    assert service.samples[0]["sample_id"] == "BASE"


def make_package_file(tmp_path: Path, name: str, version: str, sample_id: str) -> Path:
    source = tmp_path / name
    source.write_text(
        json.dumps({"version": version, "samples": samples(sample_id)}),
        encoding="utf-8",
    )
    return source


def setup_manager(tmp_path: Path) -> tuple[CalibrationManager, PackagingEstimationService, Path]:
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
    return manager, service, builtin


def test_activate_switches_any_registered_version_and_runtime_service(tmp_path: Path):
    manager, service, _ = setup_manager(tmp_path)
    custom = manager.import_package(make_package_file(tmp_path, "custom.json", "custom-v2", "CUSTOM"))
    other = manager.import_package(make_package_file(tmp_path, "other.json", "other-v3", "OTHER"))
    assert manager.active_package()["id"] == other["id"]

    # 任意启用：切回 custom
    activated = manager.activate(custom["id"])
    assert activated["id"] == custom["id"]
    assert service.calibration_version == "custom-v2"
    assert service.samples[0]["sample_id"] == "CUSTOM"
    # 再启用 builtin
    builtin = next(item for item in manager.list_packages() if item["metadata"].get("builtin"))
    activated = manager.activate(builtin["id"])
    assert activated["version"] == "builtin-v1"
    assert service.calibration_version == "builtin-v1"
    assert service.samples[0]["sample_id"] == "BASE"


def test_activate_unknown_package_fails(tmp_path: Path):
    manager, _service, _ = setup_manager(tmp_path)
    with pytest.raises(KeyError):
        manager.activate("missing-package-id")


def test_delete_non_active_imported_package(tmp_path: Path):
    manager, service, _ = setup_manager(tmp_path)
    first = manager.import_package(make_package_file(tmp_path, "first.json", "first-v1", "FIRST"))
    second = manager.import_package(make_package_file(tmp_path, "second.json", "second-v1", "SECOND"))
    assert manager.active_package()["id"] == second["id"]

    remaining = manager.delete_package(first["id"])
    assert remaining["id"] == second["id"]
    assert all(item["id"] != first["id"] for item in manager.list_packages())
    assert not Path(first["path"]).parent.exists()
    # 运行时服务不受影响
    assert service.calibration_version == "second-v1"


def test_delete_active_package_falls_back_to_builtin_then_removes(tmp_path: Path):
    manager, service, _ = setup_manager(tmp_path)
    custom = manager.import_package(make_package_file(tmp_path, "custom.json", "custom-v2", "CUSTOM"))
    assert manager.active_package()["id"] == custom["id"]

    remaining = manager.delete_package(custom["id"])
    assert remaining["metadata"]["builtin"] is True
    assert remaining["version"] == "builtin-v1"
    assert all(item["id"] != custom["id"] for item in manager.list_packages())
    assert not Path(custom["path"]).parent.exists()
    assert service.calibration_version == "builtin-v1"
    assert service.samples[0]["sample_id"] == "BASE"


def test_delete_active_package_keeps_original_when_fallback_fails(tmp_path: Path):
    manager, service, builtin_source = setup_manager(tmp_path)
    custom = manager.import_package(make_package_file(tmp_path, "custom.json", "custom-v2", "CUSTOM"))
    builtin = next(item for item in manager.list_packages() if item["metadata"].get("builtin"))
    # 破坏 builtin：删除注册文件与原始源，fallback 无法恢复
    Path(builtin["path"]).unlink()
    builtin_source.unlink()

    with pytest.raises(RuntimeError):
        manager.delete_package(custom["id"])
    # 原 active 未被删除，运行时服务未切换
    active = manager.active_package()
    assert active["id"] == custom["id"]
    assert any(item["id"] == custom["id"] for item in manager.list_packages())
    assert Path(custom["path"]).is_file()
    assert service.calibration_version == "custom-v2"


def test_builtin_package_cannot_be_deleted(tmp_path: Path):
    manager, _service, _ = setup_manager(tmp_path)
    builtin = next(item for item in manager.list_packages() if item["metadata"].get("builtin"))
    with pytest.raises(ValueError):
        manager.delete_package(builtin["id"])
    assert manager.active_package()["id"] == builtin["id"]


def test_active_still_valid_after_recreating_manager(tmp_path: Path):
    manager, _service, _ = setup_manager(tmp_path)
    custom = manager.import_package(make_package_file(tmp_path, "custom.json", "custom-v2", "CUSTOM"))
    manager.delete_package(custom["id"])

    # 模拟重启：重新创建 Manager，读取同一数据库
    fresh = CalibrationManager(manager.store, manager.paths)
    active = fresh.active_package()
    assert active is not None
    assert active["version"] == "builtin-v1"
    assert Path(active["path"]).is_file()


def test_delete_unknown_package_fails(tmp_path: Path):
    manager, _service, _ = setup_manager(tmp_path)
    with pytest.raises(KeyError):
        manager.delete_package("missing-package-id")


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
