from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QComboBox, QLineEdit, QDoubleSpinBox, QWidget


class DraftAwareDoubleSpinBox(QDoubleSpinBox):
    """Commit only valid completed edits; restore the prior value on blank drafts."""

    committed = Signal(float)
    unknownRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._committed_value = float(self.value())
        self._programmatic = False
        self.setKeyboardTracking(False)
        self.editingFinished.connect(self._commit_or_restore)

    def setValue(self, value: float) -> None:  # noqa: N802
        self._programmatic = True
        try:
            super().setValue(float(value))
            self._committed_value = float(value)
        finally:
            self._programmatic = False

    def focusInEvent(self, event) -> None:  # noqa: N802
        self._committed_value = float(self.value())
        super().focusInEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            super().setValue(self._committed_value)
            self.lineEdit().selectAll()
            self.clearFocus()
            event.accept()
            return
        super().keyPressEvent(event)

    def _commit_or_restore(self) -> None:
        if self._programmatic:
            return
        text = self.lineEdit().text().strip()
        if not text:
            super().setValue(self._committed_value)
            return
        try:
            value = float(text.replace(",", ""))
        except ValueError:
            super().setValue(self._committed_value)
            return
        super().setValue(value)
        if value != self._committed_value:
            self._committed_value = value
            self.committed.emit(value)

    def request_unknown(self) -> None:
        self.unknownRequested.emit()


class BlankClickFocusFilter(QObject):
    """Clicking a non-editor area inside the calculation page commits/restores the active editor."""

    EDITOR_TYPES = (QLineEdit, QAbstractSpinBox, QComboBox)

    def __init__(self, root: QWidget) -> None:
        super().__init__(root)
        self.root = root

    def _inside_root(self, target: QWidget) -> bool:
        cursor: QWidget | None = target
        while cursor is not None:
            if cursor is self.root:
                return True
            cursor = cursor.parentWidget()
        return False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() != QEvent.Type.MouseButtonPress or not isinstance(watched, QWidget):
            return False
        target = watched
        if not self._inside_root(target):
            return False
        cursor: QWidget | None = target
        while cursor is not None and cursor is not self.root:
            if isinstance(cursor, self.EDITOR_TYPES):
                return False
            cursor = cursor.parentWidget()
        focused = QApplication.focusWidget()
        if focused is not None and focused is not target:
            focused.clearFocus()
        return False


def install_blank_click_focus_filter(root: QWidget) -> BlankClickFocusFilter:
    guard = BlankClickFocusFilter(root)
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("QApplication尚未创建")
    app.installEventFilter(guard)
    return guard


class FirstClickSelectAllFilter(QObject):
    """数值输入框首次点击全选（主软件 / UU测算 共享的最小公共实现）。

    行为：
    - 输入框当前没有焦点时，第一次鼠标左键点击进入 → 自动全选整个数值，
      效果等同 Tab 键切入（用户直接输入即可覆盖原数字）；
    - 输入框已获得焦点后，第二次及以后点击 → 恢复 Qt 默认行为
      （可移动光标 / 局部选择），不再强制 selectAll；
    - 只作用于 ``QDoubleSpinBox`` 数值输入框（含其内部 lineEdit），
      不影响历史搜索 / 商品链接 / 设置页文本 / API Key / 备注等文字编辑器；
    - 点击上下微调箭头或边框区域不触发全选（必须经过内部 lineEdit 才生效）。

    安装位置：QApplication 级事件过滤器（与 BlankClickFocusFilter 相同机制），
    用 ``root`` 限定作用范围；主软件 CalculationPage 与 UU测算 各安装一份，
    不在两个窗口里复制两套逻辑。
    """

    def __init__(self, root: QWidget) -> None:
        super().__init__(root)
        self.root = root

    def _inside_root(self, target: QWidget) -> bool:
        cursor: QWidget | None = target
        while cursor is not None:
            if cursor is self.root:
                return True
            cursor = cursor.parentWidget()
        return False

    @staticmethod
    def _spinbox_from_target(target: QWidget):
        """事件目标 → 命中的 QDoubleSpinBox；未命中返回 None。

        必须经过 spinbox 的内部 lineEdit 才算命中：点击微调箭头 / 边框 /
        其它控件时返回 None，绝不触发全选。
        """
        cursor: QWidget | None = target
        while cursor is not None:
            if isinstance(cursor, QLineEdit):
                parent = cursor.parentWidget()
                if isinstance(parent, QDoubleSpinBox):
                    return parent
                return None
            if isinstance(cursor, QDoubleSpinBox):
                return None
            cursor = cursor.parentWidget()
        return None

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() != QEvent.Type.MouseButtonPress or not isinstance(watched, QWidget):
            return False
        spin = self._spinbox_from_target(watched)
        if spin is None or not self._inside_root(spin):
            return False
        if spin.hasFocus():
            # 已获得焦点：第二次及以后点击恢复 Qt 默认光标行为
            return False
        # 无焦点第一次点击：拦截本次 press（否则 Qt 默认光标定位会
        # 覆盖 selectAll），手动聚焦并全选整个数值——等同 Tab 切入效果。
        line = spin.lineEdit()
        if line is None:
            return False
        spin.setFocus(Qt.FocusReason.MouseFocusReason)
        line.selectAll()
        return True


def install_first_click_select_all(root: QWidget) -> FirstClickSelectAllFilter:
    """安装首次点击全选过滤器（主软件计算页 / UU测算 各自调用一次）。"""
    guard = FirstClickSelectAllFilter(root)
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("QApplication尚未创建")
    app.installEventFilter(guard)
    return guard
