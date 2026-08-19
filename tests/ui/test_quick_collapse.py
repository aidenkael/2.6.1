"""UU测算 折叠/展开 targeted tests（任务书三、四节）。

覆盖：
- 默认折叠：只显示上半部分（spec / cost / forwarder），利润/活动区域默认隐藏；
- 折叠箭头：▼ = 可展开，▲ = 可收起；点击切换；
- 连续折叠/展开 50 次：窗口宽度恒 448、collapsed 高度恒定、
  expanded 高度恒定、0px 漂移（稳定尺寸切换，禁止按当前尺寸累加推导）；
- 活动预留 spinPromotionReserve objectName / Binder 绑定不变。

禁止真实 API / 浏览器 / 外部链接。
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QDoubleSpinBox, QFrame  # noqa: E402

from profit_accounting_26.ui.quick_calculator_window import (  # noqa: E402
    QUICK_WINDOW_WIDTH,
    QuickCalculatorWindow,
)

_DETAIL_SECTIONS = ("noActivitySection", "activitySection", "bottomSection")
_BASE_SECTIONS = ("specSection", "costSection", "forwarderCostSection")


@pytest.fixture
def temp_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    from profit_accounting_26.application import AppContext
    return AppContext.create_default()


@pytest.fixture
def page(qapp, temp_context):
    window = QuickCalculatorWindow(temp_context)
    window.show()  # 建立原生窗口，走一次 showEvent 固定契约
    yield window
    window.close()
    window.deleteLater()


def _assert_sections(page: QuickCalculatorWindow, hidden: bool, names: tuple[str, ...]) -> None:
    for name in names:
        section = page.findChild(QFrame, name)
        assert section is not None, f"{name} 应存在"
        assert section.isHidden() is hidden, (
            f"{name} 折叠状态错误：期望 hidden={hidden}，实际 isHidden={section.isHidden()}"
        )


class TestQuickCollapse:
    def test_collapsed_by_default(self, page):
        """默认折叠：利润/活动区域隐藏，上半部分保留，箭头为 ▼。"""
        assert page._expanded is False
        assert page.btn_toggle_details.text() == "▼"
        _assert_sections(page, hidden=True, names=_DETAIL_SECTIONS)
        _assert_sections(page, hidden=False, names=_BASE_SECTIONS)

    def test_expand_shows_profit_sections(self, page):
        """点击箭头展开：显示完整 UU测算，箭头变 ▲。"""
        QTest.mouseClick(page.btn_toggle_details, Qt.MouseButton.LeftButton)
        assert page._expanded is True
        assert page.btn_toggle_details.text() == "▲"
        _assert_sections(page, hidden=False, names=_DETAIL_SECTIONS)
        _assert_sections(page, hidden=False, names=_BASE_SECTIONS)

    def test_collapse_again_restores_compact(self, page):
        """再次点击收起：恢复紧凑状态，箭头变 ▼。"""
        QTest.mouseClick(page.btn_toggle_details, Qt.MouseButton.LeftButton)
        QTest.mouseClick(page.btn_toggle_details, Qt.MouseButton.LeftButton)
        assert page._expanded is False
        assert page.btn_toggle_details.text() == "▼"
        _assert_sections(page, hidden=True, names=_DETAIL_SECTIONS)

    def test_stay_on_top_checkbox_hidden_when_collapsed(self, page):
        """置顶 checkbox 在 bottomSection 内，折叠时随利润区隐藏（默认置顶不受影响）。"""
        assert page._expanded is False
        assert not page.chk_stay_on_top.isVisibleTo(page), "折叠时置顶 checkbox 应随 bottomSection 隐藏"
        assert bool(page.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)

    def test_promo_reserve_object_name_unchanged(self, page):
        """活动预留 spinPromotionReserve 存在且位于 noActivitySection 内（Binder 绑定不变）。"""
        section = page.findChild(QFrame, "noActivitySection")
        assert section is not None
        spin = section.findChild(QDoubleSpinBox, "spinPromotionReserve")
        assert spin is not None, "spinPromotionReserve 应在 noActivitySection 内"
        assert page.profit_binder is not None


class TestQuickCollapseStableSize:
    def test_collapsed_and_expanded_sizes_are_fixed(self, page):
        """两个稳定尺寸在构造时确定，collapsed 高度小于 expanded 高度。"""
        assert page._collapsed_height > 0
        assert page._expanded_height > 0
        assert page._collapsed_height < page._expanded_height

    def test_fifty_toggle_cycles_zero_drift(self, page):
        """连续展开/收起 50 次：宽度恒 448、两高度各自恒定、0px 漂移。"""
        widths: list[int] = []
        collapsed_heights: list[int] = []
        expanded_heights: list[int] = []
        for _ in range(50):
            page._toggle_details()  # 展开
            widths.append(page.width())
            expanded_heights.append(page.height())
            page._toggle_details()  # 收起
            widths.append(page.width())
            collapsed_heights.append(page.height())
        assert all(width == QUICK_WINDOW_WIDTH for width in widths), "宽度必须始终一致"
        assert len(set(collapsed_heights)) == 1, f"collapsed 高度漂移: {sorted(set(collapsed_heights))}"
        assert len(set(expanded_heights)) == 1, f"expanded 高度漂移: {sorted(set(expanded_heights))}"
        assert collapsed_heights[0] == page._collapsed_height
        assert expanded_heights[0] == page._expanded_height

    def test_width_never_changes_through_toggles(self, page):
        """50 次切换中宽度不允许出现任何不同于 448 的值。"""
        for _ in range(50):
            page._toggle_details()
            assert page.width() == QUICK_WINDOW_WIDTH
        assert page.width() == QUICK_WINDOW_WIDTH
