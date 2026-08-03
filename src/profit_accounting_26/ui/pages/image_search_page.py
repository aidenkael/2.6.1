from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt, Signal
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent, QKeyEvent, QKeySequence, QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget

from profit_accounting_26.application import AppContext
from profit_accounting_26.ui.widgets import Card, QuickLineEdit, SectionHeader


class ImageSearchPage(QWidget):
    sendToCalculation = Signal(str, str)

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.path: Path | None = None
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 18)
        layout.setSpacing(12)
        card = Card()
        card_layout = QVBoxLayout(card)
        header = SectionHeader("以图搜图")
        choose = QPushButton("导入图片")
        search = QPushButton("开始搜图")
        search.setProperty("primary", True)
        send = QPushButton("发送到新商品测算")
        header.right_layout.addWidget(choose)
        header.right_layout.addWidget(search)
        header.right_layout.addWidget(send)
        card_layout.addWidget(header)
        self.preview = QLabel("拖入图片、点击导入或按 Ctrl+V 粘贴")
        self.preview.setMinimumHeight(420)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setProperty("muted", True)
        card_layout.addWidget(self.preview)
        link_row = QHBoxLayout()
        self.candidate_link = QuickLineEdit()
        self.candidate_link.setPlaceholderText("可粘贴1688商品链接，发送后带入测算记录")
        copy_link = QPushButton("复制链接")
        copy_link.clicked.connect(lambda: QApplication.clipboard().setText(self.candidate_link.text().strip()))
        link_row.addWidget(self.candidate_link, 1)
        link_row.addWidget(copy_link)
        card_layout.addLayout(link_row)
        self.status = QLabel("开始搜图后会把图片复制到剪贴板，并打开已登录的Edge与1688。")
        self.status.setWordWrap(True)
        self.status.setProperty("muted", True)
        card_layout.addWidget(self.status)
        layout.addWidget(card)
        layout.addStretch(1)
        choose.clicked.connect(self.choose_image)
        search.clicked.connect(self.search_image)
        send.clicked.connect(self.send_image)

    def choose_image(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "选择图片", "", "图片 (*.png *.jpg *.jpeg *.webp *.bmp)")
        if selected:
            self.load_path(Path(selected))

    def load_path(self, path: Path) -> None:
        if not path.is_file():
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            QMessageBox.warning(self, "无法读取", "该文件不是可读取的图片。")
            return
        self.path = path
        self.preview.setPixmap(
            pixmap.scaled(
                760,
                430,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def paste_from_clipboard(self) -> bool:
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    self.load_path(Path(url.toLocalFile()))
                    return True
        image = clipboard.image()
        if image.isNull():
            return False
        array = QByteArray()
        buffer = QBuffer(array)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        target = Path(tempfile.gettempdir()) / "profit_accounting_image_search_clipboard.png"
        target.write_bytes(bytes(array))
        self.load_path(target)
        return True

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.matches(QKeySequence.StandardKey.Paste) and self.paste_from_clipboard():
            event.accept()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.load_path(Path(url.toLocalFile()))
                event.acceptProposedAction()
                return

    def _open_1688(self) -> None:
        url = "https://www.1688.com/"
        if not QDesktopServices.openUrl(QUrl(url)):
            raise RuntimeError("无法打开默认浏览器。")

    def search_image(self) -> None:
        if not self.path:
            return
        pixmap = QPixmap(str(self.path))
        QApplication.clipboard().setPixmap(pixmap)
        try:
            self._open_1688()
        except Exception as exc:
            QMessageBox.warning(self, "打开失败", str(exc))
            return
        self.status.setText("图片已复制到剪贴板，已打开1688首页；请在1688的以图搜图入口粘贴或上传图片。")
        self.status.setProperty("success", True)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def send_image(self) -> None:
        if not self.path:
            QMessageBox.information(self, "未选择图片", "请先导入图片。")
            return
        self.sendToCalculation.emit(str(self.path), self.candidate_link.text().strip())
