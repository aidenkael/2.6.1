import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from profit_accounting_26.ui.app import NAV_ITEMS, build_window


def test_six_navigation_items_are_visible_in_fixed_order(qapp, tmp_path, monkeypatch):
    # qapp 来自 tests/conftest.py 会话级 fixture；build_window() 复用
    # QApplication.instance()，整个测试会话只存在一个 QApplication。
    # 隔离数据目录：create_default 会初始化包含 images 表的新库，避免依赖真实用户数据目录。
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    assert NAV_ITEMS == [
        "以图搜图",
        "新商品测算",
        "历史记录管理",
        "数据导入导出",
        "模型校准反馈",
        "设置",
    ]
    app, window = build_window()
    # 标题来自冻结 main_window.ui 的 windowTitle（运行时为 2.6.1），不硬编码旧版本
    assert window.windowTitle() == "微智能利润管理软件 2.6.1"
    window.close()
    app.processEvents()
