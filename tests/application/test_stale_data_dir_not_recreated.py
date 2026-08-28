"""数据目录生命周期回归：location.json 是唯一权威，废弃目录不得复活。

覆盖任务契约：
A. 切换数据目录后，location.json 是后续启动（UU护航 / UU测算 共享）的唯一权威；
B. 旧数据目录被删除后，后续正常启动/激活不得重建它；
C. 陈旧 AppContext / SettingsService（切换前创建）在目录被删除后不得静默重建它；
E. 不全局吞掉文件系统错误：拒绝时抛出明确的 StaleDataDirectoryError。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from profit_accounting_26.application import AppContext, SettingsService
from profit_accounting_26.application.api_profile_store import (
    ApiProfile,
    ApiProfileStore,
)
from profit_accounting_26.application.diagnostic_logger import DiagnosticLogger
from profit_accounting_26.shared import (
    ApplicationPaths,
    StaleDataDirectoryError,
    activate_data_dir_lifecycle,
    deactivate_data_dir_lifecycle,
    is_authoritative_data_dir,
)
from profit_accounting_26.storage import SQLiteStore
from profit_accounting_26.storage.image_store import ImageStore


@pytest.fixture
def location_json(tmp_path, monkeypatch):
    """location.json 重定向到测试临时目录（与 test_data_dir_unify 相同模式）。"""
    config = tmp_path / "home" / "location.json"
    monkeypatch.setattr(
        ApplicationPaths,
        "location_config_path",
        classmethod(lambda _cls: config),
    )
    return config


@pytest.fixture
def production_lifecycle(location_json):
    """模拟正式 UI 启动激活的生命周期守卫；测试结束必须复位。"""
    activate_data_dir_lifecycle()
    yield
    deactivate_data_dir_lifecycle()


def _populate(data_dir: Path) -> None:
    paths = ApplicationPaths.from_data_dir(data_dir)
    paths.ensure()
    service = SettingsService(paths.settings_path)
    data = service.load()
    data["exchange_rate_usd_to_rmb"] = 7.35
    service.save(data)


def test_switch_authority_moves_to_new_dir_and_launch_uses_it(tmp_path, location_json, production_lifecycle):
    old_dir = tmp_path / "old_data"
    new_dir = tmp_path / "new_data"
    _populate(old_dir)

    # 用户在 UU护航 设置页切换数据目录：只写 location.json
    ApplicationPaths.save_data_dir(new_dir)

    # A：后续启动解析以 location.json 为唯一权威
    resolved = ApplicationPaths.ui_default()
    assert resolved is not None
    assert resolved.data_dir.resolve() == new_dir.resolve()
    assert is_authoritative_data_dir(old_dir) is False
    assert is_authoritative_data_dir(new_dir) is True


def test_deleted_old_dir_is_not_recreated_by_next_launch(tmp_path, location_json, production_lifecycle):
    old_dir = tmp_path / "old_data"
    new_dir = tmp_path / "new_data"
    _populate(old_dir)
    ApplicationPaths.save_data_dir(new_dir)
    shutil.rmtree(old_dir)

    # B：后续正常启动只解析/初始化新目录，不复活旧目录
    resolved = ApplicationPaths.ui_default()
    context = AppContext.create_default(paths=resolved)

    assert old_dir.exists() is False
    assert new_dir.is_dir()
    assert (new_dir / "settings.json").is_file()
    # 新目录没有旧数据（不复制/合并不属于既有契约）
    assert context.settings_service.load()["exchange_rate_usd_to_rmb"] == pytest.approx(7.2)


def test_stale_settings_service_cannot_recreate_deleted_dir(tmp_path, location_json, production_lifecycle):
    old_dir = tmp_path / "old_data"
    new_dir = tmp_path / "new_data"
    _populate(old_dir)

    # 切换前创建的陈旧服务（等价于仍在运行的旧会话 / UU测算 启动时持有的 AppContext）
    stale_settings = SettingsService(ApplicationPaths.from_data_dir(old_dir).settings_path)

    ApplicationPaths.save_data_dir(new_dir)
    shutil.rmtree(old_dir)

    # C：load() 降级为内存默认值，绝不静默重建目录/文件
    loaded = stale_settings.load()
    assert loaded["exchange_rate_usd_to_rmb"] == pytest.approx(7.2)
    assert not old_dir.exists()

    # E：save() 明确拒绝，不吞掉错误
    with pytest.raises(StaleDataDirectoryError):
        stale_settings.save({"exchange_rate_usd_to_rmb": 7.5})
    assert not old_dir.exists()


def test_stale_paths_store_and_stores_reject_deleted_dir(tmp_path, location_json, production_lifecycle):
    old_dir = tmp_path / "old_data"
    new_dir = tmp_path / "new_data"
    _populate(old_dir)

    stale_paths = ApplicationPaths.from_data_dir(old_dir)
    stale_store = SQLiteStore(stale_paths.database_path)
    stale_images = ImageStore(stale_store, old_dir)
    stale_api = ApiProfileStore(old_dir)
    stale_logger = DiagnosticLogger(old_dir, {"log_retention_days": 30})

    ApplicationPaths.save_data_dir(new_dir)
    shutil.rmtree(old_dir)

    with pytest.raises(StaleDataDirectoryError):
        stale_paths.ensure()
    with pytest.raises(StaleDataDirectoryError):
        stale_store.list_records(limit=1)
    with pytest.raises(StaleDataDirectoryError):
        stale_images.add_bytes(b"image-bytes", suffix=".png")
    with pytest.raises(StaleDataDirectoryError):
        stale_api.save_profile(
            ApiProfile.create(
                display_name="DeepSeek",
                provider="DeepSeek",
                api_url="https://api.example.com",
                model_name="m",
            ),
            "key",
        )
    # 诊断日志是 best-effort：不抛错、不重建，只静默不落盘
    stale_logger.begin_operation("check")
    assert not old_dir.exists()

    assert not old_dir.exists()


def test_existing_old_dir_stays_writable_until_restart(tmp_path, location_json, production_lifecycle):
    """会话延续契约：旧目录仍存在时，陈旧会话照常可写（目录早已存在，谈不上复活）。"""
    old_dir = tmp_path / "old_data"
    new_dir = tmp_path / "new_data"
    _populate(old_dir)
    stale_settings = SettingsService(ApplicationPaths.from_data_dir(old_dir).settings_path)

    ApplicationPaths.save_data_dir(new_dir)

    data = stale_settings.load()
    data["exchange_rate_usd_to_rmb"] = 7.4
    stale_settings.save(data)

    assert (old_dir / "settings.json").is_file()
    assert SettingsService(old_dir / "settings.json").load()["exchange_rate_usd_to_rmb"] == pytest.approx(7.4)


def test_authoritative_dir_deleted_by_user_is_recreated_on_relaunch(tmp_path, location_json, production_lifecycle):
    """用户删除的是当前权威目录时，重新启动照常全新初始化（不是废弃目录）。"""
    data_dir = tmp_path / "current_data"
    _populate(data_dir)
    ApplicationPaths.save_data_dir(data_dir)
    shutil.rmtree(data_dir)

    resolved = ApplicationPaths.ui_default()
    assert resolved is not None
    resolved.ensure()
    assert data_dir.is_dir()


def test_lifecycle_inactive_by_default_injected_contexts(tmp_path, location_json):
    """测试/工具显式注入路径不受守卫影响（生命周期未激活时不设限）。"""
    plain = tmp_path / "plain_data"
    plain.mkdir()
    assert is_authoritative_data_dir(plain) is True

    ApplicationPaths.save_data_dir(tmp_path / "elsewhere")
    stale_settings = SettingsService(plain / "settings.json")
    # 目录已存在 → 无论权威性都放行
    stale_settings.save({"exchange_rate_usd_to_rmb": 7.2})
    assert (plain / "settings.json").is_file()


def test_bootstrap_injected_data_dir_does_not_activate_lifecycle(qapp, tmp_path, location_json):
    """bootstrap 显式注入分支（测试/工具）不激活生命周期。"""
    from profit_accounting_26.shared import deactivate_data_dir_lifecycle
    from profit_accounting_26.ui.bootstrap import bootstrap_application

    deactivate_data_dir_lifecycle()
    try:
        target = tmp_path / "injected"
        target.mkdir()
        _app, paths = bootstrap_application(data_dir=target, app_name="测试")
        assert paths is not None
        assert is_authoritative_data_dir(target) is True  # 未激活 → 不设限
    finally:
        deactivate_data_dir_lifecycle()


def test_bootstrap_production_path_activates_lifecycle(qapp, tmp_path, location_json):
    """bootstrap 正式启动分支激活生命周期，location.json 权威生效。"""
    from profit_accounting_26.shared import deactivate_data_dir_lifecycle
    from profit_accounting_26.ui.bootstrap import bootstrap_application

    deactivate_data_dir_lifecycle()
    try:
        data_dir = tmp_path / "prod_data"
        data_dir.mkdir()
        ApplicationPaths.save_data_dir(data_dir)
        _app, paths = bootstrap_application(app_name="测试")
        assert paths is not None
        assert paths.data_dir.resolve() == data_dir.resolve()
        other = tmp_path / "not_authoritative"
        other.mkdir()
        assert is_authoritative_data_dir(data_dir) is True
        assert is_authoritative_data_dir(other) is False
    finally:
        deactivate_data_dir_lifecycle()
