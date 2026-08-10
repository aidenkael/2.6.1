"""阶段 1：切换 data_dir 迁移配置体系，不复制历史记录与图片。"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

from profit_accounting_26.application import AppContext, SettingsService
from profit_accounting_26.application.api_profile_store import (
    ApiProfile,
    ApiProfileStore,
    VISUAL_AI,
)
from profit_accounting_26.application.calibration_manager import CalibrationManager
from profit_accounting_26.application.settings_migration import sync_user_config
from profit_accounting_26.application.settings_service import DEFAULT_SUBSIDY_RULE
from profit_accounting_26.shared import ApplicationPaths
from profit_accounting_26.storage import SQLiteStore


def _make_paths(root: Path) -> ApplicationPaths:
    return ApplicationPaths(
        data_dir=root,
        database_path=root / "profit_accounting_26.sqlite3",
        settings_path=root / "settings.json",
        images_dir=root / "images",
        exports_dir=root / "exports",
        calibration_packages_dir=root / "calibration_packages",
    )


def _samples(sample_id: str) -> list[dict]:
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


def _populate_source(root: Path) -> dict:
    paths = _make_paths(root)
    paths.ensure()
    store = SQLiteStore(paths.database_path)
    store.initialize()

    service = SettingsService(paths.settings_path, defaults_path=None)
    settings = service.load()
    settings["exchange_rate_usd_to_rmb"] = 7.35
    forwarder = SettingsService.new_forwarder("深圳货代", 88, 7, 8000)
    settings["forwarders"] = [asdict(forwarder)]
    settings["selected_forwarder_id"] = forwarder.id
    custom = deepcopy(DEFAULT_SUBSIDY_RULE)
    custom.update({"id": "custom_rule", "name": "自定义规则"})
    settings["profit_rules"].append(custom)
    service.save(settings)

    api = ApiProfileStore(root)
    profile = ApiProfile.create(
        display_name="DeepSeek",
        provider="DeepSeek",
        api_url="https://api.deepseek.com/chat/completions",
        model_name="deepseek-vl",
    )
    api.save_profile(profile, "secret-key-123")
    api.bind(VISUAL_AI, profile.profile_id)

    manager = CalibrationManager(store, paths)
    builtin = root.parent / "builtin.json"
    builtin.write_text(json.dumps(_samples("BASE")), encoding="utf-8")
    manager.ensure_builtin(builtin, version="builtin-v1")
    custom_pkg = root / "custom_pkg.json"
    custom_pkg.write_text(
        json.dumps({"version": "custom-v2", "samples": _samples("CUSTOM")}),
        encoding="utf-8",
    )
    manager.import_package(custom_pkg)

    return {
        "paths": paths,
        "store": store,
        "profile_id": profile.profile_id,
    }


def test_switch_data_dir_migrates_all_user_config(tmp_path: Path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    ctx = _populate_source(source)
    target_store = SQLiteStore(target / "profit_accounting_26.sqlite3")

    summary = sync_user_config(
        ctx["paths"].data_dir,
        target,
        source_store=ctx["store"],
        target_store=target_store,
    )

    assert summary.copied_files == ["settings.json", "api_profiles.json", "api_keys.local.json"]
    assert summary.calibration_registry_migrated is True

    # 设置：汇率 / 货代 / 默认+自定义利润规则
    migrated = SettingsService(target / "settings.json").load()
    assert migrated["exchange_rate_usd_to_rmb"] == 7.35
    assert [item["name"] for item in migrated["forwarders"]] == ["深圳货代"]
    rule_ids = [rule["id"] for rule in migrated["profit_rules"]]
    assert "under_29_subsidy" in rule_ids
    assert "custom_rule" in rule_ids

    # API profile / key / binding
    migrated_api = ApiProfileStore(target)
    public = migrated_api.load_public()
    assert [item["profile_id"] for item in public["profiles"]] == [ctx["profile_id"]]
    assert migrated_api.load_keys()[ctx["profile_id"]] == "secret-key-123"
    assert migrated_api.bound_profile(VISUAL_AI)[0].profile_id == ctx["profile_id"]

    # 校准包文件 + 注册表：版本齐全、启用版本保持、路径指向新目录
    target_store.initialize()
    packages = target_store.list_calibration_packages()
    assert {item["version"] for item in packages} == {"builtin-v1", "custom-v2"}
    active = target_store.get_active_calibration()
    assert active["version"] == "custom-v2"
    assert Path(active["path"]).is_file()
    assert str(Path(active["path"]).resolve()).startswith(str(target.resolve()))


def test_switch_does_not_copy_history_or_images(tmp_path: Path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    paths = _make_paths(source)
    paths.ensure()
    store = SQLiteStore(paths.database_path)
    store.initialize()
    store.save_new_record({"product_name": "旧历史记录"})
    (paths.images_dir / "old.png").write_bytes(b"image-bytes")
    SettingsService(paths.settings_path, defaults_path=None).load()

    target_store = SQLiteStore(target / "profit_accounting_26.sqlite3")
    sync_user_config(source, target, source_store=store, target_store=target_store)

    target_store.initialize()
    assert target_store.list_records(limit=10) == []
    assert not (target / "images").exists() or not list((target / "images").glob("*"))


def test_switch_does_not_merge_into_existing_target_database(tmp_path: Path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    ctx = _populate_source(source)
    target_store = SQLiteStore(target / "profit_accounting_26.sqlite3")
    target_store.initialize()
    target_store.save_new_record({"product_name": "目标目录已有历史"})

    summary = sync_user_config(
        ctx["paths"].data_dir,
        target,
        source_store=ctx["store"],
        target_store=target_store,
    )

    assert summary.calibration_registry_skipped_reason is not None
    assert len(target_store.list_calibration_packages()) == 0
    assert len(target_store.list_records(limit=10)) == 1


def test_new_context_after_switch_reads_only_new_data_dir(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    target = tmp_path / "target"
    ctx = _populate_source(source)
    target_store = SQLiteStore(target / "profit_accounting_26.sqlite3")
    sync_user_config(
        ctx["paths"].data_dir,
        target,
        source_store=ctx["store"],
        target_store=target_store,
    )

    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(target))
    context = AppContext.create_default()

    settings = context.settings_service.load()
    assert settings["exchange_rate_usd_to_rmb"] == 7.35
    assert [item["name"] for item in settings["forwarders"]] == ["深圳货代"]
    assert context.api_profile_store.bound_profile(VISUAL_AI) is not None
    # 新目录没有历史记录，且不会偷偷读取旧目录
    assert context.store.list_records(limit=10) == []
    assert context.calibration_manager.active_package()["version"] == "custom-v2"
