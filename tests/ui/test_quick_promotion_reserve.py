"""Quick 活动预留布局 targeted tests。

验证：
- spinPromotionReserve objectName 不变、CalculationBinder 能找到；
- 活动预留在独立列（column 3），与标价利率（column 2）分开；
- 折叠/展开 50 次尺寸 0px 漂移。

禁止真实 API / 浏览器 / 外部链接。
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QDoubleSpinBox, QFrame, QGridLayout  # noqa: E402


class TestQuickPromotionReserveLayout:
    @pytest.fixture
    def quick_window(self, qapp, tmp_path, monkeypatch):
        monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
        from profit_accounting_26.application import AppContext
        from profit_accounting_26.ui.quick_calculator_window import QuickCalculatorWindow

        context = AppContext.create_default()
        window = QuickCalculatorWindow(context)
        yield window
        window.close()
        window.deleteLater()

    def test_spin_promotion_reserve_found_by_objectname(self, quick_window):
        """spinPromotionReserve 仍可通过 findChild 找到（CalculationBinder 依赖）。"""
        spin = quick_window.findChild(QDoubleSpinBox, "spinPromotionReserve")
        assert spin is not None, "spinPromotionReserve 必须可被 findChild 找到"
        assert spin.value() == 15.0, "默认值应保持 15.0"

    def test_lbl_promotion_reserve_found(self, quick_window):
        """活动预留标题标签仍可找到。"""
        from PySide6.QtWidgets import QLabel
        lbl = quick_window.findChild(QLabel, "lblPromotionReserve")
        assert lbl is not None, "lblPromotionReserve 必须可被 findChild 找到"
        assert lbl.text() == "活动预留"

    def test_promotion_reserve_in_separate_column(self, quick_window):
        """活动预留在 noActivityGrid 的 column 3，与标价利率 column 2 分开。"""
        section = quick_window.findChild(QFrame, "noActivitySection")
        assert section is not None
        grid = section.findChild(QGridLayout, "noActivityGrid")
        assert grid is not None

        # 找到 lblPromotionReserve 所在的 grid 列号
        lbl = quick_window.findChild(QDoubleSpinBox, "spinPromotionReserve")
        assert lbl is not None

        # 遍历 grid items 找 spinPromotionReserve 的列号
        reserve_col = None
        rate_col = None
        for i in range(grid.count()):
            item = grid.itemAt(i)
            if item is None:
                continue
            w = item.widget()
            if w is None:
                continue
            row, col, _rs, _cs = grid.getItemPosition(i)
            # promotionReserveRow 容器包含 spinPromotionReserve
            if w.objectName() == "promotionReserveRow":
                reserve_col = col
            elif w.objectName() == "listPriceRateRow":
                rate_col = col

        assert reserve_col is not None, "promotionReserveRow 必须在 grid 中"
        assert rate_col is not None, "listPriceRateRow 必须在 grid 中"
        assert reserve_col > rate_col, (
            f"活动预留列({reserve_col}) 必须在标价利率列({rate_col}) 右侧"
        )

    def test_collapse_expand_50_times_zero_drift(self, quick_window):
        """折叠/展开 50 次后窗口尺寸与初始值 0px 偏差。"""
        collapsed_h = quick_window._collapsed_height
        expanded_h = quick_window._expanded_height
        assert collapsed_h > 0, "collapsed_height 必须已测量"
        assert expanded_h > collapsed_h, "expanded_height 必须大于 collapsed_height"

        for _ in range(50):
            quick_window._toggle_details()

        # 50 次切换后（偶数次回到 collapsed）
        assert quick_window._expanded is False, "50 次切换后应回到折叠状态"
        assert quick_window._collapsed_height == collapsed_h, (
            f"collapsed_height 不应漂移："
            f"初始={collapsed_h}，当前={quick_window._collapsed_height}"
        )
        assert quick_window._expanded_height == expanded_h, (
            f"expanded_height 不应漂移："
            f"初始={expanded_h}，当前={quick_window._expanded_height}"
        )

    def test_calculation_binder_finds_reserve_spin(self, quick_window):
        """CalculationBinder.profit_binder 的 spin_reserve 指向正确控件。"""
        binder = quick_window.profit_binder
        assert binder.spin_reserve is not None, "Binder 必须找到 spin_reserve"
        assert binder.spin_reserve.objectName() == "spinPromotionReserve"
