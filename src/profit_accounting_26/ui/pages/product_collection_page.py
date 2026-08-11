"""商品采集页 —— 第一版极简闭环。

流程：搜索词 + 目标数量 → 后台线程运行 AliExpress Business 采集核心
（不冻结 UI）→ 一次性显示商品卡片墙 → 人工移除 / 恢复 → 一键复制保留链接。

本轮只做内存态 KEEP / REMOVED，不落盘；关闭软件后状态丢失。
采集核心为 vendored 版本：``profit_accounting_26.product_collection``。
"""

from __future__ import annotations

from typing import List

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from profit_accounting_26.product_collection.models import CandidateProduct
from profit_accounting_26.ui.widgets import show_notice

CARD_WIDTH = 250
IMAGE_SIZE = 210
TITLE_HEIGHT = 58
GRID_SPACING = 14

KEEP = "KEEP"
REMOVED = "REMOVED"


class _CardContainer(QWidget):
    """卡片墙容器：窗口尺寸变化时通知页面重新排布卡片。"""

    layoutRequested = Signal()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        super().resizeEvent(event)
        self.layoutRequested.emit()


class ProductCard(QFrame):
    """单张商品卡片：主图 + 标题 + 移除/恢复按钮。"""

    removeRequested = Signal(str)
    restoreRequested = Signal(str)

    def __init__(
        self,
        product: CandidateProduct,
        network: QNetworkAccessManager,
        fetch_images: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._product = product
        self._removed = False
        self._fetch_images = fetch_images
        self.setObjectName("productCard")
        self.setProperty("card", True)
        self.setFixedWidth(CARD_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.lbl_image = QLabel(self)
        self.lbl_image.setObjectName("productCardImage")
        self.lbl_image.setFixedSize(IMAGE_SIZE, IMAGE_SIZE)
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_image.setStyleSheet(
            "background:#f1f5fa;border:1px solid #dbe5f1;border-radius:8px;color:#8a97ab;"
        )
        layout.addWidget(self.lbl_image, 0, Qt.AlignmentFlag.AlignHCenter)

        self.lbl_title = QLabel(product.title, self)
        self.lbl_title.setObjectName("productCardTitle")
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setFixedHeight(TITLE_HEIGHT)
        self.lbl_title.setToolTip(product.title)
        layout.addWidget(self.lbl_title)

        self.btn_action = QPushButton("移除", self)
        self.btn_action.setObjectName("productCardAction")
        self.btn_action.clicked.connect(self._on_action_clicked)
        layout.addWidget(self.btn_action)

        self._network = network
        self._load_image()

    # ------------------------------------------------------------------
    # 对外状态
    # ------------------------------------------------------------------

    @property
    def product(self) -> CandidateProduct:
        return self._product

    @property
    def removed(self) -> bool:
        return self._removed

    def set_removed_mode(self, removed: bool) -> None:
        """切换卡片按钮：移除 <-> 恢复。"""
        self._removed = removed
        self.btn_action.setText("恢复" if removed else "移除")

    # ------------------------------------------------------------------
    # 图片加载（Qt 自带网络能力，不新增依赖）
    # ------------------------------------------------------------------

    def _load_image(self) -> None:
        if not self._fetch_images or not self._product.main_image:
            self._set_image_failed()
            return
        url = QUrl(self._product.main_image)
        if not url.isValid() or url.scheme() not in ("http", "https"):
            self._set_image_failed()
            return
        request = QNetworkRequest(url)
        request.setTransferTimeout(15_000)
        reply = self._network.get(request)
        reply.finished.connect(lambda r=reply: self._on_image_finished(r))

    def _on_image_finished(self, reply: QNetworkReply) -> None:
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self._set_image_failed()
            reply.deleteLater()
            return
        data = reply.readAll()
        reply.deleteLater()
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self._set_image_failed()
            return
        scaled = pixmap.scaled(
            IMAGE_SIZE,
            IMAGE_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.lbl_image.setText("")
        self.lbl_image.setPixmap(scaled)

    def _set_image_failed(self) -> None:
        self.lbl_image.setText("图片加载失败")

    def _on_action_clicked(self) -> None:
        if self._removed:
            self.restoreRequested.emit(self._product.product_id)
        else:
            self.removeRequested.emit(self._product.product_id)


class CollectWorker(QObject):
    """后台采集线程：在子线程内 asyncio.run(collect(...))，不冻结 UI。"""

    succeeded = Signal(list)
    failed = Signal(str)

    def __init__(self, keyword: str, target_count: int) -> None:
        super().__init__()
        self._keyword = keyword
        self._target_count = target_count

    @Slot()
    def run(self) -> None:
        try:
            import asyncio

            from profit_accounting_26.product_collection import collect

            results = asyncio.run(collect(self._keyword, self._target_count))
        except Exception as exc:  # noqa: BLE001 - UI 层统一提示
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.succeeded.emit(results)


class ProductCollectionPage(QWidget):
    """商品采集页：搜索 → 后台采集 → 卡片墙 → 移除/恢复 → 复制链接。"""

    def __init__(self, context=None) -> None:  # context 暂未使用，保持与其它页面签名一致
        super().__init__()
        self._products: list[CandidateProduct] = []
        self._states: dict[str, str] = {}
        self._cards: dict[str, ProductCard] = {}
        self._show_removed = False
        self._fetch_images = True
        self._thread: QThread | None = None
        self._worker: CollectWorker | None = None
        self._network = QNetworkAccessManager(self)
        self._notice = show_notice  # 测试环境可替换，避免模态弹窗阻塞

        self._build_ui()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(QLabel("搜索词", self))
        self.txt_keyword = QLineEdit(self)
        self.txt_keyword.setObjectName("txtCollectKeyword")
        self.txt_keyword.setPlaceholderText("输入搜索词，如 women bag")
        header.addWidget(self.txt_keyword, 1)
        header.addWidget(QLabel("目标数量", self))
        self.spin_target = QSpinBox(self)
        self.spin_target.setObjectName("spinCollectTarget")
        self.spin_target.setRange(1, 1000)
        self.spin_target.setValue(100)
        header.addWidget(self.spin_target)
        self.btn_start = QPushButton("开始采集", self)
        self.btn_start.setObjectName("btnStartCollect")
        self.btn_start.setProperty("primary", True)
        self.btn_start.clicked.connect(self.start_collect)
        header.addWidget(self.btn_start)
        root.addLayout(header)

        status_row = QHBoxLayout()
        status_row.setSpacing(16)
        self.lbl_status = QLabel("状态：待采集", self)
        self.lbl_status.setObjectName("lblCollectStatus")
        status_row.addWidget(self.lbl_status)
        self.lbl_stats = QLabel("已采集 0    保留 0    已移除 0", self)
        self.lbl_stats.setObjectName("lblCollectStats")
        status_row.addWidget(self.lbl_stats)
        status_row.addStretch(1)
        self.btn_toggle_removed = QPushButton("显示已移除", self)
        self.btn_toggle_removed.setObjectName("btnToggleRemoved")
        self.btn_toggle_removed.setCheckable(True)
        self.btn_toggle_removed.clicked.connect(self._on_toggle_removed)
        status_row.addWidget(self.btn_toggle_removed)
        self.btn_copy = QPushButton("复制保留链接", self)
        self.btn_copy.setObjectName("btnCopyKeptLinks")
        self.btn_copy.clicked.connect(self.copy_kept_links)
        status_row.addWidget(self.btn_copy)
        root.addLayout(status_row)

        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("collectScrollArea")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._container = _CardContainer()
        self._container.layoutRequested.connect(self._relayout_cards)
        self.scroll.setWidget(self._container)
        self._card_grid = QGridLayout(self._container)
        self._card_grid.setContentsMargins(0, 4, 0, 4)
        self._card_grid.setHorizontalSpacing(GRID_SPACING)
        self._card_grid.setVerticalSpacing(GRID_SPACING)
        root.addWidget(self.scroll, 1)

    # ------------------------------------------------------------------
    # 采集控制
    # ------------------------------------------------------------------

    def start_collect(self) -> None:
        keyword = self.txt_keyword.text().strip()
        if not keyword:
            self._notice(self, "提示", "请先输入搜索词。")
            return
        target_count = self.spin_target.value()
        self.btn_start.setEnabled(False)
        self.lbl_status.setText("状态：采集中")

        self._thread = QThread(self)
        self._worker = CollectWorker(keyword, target_count)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.succeeded.connect(self._on_collect_succeeded)
        self._worker.failed.connect(self._on_collect_failed)
        self._worker.succeeded.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_collect_succeeded(self, products: List[CandidateProduct]) -> None:
        self.load_results(products)
        self.btn_start.setEnabled(True)

    def _on_collect_failed(self, message: str) -> None:
        self.lbl_status.setText("状态：失败")
        self.btn_start.setEnabled(True)
        self._notice(self, "采集失败", message, level="error")

    # ------------------------------------------------------------------
    # 结果与卡片
    # ------------------------------------------------------------------

    def load_results(self, products: List[CandidateProduct]) -> None:
        """一次性载入采集结果并构建卡片墙（第一版不边采边显示）。"""
        for card in self._cards.values():
            card.deleteLater()
        self._cards = {}
        self._products = list(products)
        self._states = {p.product_id: KEEP for p in self._products}
        self._show_removed = False
        self.btn_toggle_removed.setChecked(False)
        self.btn_toggle_removed.setText("显示已移除")

        for product in self._products:
            card = ProductCard(product, self._network, self._fetch_images, self._container)
            card.removeRequested.connect(self.remove_product)
            card.restoreRequested.connect(self.restore_product)
            self._cards[product.product_id] = card

        self.lbl_status.setText("状态：已完成")
        self._update_stats()
        self._relayout_cards()

    def _relayout_cards(self) -> None:
        for card in self._cards.values():
            card.hide()
        while self._card_grid.count():
            item = self._card_grid.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
        visible = self._visible_cards()
        if not visible:
            return
        width = max(1, self._container.width())
        columns = max(1, (width + GRID_SPACING) // (CARD_WIDTH + GRID_SPACING))
        for index, card in enumerate(visible):
            row, col = divmod(index, columns)
            self._card_grid.addWidget(
                card, row, col, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            )
            card.show()

    def _visible_cards(self) -> list[ProductCard]:
        want_removed = self._show_removed
        return [
            card
            for product_id, card in self._cards.items()
            if (self._states[product_id] == REMOVED) == want_removed
        ]

    # ------------------------------------------------------------------
    # 移除 / 恢复 / 复制
    # ------------------------------------------------------------------

    def remove_product(self, product_id: str) -> None:
        if product_id not in self._states:
            return
        self._states[product_id] = REMOVED
        self._cards[product_id].set_removed_mode(True)
        self._update_stats()
        self._relayout_cards()

    def restore_product(self, product_id: str) -> None:
        if product_id not in self._states:
            return
        self._states[product_id] = KEEP
        self._cards[product_id].set_removed_mode(False)
        self._update_stats()
        self._relayout_cards()

    def _on_toggle_removed(self, checked: bool) -> None:
        self._show_removed = checked
        self.btn_toggle_removed.setText("隐藏已移除" if checked else "显示已移除")
        self._relayout_cards()

    def kept_links(self) -> str:
        """返回所有 KEEP 商品链接文本（一行一个 URL）。"""
        return "\n".join(
            product.product_url
            for product in self._products
            if self._states.get(product.product_id) == KEEP
        )

    def copy_kept_links(self) -> str:
        text = self.kept_links()
        self._write_clipboard(text)
        count = len([p for p in self._products if self._states.get(p.product_id) == KEEP])
        self._notice(self, "已复制", f"已复制 {count} 个保留商品链接。")
        return text

    def _write_clipboard(self, text: str) -> None:
        """写入系统剪贴板；测试环境可替换以避免阻塞。"""
        QApplication.clipboard().setText(text)

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def keep_count(self) -> int:
        return sum(1 for state in self._states.values() if state == KEEP)

    def removed_count(self) -> int:
        return sum(1 for state in self._states.values() if state == REMOVED)

    def _update_stats(self) -> None:
        self.lbl_stats.setText(
            f"已采集 {len(self._products)}    保留 {self.keep_count()}    已移除 {self.removed_count()}"
        )
