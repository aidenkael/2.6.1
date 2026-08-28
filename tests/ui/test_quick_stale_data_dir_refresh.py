"""UU测算 WindowActivate → _refresh_settings_from_disk 的废弃目录回归。

场景：UU测算 在旧数据目录上启动（持有陈旧 AppContext）；用户随后在
UU护航 切换数据目录并删除旧目录；回到 UU测算 窗口触发设置刷新时，
陈旧 SettingsService.load() 不得重建废弃目录（否则 Quick 会复活 old_dir）。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from profit_accounting_26.application import AppContext
from profit_accounting_26.shared import (
    ApplicationPaths,
    activate_data_dir_lifecycle,
    deactivate_data_dir_lifecycle,
)
from profit_accounting_26.ui.quick_calculator_window import QuickCalculatorWindow


@pytest.fixture
def location_json(tmp_path, monkeypatch):
    config = tmp_path / "home" / "location.json"
    monkeypatch.setattr(
        ApplicationPaths,
        "location_config_path",
        classmethod(lambda _cls: config),
    )
    return config


@pytest.fixture
def production_lifecycle(location_json):
    activate_data_dir_lifecycle()
    yield
    deactivate_data_dir_lifecycle()


def test_quick_refresh_keeps_quick_alive_without_reviving_old_dir(
    qapp, tmp_path, location_json, production_lifecycle
):
    old_dir = tmp_path / "old_data"
    new_dir = tmp_path / "new_data"

    # UU测算 在旧目录上启动（与主软件共享 location.json 解析结果）
    paths_old = ApplicationPaths.from_data_dir(old_dir)
    paths_old.ensure()
    context = AppContext.create_default(paths=paths_old)
    window = QuickCalculatorWindow(context)
    try:
        # 用户随后在 UU护航 切换目录并删除旧目录
        ApplicationPaths.save_data_dir(new_dir)
        shutil.rmtree(old_dir)

        # 窗口激活 → 设置刷新：不得抛错、不得重建旧目录
        window._refresh_settings_from_disk()
        qapp.processEvents()

        assert not old_dir.exists()
        # 窗口仍可用：默认汇率 7.2 生效，利润区 Binder 正常
        assert window.profit_binder is not None
        assert window.profit_binder._exchange_rate == pytest.approx(7.2)

        # 后续启动解析到新目录（UU测算 与 UU护航 共享同一权威）
        resolved = ApplicationPaths.ui_default()
        assert resolved is not None
        assert resolved.data_dir.resolve() == new_dir.resolve()
        assert not old_dir.exists()
    finally:
        window.deleteLater()
        qapp.processEvents()
