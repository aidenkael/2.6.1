from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from profit_accounting_26.domain.models import ImageType, LogisticsQuote
from profit_accounting_26.ui.input_editing import DraftAwareDoubleSpinBox


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None, *, soft: bool = False) -> None:
        super().__init__(parent)
        self.setProperty("softCard" if soft else "card", True)

    def set_choice_state(self, *, selected: bool, frozen: bool = False) -> None:
        self.setProperty("choiceSelected", selected)
        self.setProperty("choiceFrozen", frozen)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


# ----------------------------------------------------------------------
# 中文弹窗 helper：按钮文案完全可控，不依赖 Qt 默认英文按钮
# ----------------------------------------------------------------------


def confirm_action(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    confirm_text: str = "确定",
    cancel_text: str = "取消",
    danger: bool = False,
) -> bool:
    """中文确认弹窗；返回用户是否点击了确认按钮。"""
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question)
    confirm_button = box.addButton(confirm_text, QMessageBox.ButtonRole.AcceptRole)
    box.addButton(cancel_text, QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is confirm_button


def show_notice(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    ok_text: str = "确定",
    level: str = "info",
) -> None:
    """中文单按钮提示弹窗；level: info / warning / error。"""
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    icons = {
        "info": QMessageBox.Icon.Information,
        "warning": QMessageBox.Icon.Warning,
        "error": QMessageBox.Icon.Critical,
    }
    box.setIcon(icons.get(level, QMessageBox.Icon.Information))
    box.addButton(ok_text, QMessageBox.ButtonRole.AcceptRole)
    box.exec()


class SectionHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setProperty("sectionTitle", True)
        layout.addWidget(title_label)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setProperty("muted", True)
            layout.addWidget(subtitle_label)
        layout.addStretch(1)
        self.right_layout = QHBoxLayout()
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(7)
        layout.addLayout(self.right_layout)


class QuickLineEdit(QLineEdit):
    """Line edit with a small whole-field context menu."""

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        copy_action = menu.addAction("复制")
        paste_action = menu.addAction("粘贴")
        clear_action = menu.addAction("清除")
        chosen = menu.exec(event.globalPos())
        if chosen is copy_action:
            self.selectAll()
            self.copy()
        elif chosen is paste_action and not self.isReadOnly():
            self.selectAll()
            self.paste()
        elif chosen is clear_action and not self.isReadOnly():
            self.clear()


class CompactDoubleSpinBox(DraftAwareDoubleSpinBox):
    """Compact numeric editor: no arrow buttons, wheel adjustment retained."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        copy_action = menu.addAction("复制")
        paste_action = menu.addAction("粘贴")
        unknown_action = menu.addAction("设为未知")
        chosen = menu.exec(event.globalPos())
        editor = self.lineEdit()
        if chosen is copy_action:
            editor.selectAll()
            editor.copy()
        elif chosen is paste_action and not self.isReadOnly():
            raw = QApplication.clipboard().text().strip().replace(",", "")
            try:
                value = float(raw)
            except ValueError:
                return
            self.setValue(value)
            editor.selectAll()
        elif chosen is unknown_action and not self.isReadOnly():
            self.request_unknown()


class LabeledSpin(QWidget):
    valueChanged = Signal(float)
    editingFinished = Signal()

    def __init__(
        self,
        label: str,
        *,
        suffix: str = "",
        decimals: int = 2,
        minimum: float = 0.0,
        maximum: float = 1_000_000.0,
        value: float = 0.0,
        input_width: int = 106,
        special_text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        self.label_widget = QLabel(label)
        self.label_widget.setProperty("muted", True)
        layout.addWidget(self.label_widget)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(5)
        self.spin = CompactDoubleSpinBox()
        self.spin.setDecimals(decimals)
        self.spin.setRange(minimum, maximum)
        self.spin.setValue(value)
        self.spin.setFixedWidth(input_width)
        if special_text:
            self.spin.setSpecialValueText(special_text)
        input_row.addWidget(self.spin)
        self.unit_label = QLabel(suffix)
        self.unit_label.setProperty("muted", True)
        self.unit_label.setVisible(bool(suffix))
        input_row.addWidget(self.unit_label)
        input_row.addStretch(1)
        layout.addLayout(input_row)
        self.spin.valueChanged.connect(self.valueChanged)
        self.spin.editingFinished.connect(self.editingFinished)

    def value(self) -> float:
        return float(self.spin.value())

    def setValue(self, value: float) -> None:
        self.spin.setValue(float(value))

    def setReadOnly(self, read_only: bool) -> None:
        self.spin.setReadOnly(read_only)
        self.spin.setProperty("readOnly", read_only)
        self.spin.style().unpolish(self.spin)
        self.spin.style().polish(self.spin)

    def setSpecialValueText(self, text: str) -> None:
        self.spin.setSpecialValueText(text)

    def setLabel(self, text: str) -> None:
        self.label_widget.setText(text)


class ImagePreviewDialog(QDialog):
    def __init__(self, path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("图片预览")
        self.resize(980, 760)
        layout = QVBoxLayout(self)
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(path))
        label.setPixmap(
            pixmap.scaled(
                940,
                700,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        layout.addWidget(label)


class ImageSlotWidget(Card):
    changed = Signal()
    removeRequested = Signal(int)
    imageLoaded = Signal(int, str, str)

    def __init__(self, index: int, image_type: ImageType, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.index = index
        self.path: Path | None = None
        self.setAcceptDrops(True)
        self.setMinimumWidth(175)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(5)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addStretch(1)

        self.upload_button = QPushButton("↑")
        self.upload_button.setToolTip("上传图片")
        self.upload_button.setFixedSize(30, 28)
        self.upload_button.clicked.connect(self.select_file)
        header.addWidget(self.upload_button)

        self.delete_button = QPushButton("×")
        self.delete_button.setToolTip("删除图片")
        self.delete_button.setProperty("danger", True)
        self.delete_button.setFixedSize(30, 28)
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(lambda: self.removeRequested.emit(self.index))
        header.addWidget(self.delete_button)
        layout.addLayout(header)

        self.preview = QPushButton("＋\n拖入图片\n或 Ctrl+V")
        self.preview.setFixedHeight(102)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.preview.clicked.connect(self.open_preview)
        layout.addWidget(self.preview)

    def image_type(self) -> ImageType:
        return ImageType.MAIN

    def set_image_type(self, image_type: ImageType) -> None:
        return

    def select_file(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "选择图片",
            "",
            "图片 (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if selected:
            self.load_path(Path(selected))

    def _confirm_replace(self) -> bool:
        if self.path is None:
            return True
        return confirm_action(
            self,
            "覆盖图片",
            "当前图片框已有图片，是否覆盖？",
            confirm_text="覆盖",
            cancel_text="取消",
        )

    def load_path(self, path: Path) -> None:
        if not path.is_file() or not self._confirm_replace():
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            show_notice(self, "无法读取", "该文件不是可读取的图片。", level="warning")
            return
        self.path = path
        self.preview.setText("")
        scaled = pixmap.scaled(
            170,
            90,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview.setIcon(QIcon(scaled))
        self.preview.setIconSize(QSize(170, 90))
        self.delete_button.setEnabled(True)
        self.changed.emit()
        self.imageLoaded.emit(self.index, str(path), self.image_type().value)

    def clear_image(self) -> None:
        self.path = None
        self.preview.setIcon(QIcon())
        self.preview.setText("＋\n拖入图片\n或 Ctrl+V")
        self.delete_button.setEnabled(False)
        self.changed.emit()

    def open_preview(self) -> None:
        if self.path:
            ImagePreviewDialog(self.path, self).exec()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.load_path(Path(url.toLocalFile()))
                event.acceptProposedAction()
                return


class QuoteCard(Card):
    selected = Signal(str)

    def __init__(self, forwarder_id: str, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent, soft=True)
        self.forwarder_id = forwarder_id
        self._name = name
        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 7, 9, 8)
        # 货代区释放尾程输入行后，适当增加行距（不明显增加页面高度）
        layout.setSpacing(7)
        title_row = QHBoxLayout()
        self.select_button = QPushButton(f"○ {name}")
        self.select_button.setCheckable(True)
        self.select_button.clicked.connect(lambda: self.selected.emit(self.forwarder_id))
        title_row.addWidget(self.select_button)
        title_row.addStretch(1)
        self.cheapest_label = QLabel("")
        self.cheapest_label.setProperty("success", True)
        title_row.addWidget(self.cheapest_label)
        layout.addLayout(title_row)
        self.rows: dict[str, QLabel] = {}
        for key, label in (
            ("actual", "实际重"),
            ("volume", "体积重"),
            ("chargeable", "计费重"),
            ("weight_fee", "头程费"),
            ("fixed", "固定费"),
            # 尾程行标题留空但保留行高：货代卡只负责头程展示
            ("tail", ""),
            ("total", "头程总费用"),
        ):
            row = QHBoxLayout()
            row.setSpacing(4)
            row.addWidget(QLabel(label))
            row.addStretch(1)
            value = QLabel("—")
            if key == "total":
                value.setProperty("primary", True)
            row.addWidget(value)
            self.rows[key] = value
            layout.addLayout(row)

    def set_checked(self, checked: bool, *, user_changed: bool = False) -> None:
        self.select_button.setChecked(checked)
        prefix = "✓" if checked and user_changed else ("●" if checked else "○")
        self.select_button.setText(f"{prefix} {self._name}")
        self.set_choice_state(selected=checked, frozen=not checked)

    def update_quote(self, quote: LogisticsQuote | None, *, cheapest: bool = False) -> None:
        self.cheapest_label.setText("更低成本" if cheapest else "")
        if quote is None:
            for key, label in self.rows.items():
                label.setText("" if key == "tail" else "—")
            return
        self.rows["actual"].setText(f"{quote.actual_weight_kg:.3f} kg")
        self.rows["volume"].setText(f"{quote.volume_weight_kg:.3f} kg")
        self.rows["chargeable"].setText(f"{quote.chargeable_weight_kg:.3f} kg")
        self.rows["weight_fee"].setText(f"¥{quote.weight_fee_rmb:.2f}")
        self.rows["fixed"].setText(f"¥{quote.fixed_fee_rmb:.2f}")
        # 尾程金额不显示；头程总费用 = 头程费 + 固定服务费（展示口径，不改业务引擎）
        self.rows["tail"].setText("")
        self.rows["total"].setText(f"¥{quote.weight_fee_rmb + quote.fixed_fee_rmb:.2f}")
