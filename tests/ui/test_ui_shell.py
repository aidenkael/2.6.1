import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from profit_accounting_26.ui.app import NAV_ITEMS, build_window


def test_six_navigation_items_are_visible_in_fixed_order():
    assert NAV_ITEMS == [
        "以图搜图",
        "新商品测算",
        "历史记录管理",
        "数据导入导出",
        "模型校准反馈",
        "设置",
    ]
    app, window = build_window()
    assert window.windowTitle().endswith("2.6")
    window.close()
    app.processEvents()
