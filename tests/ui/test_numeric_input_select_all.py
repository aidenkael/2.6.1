"""数值输入 ``.00`` UX 回归：获得焦点自动全选，直接键入即可替换。

真实用户交互契约：
- 既有 ``18.00`` / ``0.00`` 的可编辑数值框，点击/聚焦后直接输入新数字即
  自然替换，无需先按 Delete/Backspace；
- 保留小数精度（不变成整数输入）；
- Enter 提交；
- 已开始编辑后光标编辑保持 Qt 原生行为；
- 删空后失焦保持既有空白草稿回退安全行为；
- 只读（冻结）结果字段保持只读。

实现说明：旧 FirstClickSelectAllFilter 失败的根因是 FocusIn 投递给
spinbox 本身而非内部 lineEdit（实测验证），且按 MouseFocusReason 过滤
不可靠；本实现统一监听 spinbox 的 FocusIn 并用 0ms 定时器延迟全选。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QFocusEvent, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QDoubleSpinBox

from profit_accounting_26.ui.input_editing import (
    DraftAwareDoubleSpinBox,
    install_natural_numeric_input,
)


@pytest.fixture
def spin(qapp):
    box = QDoubleSpinBox()
    box.setRange(0.0, 10_000_000.0)  # 与主软件金额/成本字段量级一致
    box.setValue(18.0)
    guard = install_natural_numeric_input(box)
    box._guard = guard
    box.show()
    qapp.processEvents()
    yield box
    box.deleteLater()
    qapp.processEvents()


def _focus(spin, qapp, reason=Qt.FocusReason.MouseFocusReason):
    """模拟真实焦点进入（FocusIn 由 Qt 投递给 spinbox 本身）。"""
    event = QFocusEvent(QEvent.Type.FocusIn, reason)
    QApplication.sendEvent(spin, event)
    qapp.processEvents()
    qapp.processEvents()  # 第二次让 0ms 定时器执行 selectAll


def _type(spin, text):
    for ch in text:
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            _key_for(ch),
            Qt.KeyboardModifier.NoModifier,
            ch,
        )
        QApplication.sendEvent(spin.lineEdit(), event)


def _key_for(ch: str) -> Qt.Key:
    digits = "0123456789"
    if ch in digits:
        return getattr(Qt.Key, f"Key_{digits.index(ch)}")
    return {
        ".": Qt.Key_Period,
        "-": Qt.Key_Minus,
    }.get(ch, Qt.Key_unknown)


def test_click_focus_selects_all_and_typing_replaces_18_00(qapp, spin):
    """既有 18.00 → 点击聚焦 → 直接键入 5 → 无需手动删除得到 5。"""
    assert spin.text() == "18.00"
    _focus(spin, qapp)
    assert spin.lineEdit().selectedText() == "18.00"

    _type(spin, "5")
    assert spin.lineEdit().text() == "5"  # 替换而非插入

    # Enter 提交，保留两位小数精度
    enter = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(spin.lineEdit(), enter)
    qapp.processEvents()
    assert spin.value() == pytest.approx(5.0)
    assert spin.text() == "5.00"


def test_zero_display_0_00_same_flow(qapp, spin):
    spin.setValue(0.0)
    _focus(spin, qapp)
    assert spin.lineEdit().selectedText() == "0.00"
    _type(spin, "42.5")
    enter = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Enter, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(spin.lineEdit(), enter)
    qapp.processEvents()
    assert spin.value() == pytest.approx(42.5)
    assert spin.text() == "42.50"


def test_tab_focus_also_selects_all(qapp, spin):
    _focus(spin, qapp, reason=Qt.FocusReason.TabFocusReason)
    assert spin.lineEdit().selectedText() == "18.00"


def test_editing_after_start_keeps_native_cursor_behavior(qapp, spin):
    """用户已开始编辑后，光标编辑保持原生插入行为（不再整框替换）。"""
    _focus(spin, qapp)
    _type(spin, "5")
    assert spin.lineEdit().text() == "5"

    # 光标移到末尾后继续输入 → 原生插入，不会被过滤 cleared/重选
    spin.lineEdit().setCursorPosition(1)
    _type(spin, "2")
    assert spin.lineEdit().text() == "52"

    enter = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Enter, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(spin.lineEdit(), enter)
    qapp.processEvents()
    assert spin.value() == pytest.approx(52.0)


def test_mouse_press_after_focus_clears_selection_like_native(qapp, spin):
    """已聚焦后的再次点击不重新全选：定位光标（清选区）为 Qt 原生行为。"""
    _focus(spin, qapp)
    assert spin.lineEdit().selectedText() == "18.00"

    pos = QPointF(5.0, 12.0)
    gpos = spin.lineEdit().mapToGlobal(pos.toPoint())
    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos,
        QPointF(gpos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(spin.lineEdit(), press)
    qapp.processEvents()
    assert spin.lineEdit().selectedText() == ""


def test_read_only_field_stays_read_only(qapp):
    """只读冻结字段不接受输入（Qt 原生保证），过滤器不改变这一点。"""
    box = QDoubleSpinBox()
    box.setRange(0.0, 10_000_000.0)
    box.setValue(18.0)
    box.setReadOnly(True)
    install_natural_numeric_input(box)
    box.show()
    qapp.processEvents()
    _focus(box, qapp)
    _type(box, "9")
    qapp.processEvents()
    assert box.value() == pytest.approx(18.0)
    box.deleteLater()
    qapp.processEvents()


def test_draft_aware_blank_restore_still_applies(qapp):
    """删空文本后失焦：既有空白草稿回退安全行为保持。"""
    box = DraftAwareDoubleSpinBox()
    box.setRange(0.0, 10_000_000.0)
    box.setValue(18.0)
    install_natural_numeric_input(box)
    box.show()
    qapp.processEvents()

    _focus(box, qapp)
    assert box.lineEdit().selectedText() == "18.00"
    box.lineEdit().clear()  # 用户删空
    box.clearFocus()        # 失焦 → editingFinished → 空白草稿回退
    qapp.processEvents()

    assert box.value() == pytest.approx(18.0)
    assert box.text() == "18.00"

    box.deleteLater()
    qapp.processEvents()
