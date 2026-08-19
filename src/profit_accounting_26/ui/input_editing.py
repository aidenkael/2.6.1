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
