"""数值输入框首次点击全选 targeted tests（FocusIn + MouseRelease 方案）。

事件序列：
  MousePress → FocusIn(MouseFocusReason) → MouseRelease → singleShot(selectAll)

offscreen 平台的鼠标点击焦点模拟不可靠（QTest.mouseClick 不传递焦点），
因此单元测试直接调用 eventFilter 构造 FocusIn + MouseRelease 事件序列。

禁止真实 API / 浏览器 / 外部链接。
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QFocusEvent, QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QLineEdit, QWidget  # noqa: E402

from profit_accounting_26.ui.input_editing import (  # noqa: E402
    FirstClickSelectAllFilter,
    install_first_click_select_all,
)


def _focus_in_mouse() -> QFocusEvent:
    """模拟鼠标聚焦事件。"""
    return QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.MouseFocusReason)


def _focus_in_tab() -> QFocusEvent:
    """模拟 Tab 聚焦事件。"""
    return QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.TabFocusReason)


def _release(pos: QPointF | None = None) -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        pos or QPointF(1.0, 1.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _press(pos: QPointF | None = None) -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos or QPointF(1.0, 1.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


@pytest.fixture
def host(qapp):
    """带一个 QDoubleSpinBox + 一个普通 QLineEdit 的宿主（未显示，无自动焦点）。"""
    window = QWidget()
    spin = QDoubleSpinBox(window)
    spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
    spin.setValue(123.456)
    line = QLineEdit(window)
    line.setText("hello world")
    guard = install_first_click_select_all(window)
    window._guard = guard
    window._spin = spin
    window._line = line
    yield window
    guard.deleteLater()
    window.deleteLater()


class TestFirstClickSelectAll:
    def test_focusin_mouse_then_release_selects_all(self, host, qapp):
        """FocusIn(Mouse) → MouseRelease → processEvents → 全选。"""
        spin = host._spin
        editor = spin.lineEdit()

        # Step 1: FocusIn with MouseFocusReason → 设标记
        host._guard.eventFilter(editor, _focus_in_mouse())
        assert host._guard._pending_mouse_select_all is editor, (
            "FocusIn(Mouse) 后应设 _pending_mouse_select_all"
        )
        assert editor.selectedText() == "", "FocusIn 阶段不应全选"

        # Step 2: MouseButtonRelease on same lineEdit → 清标记 + 安排 singleShot
        host._guard.eventFilter(editor, _release())
        assert host._guard._pending_mouse_select_all is None, (
            "Release 后应清除标记"
        )

        # Step 3: processEvents → 执行 singleShot selectAll
        qapp.processEvents()
        full = editor.text().strip()
        assert editor.selectedText() == full, (
            f"Release→processEvents 后应全选，"
            f"实际 selectedText={editor.selectedText()!r} vs {full!r}"
        )

    def test_focusin_tab_does_not_set_pending(self, host):
        """Tab 聚焦不设标记（只响应鼠标点击）。"""
        spin = host._spin
        editor = spin.lineEdit()

        host._guard.eventFilter(editor, _focus_in_tab())
        assert host._guard._pending_mouse_select_all is None, (
            "Tab 聚焦不应设 _pending_mouse_select_all"
        )

    def test_second_click_no_focus_in_no_select_all(self, host, qapp):
        """已有焦点第二次点击 → 不产生 FocusIn → Release 不触发全选。"""
        spin = host._spin
        editor = spin.lineEdit()

        # 第二次点击时没有 FocusIn 事件，直接 Release
        host._guard.eventFilter(editor, _release())
        qapp.processEvents()
        assert editor.selectedText() == "", "第二次点击不应全选"

    def test_arrow_area_no_focus_in(self, host):
        """点击 SpinBox 箭头区域 → 不会给 lineEdit 发送 FocusIn(Mouse)。"""
        spin = host._spin
        # 模拟 spinbox 本体收到 FocusIn（不是 lineEdit）
        host._guard.eventFilter(spin, _focus_in_mouse())
        assert host._guard._pending_mouse_select_all is None, (
            "SpinBox 本体 FocusIn 不应设标记（必须是 lineEdit）"
        )

    def test_plain_line_edit_not_affected(self, host, qapp):
        """普通 QLineEdit（非 SpinBox 内部）不受影响。"""
        line = host._line

        host._guard.eventFilter(line, _focus_in_mouse())
        assert host._guard._pending_mouse_select_all is None, (
            "普通 QLineEdit 不应设标记"
        )

        host._guard.eventFilter(line, _release())
        qapp.processEvents()
        assert line.selectedText() == "", "普通 QLineEdit 不应全选"

    def test_release_on_different_widget_ignored(self, host, qapp):
        """Release 目标与 FocusIn 设的 lineEdit 不同 → 不触发。"""
        spin = host._spin
        editor = spin.lineEdit()

        host._guard.eventFilter(editor, _focus_in_mouse())
        assert host._guard._pending_mouse_select_all is editor

        other = QLineEdit(host)
        host._guard.eventFilter(other, _release())
        assert host._guard._pending_mouse_select_all is editor, (
            "不同控件 Release 不应清除标记"
        )
        qapp.processEvents()
        assert editor.selectedText() == "", "不同控件 Release 不应触发全选"
        other.deleteLater()

    def test_outside_root_not_affected(self, qapp):
        """root 之外的 spinbox lineEdit 不受影响。"""
        root = QWidget()
        outside = QWidget()
        spin = QDoubleSpinBox(outside)
        guard = FirstClickSelectAllFilter(root)
        qapp.installEventFilter(guard)
        try:
            editor = spin.lineEdit()
            guard.eventFilter(editor, _focus_in_mouse())
            assert guard._pending_mouse_select_all is None, (
                "root 之外不应设标记"
            )
        finally:
            qapp.removeEventFilter(guard)
            guard.deleteLater()
            outside.deleteLater()
            root.deleteLater()


class TestSelectAllInstalledInBothApps:
    def test_calculation_page_installs_shared_implementation(self, qapp, tmp_path, monkeypatch):
        """主软件 CalculationPage 安装同一公共实现。"""
        monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
        from profit_accounting_26.application import AppContext
        from profit_accounting_26.ui.pages.calculation_page import CalculationPage

        context = AppContext.create_default()
        page = CalculationPage(context)
        try:
            assert hasattr(page, "_first_click_select_all_guard")
            assert isinstance(page._first_click_select_all_guard, FirstClickSelectAllFilter)
        finally:
            page.close()
            page.deleteLater()

    def test_quick_window_installs_shared_implementation(self, qapp, tmp_path, monkeypatch):
        """UU测算 安装同一公共实现。"""
        monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
        from profit_accounting_26.application import AppContext
        from profit_accounting_26.ui.quick_calculator_window import QuickCalculatorWindow

        context = AppContext.create_default()
        window = QuickCalculatorWindow(context)
        try:
            assert hasattr(window, "_first_click_select_all_guard")
            assert isinstance(window._first_click_select_all_guard, FirstClickSelectAllFilter)
        finally:
            window.close()
            window.deleteLater()

    def test_quick_focusin_release_selects_all(self, qapp, tmp_path, monkeypatch):
        """UU测算 数值输入框：FocusIn(Mouse) → Release → processEvents → 全选。"""
        monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
        from profit_accounting_26.application import AppContext
        from profit_accounting_26.ui.quick_calculator_window import QuickCalculatorWindow

        context = AppContext.create_default()
        window = QuickCalculatorWindow(context)
        try:
            spin = window.spin_length
            spin.setValue(30.5)
            editor = spin.lineEdit()

            # 模拟 FocusIn(Mouse)
            guard = window._first_click_select_all_guard
            guard.eventFilter(editor, _focus_in_mouse())
            assert guard._pending_mouse_select_all is editor

            # 模拟 MouseRelease
            guard.eventFilter(editor, _release())
            qapp.processEvents()

            full = editor.text().strip()
            assert editor.selectedText() == full, (
                f"Quick 输入框 FocusIn→Release 后应全选，"
                f"实际={editor.selectedText()!r} vs {full!r}"
            )
        finally:
            window.close()
            window.deleteLater()
