"""数值输入框首次点击全选 targeted tests（MousePress → MouseRelease 方案）。

offscreen 平台的鼠标点击焦点模拟不可靠（QTest.mouseClick 不传递焦点、
clearFocus 可能不生效），因此：
- 单元级直接调用 FirstClickSelectAllFilter.eventFilter 验证完整事件序列：
  无焦点第一次点击 → MousePress 设标记 → MouseRelease 后 selectAll；
  已有焦点第二次点击 → 不设标记，不触发 selectAll；
- 点击箭头/边框区域（事件目标非 lineEdit）→ 不设标记；
- 普通文字编辑器（QLineEdit）→ 不受影响；
- 主软件 CalculationPage 与 UU测算 都安装同一公共实现（不复制两套逻辑）；
- 真实鼠标事件序列测试（QTest.mouseClick 内部已包含 Press+Release）。

禁止真实 API / 浏览器 / 外部链接。
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QLineEdit, QWidget  # noqa: E402

from profit_accounting_26.ui.input_editing import (  # noqa: E402
    FirstClickSelectAllFilter,
    install_first_click_select_all,
)


def _press(pos: QPointF | None = None) -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos or QPointF(1.0, 1.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _release(pos: QPointF | None = None) -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        pos or QPointF(1.0, 1.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
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
    def test_press_then_release_selects_all_when_no_focus(self, host, qapp):
        """无焦点第一次完整点击（Press → Release）→ processEvents → 全选。"""
        spin = host._spin
        editor = spin.lineEdit()
        assert spin.hasFocus() is False, "未显示控件不应有焦点"

        # Step 1: MousePress → 设置 _pending_line 标记
        press_intercepted = host._guard.eventFilter(editor, _press())
        assert press_intercepted is False, "不拦截 MousePress"
        assert host._guard._pending_line is editor, "Press 后应标记 pending_line"
        assert editor.selectedText() == "", "Press 阶段不应全选"

        # Step 2: MouseRelease → 清除标记，安排 QTimer.singleShot(0, selectAll)
        release_intercepted = host._guard.eventFilter(editor, _release())
        assert release_intercepted is False, "不拦截 MouseRelease"
        assert host._guard._pending_line is None, "Release 后应清除 pending_line"

        # Step 3: processEvents → 执行 singleShot 回调中的 selectAll
        qapp.processEvents()
        full = editor.text().strip()
        assert editor.selectedText() == full, (
            f"Press→Release→processEvents 后应全选，"
            f"实际 selectedText={editor.selectedText()!r} vs {full!r}"
        )

    def test_second_click_no_select_all_when_focused(self, host, monkeypatch, qapp):
        """已有焦点第二次点击 → 不设标记 → Release 不触发全选。

        offscreen 平台焦点切换不可靠，注入 hasFocus=True 模拟已聚焦状态。
        """
        spin = host._spin
        editor = spin.lineEdit()
        monkeypatch.setattr(spin, "hasFocus", lambda: True)

        # Press（已有焦点）→ 不设标记
        host._guard.eventFilter(editor, _press())
        assert host._guard._pending_line is None, "已聚焦时 Press 不应设标记"

        # Release → 无标记，不触发 selectAll
        host._guard.eventFilter(editor, _release())
        qapp.processEvents()
        assert editor.selectedText() == "", "已聚焦点击不得全选"

    def test_arrow_area_press_does_not_set_pending(self, host):
        """点击微调箭头/边框（事件目标为 spinbox 本体，非 lineEdit）不设标记。"""
        spin = host._spin
        editor = spin.lineEdit()
        assert spin.hasFocus() is False

        host._guard.eventFilter(spin, _press())
        assert host._guard._pending_line is None, "点击箭头不应设标记"
        assert editor.selectedText() == "", "点击箭头不应全选"

    def test_plain_line_edit_not_affected(self, host, qapp):
        """普通文字编辑器（QLineEdit）不受全选过滤器影响。"""
        line = host._line

        # Press on plain QLineEdit → 不匹配 QDoubleSpinBox
        host._guard.eventFilter(line, _press())
        assert host._guard._pending_line is None, "普通 QLineEdit 不应设标记"

        # Release
        host._guard.eventFilter(line, _release())
        qapp.processEvents()
        assert line.selectedText() == "", "普通 QLineEdit 不应全选"

    def test_release_on_different_widget_ignored(self, host, qapp):
        """MouseRelease 目标与 Press 不同 → 不触发 selectAll。"""
        spin = host._spin
        editor = spin.lineEdit()

        # Press on editor → 设标记
        host._guard.eventFilter(editor, _press())
        assert host._guard._pending_line is editor

        # Release on a different widget (not the same lineEdit)
        other = QLineEdit(host)
        host._guard.eventFilter(other, _release())
        assert host._guard._pending_line is editor, "不同控件 Release 不应清除标记"
        qapp.processEvents()
        assert editor.selectedText() == "", "不同控件 Release 不应触发全选"
        other.deleteLater()

    def test_outside_root_not_affected(self, qapp):
        """root 之外的 spinbox 不受该过滤器影响。"""
        root = QWidget()
        outside = QWidget()
        spin = QDoubleSpinBox(outside)
        guard = FirstClickSelectAllFilter(root)
        qapp.installEventFilter(guard)
        try:
            editor = spin.lineEdit()
            guard.eventFilter(editor, _press())
            assert guard._pending_line is None, "root 之外的 spinbox 不应设标记"
        finally:
            qapp.removeEventFilter(guard)
            guard.deleteLater()
            outside.deleteLater()
            root.deleteLater()

    def test_real_mouse_click_sequence_selects_all(self, host, qapp):
        """真实鼠标事件序列（通过 QApplication.sendEvent）验证完整 Press→Release。"""
        spin = host._spin
        editor = spin.lineEdit()
        assert spin.hasFocus() is False

        # 发送真实 MousePress
        press_event = _press(QPointF(5.0, 5.0))
        QApplication.instance().sendEvent(editor, press_event)
        # 发送真实 MouseRelease
        release_event = _release(QPointF(5.0, 5.0))
        QApplication.instance().sendEvent(editor, release_event)

        qapp.processEvents()
        full = editor.text().strip()
        assert editor.selectedText() == full, (
            f"真实鼠标事件序列后应全选，实际 selectedText={editor.selectedText()!r}"
        )


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

    def test_quick_press_release_selects_all_value(self, qapp, tmp_path, monkeypatch):
        """UU测算 数值输入框：MousePress → MouseRelease → processEvents → 全选。"""
        monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
        from profit_accounting_26.application import AppContext
        from profit_accounting_26.ui.quick_calculator_window import QuickCalculatorWindow

        context = AppContext.create_default()
        window = QuickCalculatorWindow(context)
        try:
            spin = window.spin_length
            spin.setValue(30.5)
            editor = spin.lineEdit()
            assert spin.hasFocus() is False, "未显示窗口控件不应有焦点"

            # 真实鼠标事件序列
            press = _press(QPointF(5.0, 5.0))
            QApplication.instance().sendEvent(editor, press)
            release = _release(QPointF(5.0, 5.0))
            QApplication.instance().sendEvent(editor, release)

            qapp.processEvents()
            full = editor.text().strip()
            assert editor.selectedText() == full, "Quick 输入框第一次点击后应全选"
        finally:
            window.close()
            window.deleteLater()
