"""数值输入框首次点击全选 targeted tests（任务书六节）。

offscreen 平台的鼠标点击焦点模拟不可靠（QTest.mouseClick 不传递焦点、
clearFocus 可能不生效），因此：
- 单元级直接调用 FirstClickSelectAllFilter.eventFilter 验证两个分支：
  无焦点第一次点击 → 安排延时全选（QTimer.singleShot）；
  已有焦点第二次点击 → 放行（Qt 默认）；
- 点击箭头/边框区域（事件目标非 lineEdit）→ 不拦截；
- 普通文字编辑器（QLineEdit）→ 不受影响；
- 主软件 CalculationPage 与 UU测算 都安装同一公共实现（不复制两套逻辑）；
- UU测算 未显示窗口集成点击：第一次点击全选整个数值。

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
    def test_first_click_schedules_select_all_when_no_focus(self, host, qapp):
        """无焦点第一次点击 → 不拦截事件，但通过 QTimer.singleShot 安排全选。"""
        spin = host._spin
        editor = spin.lineEdit()
        assert spin.hasFocus() is False, "未显示控件不应有焦点"
        intercepted = host._guard.eventFilter(editor, _press())
        assert intercepted is False, "新版本不拦截事件（让 Qt 正常处理焦点）"
        # 处理 pending QTimer.singleShot(0, ...) 回调
        qapp.processEvents()
        full = editor.text().strip()
        assert editor.selectedText() == full, (
            f"第一次点击后 processEvents 应全选整个数值，"
            f"实际 selectedText={editor.selectedText()!r} vs {full!r}"
        )

    def test_second_click_restores_default_when_focused(self, host, monkeypatch):
        """已有焦点第二次点击 → 放行（Qt 默认光标行为），不再强制全选。

        offscreen 平台窗口焦点切换不可靠（show 后 hasFocus 可能仍 False），
        这里直接注入 hasFocus=True 验证"已聚焦"分支。
        """
        spin = host._spin
        editor = spin.lineEdit()
        monkeypatch.setattr(spin, "hasFocus", lambda: True)
        intercepted = host._guard.eventFilter(editor, _press())
        assert intercepted is False, "已聚焦时不得拦截点击"
        assert editor.selectedText() == "", "已聚焦点击不得再全选"

    def test_arrow_area_click_not_intercepted(self, host):
        """点击微调箭头/边框区域（事件目标为 spinbox 本体，非 lineEdit）不触发全选。"""
        spin = host._spin
        editor = spin.lineEdit()
        assert spin.hasFocus() is False
        intercepted = host._guard.eventFilter(spin, _press())
        assert intercepted is False, "点击箭头/边框不得拦截"
        assert editor.selectedText() == "", "点击箭头不得触发全选"

    def test_plain_line_edit_not_affected(self, host):
        """普通文字编辑器（QLineEdit）不受全选过滤器影响。"""
        line = host._line
        intercepted = host._guard.eventFilter(line, _press())
        assert intercepted is False, "普通 QLineEdit 不应被拦截"
        assert line.selectedText() == "", "普通 QLineEdit 不应被强制全选"

    def test_outside_root_not_affected(self, qapp):
        """root 之外的 spinbox 不受该过滤器影响。"""
        root = QWidget()
        outside = QWidget()
        spin = QDoubleSpinBox(outside)  # spin 不在 root 内
        guard = FirstClickSelectAllFilter(root)
        qapp.installEventFilter(guard)
        try:
            editor = spin.lineEdit()
            intercepted = guard.eventFilter(editor, _press())
            assert intercepted is False, "root 之外的 spinbox 不得被拦截"
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

    def test_quick_first_click_selects_all_value(self, qapp, tmp_path, monkeypatch):
        """UU测算 数值输入框：未显示窗口上第一次点击后 processEvents 全选数值。"""
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
            QTest.mouseClick(editor, Qt.MouseButton.LeftButton)
            # 处理 QTimer.singleShot(0, ...) 回调
            qapp.processEvents()
            full = editor.text().strip()
            assert editor.selectedText() == full, "Quick 输入框第一次点击后应全选"
        finally:
            window.close()
            window.deleteLater()
