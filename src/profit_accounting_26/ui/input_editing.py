from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
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

    事件方案（FocusIn + MouseRelease）：
    - 上一版用 MousePress 做起点，但 MousePress 后 Qt 的鼠标处理链可能在
      Release 阶段清除 selection。
    - 本版改用 FocusIn(reason==MouseFocusReason) 做"首次点击"判定——
      FocusIn 只在焦点首次获得时触发一次，已有焦点的后续点击不会产生
      新的 FocusIn，因此天然区分"首次"与"再次"。
    - FocusIn 时只设 _pending_mouse_select_all 标记；
    - 同一 lineEdit 收到 MouseButtonRelease 后，QTimer.singleShot(0, selectAll)
      确保 selectAll 在所有鼠标事件默认处理完成后执行。
    """

    def __init__(self, root: QWidget) -> None:
        super().__init__(root)
        self.root = root
        # 等待同一 lineEdit 的 MouseButtonRelease
        self._pending_mouse_select_all: QLineEdit | None = None

    def _inside_root(self, target: QWidget) -> bool:
        cursor: QWidget | None = target
        while cursor is not None:
            if cursor is self.root:
                return True
            cursor = cursor.parentWidget()
        return False

    @staticmethod
    def _is_spinbox_lineedit(target: QWidget) -> bool:
        """判断目标是否是 QDoubleSpinBox 内部的 lineEdit。"""
        if not isinstance(target, QLineEdit):
            return False
        parent = target.parentWidget()
        return isinstance(parent, QDoubleSpinBox)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        etype = event.type()
        if not isinstance(watched, QWidget):
            return False

        # ── FocusIn（鼠标获得焦点）→ 设标记，等 Release 后全选 ──
        if etype == QEvent.Type.FocusIn:
            if not isinstance(watched, QLineEdit):
                return False
            if not self._inside_root(watched):
                return False
            if not self._is_spinbox_lineedit(watched):
                return False
            if event.reason() == Qt.FocusReason.MouseFocusReason:
                self._pending_mouse_select_all = watched
            return False

        # ── MouseButtonRelease → 如果标记匹配，延迟 selectAll ──
        if etype == QEvent.Type.MouseButtonRelease:
            line = self._pending_mouse_select_all
            if line is None:
                return False
            if watched is not line:
                return False
            self._pending_mouse_select_all = None
            # 让 Qt 完成本次 Release 的所有默认处理（含光标定位），
            # 然后在事件循环尾部执行 selectAll——此时不会有任何后续操作覆盖。
            QTimer.singleShot(0, line.selectAll)
            return False

        return False


def install_first_click_select_all(root: QWidget) -> FirstClickSelectAllFilter:
    """安装首次点击全选过滤器（主软件计算页 / UU测算 各自调用一次）。"""
    guard = FirstClickSelectAllFilter(root)
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("QApplication尚未创建")
    app.installEventFilter(guard)
    return guard
