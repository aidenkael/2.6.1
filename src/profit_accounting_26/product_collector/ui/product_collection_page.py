"""商品采集页 V1.1 —— 独立版。

流程：平台/分类/搜索词（内置词库 + 可编辑自定义）+ 目标数量
→ 中文编辑框 + 英文预览框（自动映射）
→ 多搜索词顺序采集 → 卡片选择/移除/恢复 → 复制链接。

只做内存态 KEEP / REMOVED / selected，不落盘；关闭窗口后状态丢失。
静态布局由 ``ui/forms/product_collection.ui``（Qt Designer）管理，
本文件只负责动态行为与样式；采集核心在 ``collector_core``，
默认调用 ``business_source.collect_with_report``（可显式注入同签名 collector）。
不依赖 2.6.1 的 AppContext / 数据库 / 利润 / 物流 / 历史记录。
"""

from __future__ import annotations

import base64
import json
import webbrowser
from dataclasses import dataclass
from typing import Callable, List
from urllib.request import Request, urlopen

from PySide6.QtCore import QBuffer, QEvent, QIODevice, QObject, Qt, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication,
    QAbstractSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import keyword_engine
from ..collector_core.business_source import CollectionReport
from ..collector_core.models import CandidateProduct
from .ui_loader import load_ui

CARD_WIDTH = 250
IMAGE_SIZE = 210
TITLE_LINES = 3
TITLE_HEIGHT = 54
GRID_SPACING = 14
MAX_SEARCH_TERMS = 5
SEARCH_TERM_SEPARATOR = "；"

KEEP = "KEEP"
REMOVED = "REMOVED"

# ── 全局样式（仅此模块，不影响布局） ────────────────────────────
_PAGE_STYLESHEET = """
QWidget#formWidget {
    background: #f7f9fc;
}
QLabel {
    font-size: 13px;
    color: #333;
}
QComboBox, QLineEdit {
    padding: 4px 8px;
    border: 1px solid #d0d7e2;
    border-radius: 6px;
    font-size: 13px;
    background: #fff;
}
QSpinBox {
    padding: 4px 8px;
    border: 1px solid #d0d7e2;
    border-radius: 6px;
    font-size: 13px;
    background: #fff;
}
QPushButton {
    padding: 6px 18px;
    border: 1px solid #d0d7e2;
    border-radius: 6px;
    font-size: 13px;
    background: #fff;
    color: #333;
}
QPushButton:hover {
    background: #eef3fa;
}
QPushButton:disabled {
    color: #a5b0c0;
    background: #f0f3f7;
}
QPushButton[primary="true"] {
    background: #4a90d9;
    color: #fff;
    border: 1px solid #3a7bc8;
}
QPushButton[primary="true"]:hover {
    background: #3a7bc8;
}
QScrollArea {
    border: none;
}
QFrame#productCard {
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
}
QFrame#productCard[selected="true"] {
    border: 2px solid #4a90d9;
}
QLabel#productCardTitle {
    font-size: 12px;
    color: #333;
}
QLabel#productCardBadge {
    background: #4a90d9;
    color: #fff;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11px;
}
"""


@dataclass
class SearchTask:
    """单次搜索任务。"""

    display_cn: str
    actual_query: str
    source: str          # "builtin" / "custom"
    target_count: int = 0


def parse_search_terms(text: str, limit: int = MAX_SEARCH_TERMS) -> list[str]:
    """Parse the single, shared Chinese-semicolon search-term format."""
    return [part.strip() for part in (text or "").split(SEARCH_TERM_SEPARATOR) if part.strip()][:
        limit
    ]


def _show_notice(
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
    box.setIcon(
        {
            "info": QMessageBox.Icon.Information,
            "warning": QMessageBox.Icon.Warning,
            "error": QMessageBox.Icon.Critical,
        }.get(level, QMessageBox.Icon.Information)
    )
    box.addButton(ok_text, QMessageBox.ButtonRole.AcceptRole)
    box.exec()


# ── 多搜索词选择弹窗 ──────────────────────────────────────────

class KeywordSelectPopup(QWidget):
    """多搜索词勾选弹窗：左列分类 / 右列勾选具体词（中文显示）。

    勾选状态跨分类保留；确认时按用户实际勾选顺序返回中文显示词。
    """

    keywordsSelected = Signal(list)

    def __init__(self, parent: QWidget | None = None, initial_category: str | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setFixedSize(620, 420)
        # 用户实际勾选顺序（跨分类保留），值均为中文显示文本
        self._ordered_selection: list[str] = []
        self._term_items: list[tuple[str, QListWidgetItem]] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)

        split = QHBoxLayout()
        self._cat_list = QListWidget()
        self._cat_list.setFixedWidth(200)
        self._cat_list.currentRowChanged.connect(self._on_cat_clicked)
        split.addWidget(self._cat_list)

        self._term_list = QListWidget()
        self._term_list.itemChanged.connect(self._on_item_changed)
        split.addWidget(self._term_list, 1)
        outer.addLayout(split, 1)

        btn_row = QHBoxLayout()
        btn_confirm = QPushButton("确定")
        btn_confirm.clicked.connect(self._on_confirm)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.close)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_confirm)
        outer.addLayout(btn_row)

        categories = keyword_engine.list_categories()
        self._cat_list.addItems(categories)
        if categories:
            initial_row = categories.index(initial_category) if initial_category in categories else 0
            self._cat_list.setCurrentRow(initial_row)

    def _on_cat_clicked(self, row: int) -> None:
        categories = keyword_engine.list_categories()
        if row < 0 or row >= len(categories):
            return
        # 加载新分类；勾选状态由 _ordered_selection 跨分类保留
        cat = categories[row]
        self._term_list.clear()
        self._term_items = []
        for display, actual in keyword_engine.category_cn_terms(cat):
            item = QListWidgetItem(display)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if display in self._ordered_selection:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, actual)
            self._term_list.addItem(item)
            self._term_items.append((display, item))

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        """按勾选/取消实时维护有序选择列表（勾选顺序即执行顺序）。"""
        text = item.text()
        if item.checkState() == Qt.CheckState.Checked:
            if text not in self._ordered_selection and len(self._ordered_selection) >= MAX_SEARCH_TERMS:
                self._term_list.blockSignals(True)
                item.setCheckState(Qt.CheckState.Unchecked)
                self._term_list.blockSignals(False)
                _show_notice(self, "提示", f"最多同时选择 {MAX_SEARCH_TERMS} 个搜索词。", level="warning")
                return
            if text not in self._ordered_selection:
                self._ordered_selection.append(text)
        elif text in self._ordered_selection:
            self._ordered_selection.remove(text)

    def _on_confirm(self) -> None:
        self.keywordsSelected.emit(list(self._ordered_selection))
        self.close()


# ── 商品卡片 ──────────────────────────────────────────────────

class ProductCard(QFrame):
    """单张商品卡片：主图 + 标题（最多 3 行）+ 选中角标 + 风险标签。

    左键单击选中、右键单击取消选中；双击图片或标题执行对应动作。
    """

    selectionRequested = Signal(str, bool)
    titleActivated = Signal(str)
    imageSearchRequested = Signal(str)

    def __init__(
        self,
        product: CandidateProduct,
        network: QNetworkAccessManager,
        fetch_images: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._product = product
        self._selected = False
        self._fetch_images = fetch_images
        self.setObjectName("productCard")
        self.setProperty("card", True)
        self.setProperty("selected", False)
        self.setFixedWidth(CARD_WIDTH)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.lbl_image = QLabel(self)
        self.lbl_image.setObjectName("productCardImage")
        self.lbl_image.setFixedSize(IMAGE_SIZE, IMAGE_SIZE)
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_image.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.lbl_image.setStyleSheet(
            "background:#f1f5fa;border:1px solid #dbe5f1;border-radius:8px;color:#8a97ab;"
        )
        layout.addWidget(self.lbl_image, 0, Qt.AlignmentFlag.AlignHCenter)

        self.lbl_title = QLabel(product.title, self)
        self.lbl_title.setObjectName("productCardTitle")
        self.lbl_title.setWordWrap(True)
        # 标题最多 3 行，超长部分截断，不拉长卡片
        self.lbl_title.setFixedHeight(TITLE_HEIGHT)
        self.lbl_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.lbl_title.setToolTip(product.title)
        layout.addWidget(self.lbl_title)

        # 风险标签（初始隐藏）
        self.lbl_risk = QLabel(self)
        self.lbl_risk.setObjectName("productCardRisk")
        self.lbl_risk.setWordWrap(True)
        self.lbl_risk.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.lbl_risk.setStyleSheet(
            "background:#FFF4E5;color:#C77600;border:1px solid #FFD59E;"
            "border-radius:4px;padding:2px 6px;font-size:11px;"
        )
        self.lbl_risk.hide()
        layout.addWidget(self.lbl_risk)

        # 右上角"已选"角标（绝对定位，不参与布局）
        self.lbl_badge = QLabel("✓ 已选", self)
        self.lbl_badge.setObjectName("productCardBadge")
        self.lbl_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.lbl_badge.hide()

        self._network = network
        self._load_image()

    # ------------------------------------------------------------------
    # 对外状态
    # ------------------------------------------------------------------

    @property
    def product(self) -> CandidateProduct:
        return self._product

    @property
    def selected(self) -> bool:
        return self._selected

    @property
    def title_line_limit(self) -> int:
        return TITLE_LINES

    def set_selected(self, selected: bool) -> None:
        """切换选中外观；不触发重排、不改变 KEEP / REMOVED。"""
        if self._selected == selected:
            return
        self._selected = selected
        self.setProperty("selected", selected)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.lbl_badge.setVisible(selected)

    def set_risk_labels(self, labels: list[str], result: str = "") -> None:
        """设置风险标签显示。"""
        if not labels:
            self.lbl_risk.hide()
            return
        # 显示格式：[禁止] 带电, 电池充电 或 [复核] 品牌/IP复核
        prefix = "⛔" if result == "禁止" else "⚠️"
        text = f"{prefix} {', '.join(labels)}"
        self.lbl_risk.setText(text)
        self.lbl_risk.setToolTip(text)
        if result == "禁止":
            self.lbl_risk.setStyleSheet(
                "background:#FEE2E2;color:#DC2626;border:1px solid #FCA5A5;"
                "border-radius:4px;padding:2px 6px;font-size:11px;"
            )
        else:
            self.lbl_risk.setStyleSheet(
                "background:#FFF4E5;color:#C77600;border:1px solid #FFD59E;"
                "border-radius:4px;padding:2px 6px;font-size:11px;"
            )
        self.lbl_risk.show()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        super().resizeEvent(event)
        self.lbl_badge.move(self.width() - self.lbl_badge.width() - 8, 8)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        if event.button() == Qt.MouseButton.LeftButton:
            self.selectionRequested.emit(self._product.product_id, True)
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self.selectionRequested.emit(self._product.product_id, False)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        if event.button() == Qt.MouseButton.LeftButton:
            position = event.position().toPoint()
            if self.lbl_image.geometry().contains(position):
                self.imageSearchRequested.emit(self._product.main_image)
                event.accept()
                return
            if self.lbl_title.geometry().contains(position):
                self.titleActivated.emit(self._product.product_url)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

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


# ── 采集 Worker ───────────────────────────────────────────────

class CollectWorker(QObject):
    """后台采集线程：在子线程内 asyncio.run(collect_with_report(...))。"""

    reportReady = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        keyword: str,
        target_count: int,
        collector: Callable | None = None,
        seed: int | None = None,
        log_dir: str | None = None,
    ) -> None:
        super().__init__()
        self._keyword = keyword
        self._target_count = target_count
        self._collector = collector
        self._seed = seed
        self._log_dir = log_dir

    @Slot()
    def run(self) -> None:
        try:
            import asyncio

            collector = self._collector
            if collector is None:
                from ..collector_core.business_source import collect_with_report

                collector = collect_with_report
            kwargs: dict = {}
            if self._seed is not None:
                kwargs["seed"] = self._seed
            if self._log_dir is not None:
                kwargs["log_dir"] = self._log_dir
            report = asyncio.run(
                collector(self._keyword, self._target_count, **kwargs)
            )
        except Exception:  # noqa: BLE001 - UI 层统一提示，细节已写日志
            self.failed.emit("采集失败\n未获取到有效商品。\n详细原因已记录日志。")
            return
        self.reportReady.emit(report)


# ── 主页面 ────────────────────────────────────────────────────

class ImageSearchWorker(QObject):
    """Upload one card image to 1688 away from the Qt GUI thread."""

    ready = Signal(str)
    failed = Signal(str)

    def __init__(self, image_url: str) -> None:
        super().__init__()
        self._image_url = image_url

    @Slot()
    def run(self) -> None:
        try:
            if not self._image_url:
                raise RuntimeError("商品图片不可用")
            request = Request(self._image_url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=20) as response:  # nosec B310 - selected product image
                image_data = response.read()
            image = QImage.fromData(image_data)
            if image.isNull():
                raise RuntimeError("商品图片无法读取")
            if max(image.width(), image.height()) > 1280:
                image = image.scaled(1280, 1280, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
            side = max(image.width(), image.height())
            square = QImage(side, side, QImage.Format.Format_RGB32)
            square.fill(Qt.GlobalColor.white)
            painter = QPainter(square)
            painter.drawImage((side - image.width()) // 2, (side - image.height()) // 2, image)
            painter.end()
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            if not square.save(buffer, "JPEG", 85):
                raise RuntimeError("商品图片压缩失败")
            image_b64 = base64.b64encode(bytes(buffer.data())).decode("ascii")
            payload = json.dumps({"imgBase64": image_b64, "searchType": "imageSearch",
                                  "appName": "pcErpImage", "urlType": "main"}).encode("utf-8")
            upload = Request("https://search.1688.com/service/uploadErpImgSearch", data=payload,
                             headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(upload, timeout=30) as response:  # nosec B310 - fixed 1688 endpoint
                data = json.loads(response.read().decode("utf-8"))
            image_id = data.get("data", {}).get("imageId", "")
            if data.get("code") != 0 or not image_id:
                raise RuntimeError(data.get("errMsg") or "1688 图片上传失败")
            self.ready.emit("https://air.1688.com/kapp/1688-search/pc-image-search/"
                            f"?tab=imageSearch&showP4P=false&odTab=consign&showBid=false&imageId={image_id}")
        except Exception as exc:  # noqa: BLE001 - only a short UI notice is required
            self.failed.emit(str(exc))


class ProductCollectionPage(QWidget):
    """商品采集页 V1.1：中英文映射 + 多搜索词顺序采集 + 卡片批量操作 + AI风险检测。

    独立创建：``ProductCollectionPage()``
    也可注入同签名采集函数（async (keyword, target) -> CollectionReport）：
    ``ProductCollectionPage(collector=collect_with_report)``
    """

    def __init__(self, collector: Callable | None = None) -> None:
        super().__init__()
        self._collector = collector
        self._log_dir: str | None = None
        self._api_profile_store = None  # 由宿主注入
        self._products: list[CandidateProduct] = []
        self._states: dict[str, str] = {}
        self._selected_ids: set[str] = set()
        self._cards: dict[str, ProductCard] = {}
        self._fetch_images = True
        self._thread: QThread | None = None
        self._worker: CollectWorker | None = None
        self._image_search_thread: QThread | None = None
        self._image_search_worker: ImageSearchWorker | None = None
        self._network = QNetworkAccessManager(self)
        self._notice = _show_notice  # 测试环境可替换，避免模态弹窗阻塞

        # 多关键词顺序采集
        self._search_tasks: list[SearchTask] = []
        self._current_task_idx = 0
        self._all_products: list[CandidateProduct] = []
        self._seen_ids: set[str] = set()
        self._task_statuses: list[str] = []

        # 已移除视图
        self._showing_removed = False

        # AI 风险检测
        self._title_risk_thread: QThread | None = None
        self._title_risk_worker: QObject | None = None
        self._image_risk_thread: QThread | None = None
        self._image_risk_worker: QObject | None = None
        self._title_risk_service = None
        self._image_risk_service = None

        self._load_ui()

    def set_log_dir(self, log_dir: str | None) -> None:
        """注入日志目录（由宿主应用调用）。"""
        self._log_dir = log_dir

    def set_api_profile_store(self, profile_store) -> None:
        """注入 API Profile Store（由宿主应用调用）。"""
        self._api_profile_store = profile_store
        # 初始化风险检测服务
        if profile_store is not None:
            from ..title_risk_scan import TitleRiskScanService
            from ..image_risk_scan import ImageRiskScanService
            self._title_risk_service = TitleRiskScanService(profile_store)
            self._image_risk_service = ImageRiskScanService(profile_store)
        self._update_risk_buttons_state()

    # ------------------------------------------------------------------
    # UI 构建（从 .ui 加载静态布局）
    # ------------------------------------------------------------------

    def _load_ui(self) -> None:
        """加载 .ui 静态布局，绑定控件引用和信号。"""
        form = load_ui(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(form)

        form.setStyleSheet(_PAGE_STYLESHEET)

        # 映射 .ui 控件到实例属性
        self.cmb_platform = form.findChild(QWidget, "cmbPlatform")
        self.cmb_category = form.findChild(QWidget, "cmbCategory")
        self.txt_cn = form.findChild(QLineEdit, "txtKeywordCN")
        self.txt_en = form.findChild(QLineEdit, "txtKeywordEN")
        self.btn_select_kw = form.findChild(QWidget, "btnSelectKeywords")
        self.btn_random_idea = form.findChild(QWidget, "btnRandomIdea")
        self.spin_per_keyword = form.findChild(QWidget, "spinPerKeyword")
        self.spin_target = form.findChild(QWidget, "spinTarget")
        self.btn_start = form.findChild(QWidget, "btnCollect")
        self.lbl_status = form.findChild(QWidget, "lblStatus")
        self.lbl_total = form.findChild(QWidget, "lblTotal")
        self.lbl_selected = form.findChild(QWidget, "lblSelected")
        self.lbl_sampling = form.findChild(QWidget, "lblSampling")
        self.btn_title_check = form.findChild(QWidget, "btnTitleCheck")
        self.btn_infringement_check = form.findChild(QWidget, "btnInfringementCheck")
        self.btn_copy = form.findChild(QWidget, "btnCopyLinks")
        self.btn_keep_only = form.findChild(QWidget, "btnKeepOnlySelected")
        self.btn_remove_selected = form.findChild(QWidget, "btnRemoveSelected")
        self.btn_select_all = form.findChild(QWidget, "btnSelectAll")
        self.btn_view_removed = form.findChild(QWidget, "btnViewRemoved")
        self.btn_restore = form.findChild(QWidget, "btnRestoreSelected")
        self.scroll = form.findChild(QScrollArea, "scrollProducts")
        self._container = form.findChild(QWidget, "productGridHost")

        # 卡片网格布局
        self._card_grid = QGridLayout(self._container)
        self._card_grid.setContentsMargins(0, 4, 0, 4)
        self._card_grid.setHorizontalSpacing(GRID_SPACING)
        self._card_grid.setVerticalSpacing(GRID_SPACING)

        # 每词数量可编辑；总数量是只读、可读的派生值。
        self.spin_per_keyword.setRange(1, 160)
        self.spin_per_keyword.setSingleStep(10)
        self.spin_per_keyword.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_target.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_target.setMaximum(1_000_000)
        self.spin_target.setReadOnly(True)
        self.spin_target.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # 分类初始化（signals blocked，不触发 _on_category_changed 自动填充）
        self.cmb_category.blockSignals(True)
        self.cmb_category.addItems(keyword_engine.list_categories())
        self.cmb_category.blockSignals(False)

        # 事件绑定
        self.cmb_category.activated.connect(self._on_category_changed)
        self.btn_random_idea.clicked.connect(self._on_random_idea)
        self.btn_select_kw.clicked.connect(self._on_select_keywords)
        self.txt_cn.textEdited.connect(self._on_keywords_edited)
        self.spin_per_keyword.valueChanged.connect(self._update_total_target)
        self.btn_start.clicked.connect(self.start_collect)
        self.btn_copy.clicked.connect(self.copy_kept_links)
        self.btn_keep_only.clicked.connect(self.keep_only_selected)
        self.btn_remove_selected.clicked.connect(self.remove_selected)
        self.btn_select_all.clicked.connect(self.select_all_visible)
        self.btn_view_removed.clicked.connect(self._toggle_removed_view)
        self.btn_restore.clicked.connect(self._restore_selected)

        # 标题检测 / 图片检测
        self.btn_title_check.clicked.connect(self._on_title_risk_check)
        self.btn_infringement_check.clicked.connect(self._on_image_risk_check)
        self._update_risk_buttons_state()
        self._update_selection_buttons()

        # 容器尺寸变化时重排卡片
        self._container.installEventFilter(self)
        self.spin_target.installEventFilter(self)
        self.btn_random_idea.installEventFilter(self)
        self._update_total_target()

    def eventFilter(self, obj, event):  # noqa: N802 (Qt 命名)
        if obj is self._container and event.type() == QEvent.Type.Resize:
            self._relayout_cards()
        if obj is self.spin_target and event.type() in (QEvent.Type.Wheel, QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return True
        if obj is self.btn_random_idea and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.RightButton:
                self.txt_cn.clear()
                self.txt_en.clear()
                event.accept()
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # 平台
    # ------------------------------------------------------------------

    def _is_valid_platform(self) -> bool:
        """仅 AliExpress Business 可执行采集。"""
        return self.cmb_platform.currentText() == "AliExpress Business"

    # ------------------------------------------------------------------
    # 分类 / 搜索词 / 中英文映射
    # ------------------------------------------------------------------

    def _on_category_changed(self, _index: int) -> None:
        """分类控件就是现有“分类 + 搜索词”弹层的唯一可见入口。"""
        self._on_select_keywords()

    def _on_keywords_edited(self) -> None:
        """Manual input uses the same Chinese-semicolon and five-term rule."""
        text = self.txt_cn.text()
        parts = text.split(SEARCH_TERM_SEPARATOR)
        effective_count = 0
        cutoff = None
        for index, part in enumerate(parts):
            if not part.strip():
                continue
            effective_count += 1
            if effective_count > MAX_SEARCH_TERMS:
                cutoff = sum(len(item) + len(SEARCH_TERM_SEPARATOR) for item in parts[:index])
                break
        if cutoff is not None:
            self.txt_cn.blockSignals(True)
            self.txt_cn.setText(text[:cutoff])
            self.txt_cn.blockSignals(False)
        self._update_en_preview()

    def _set_search_terms(self, terms: list[str]) -> None:
        self.txt_cn.setText(SEARCH_TERM_SEPARATOR.join(terms[:MAX_SEARCH_TERMS]))
        self._update_en_preview()

    def _update_total_target(self) -> None:
        self.spin_target.setValue(len(parse_search_terms(self.txt_cn.text())) * self.spin_per_keyword.value())

    def _update_en_preview(self) -> None:
        """根据中文框内容实时更新英文预览框。"""
        text = self.txt_cn.text()
        pairs = keyword_engine.resolve_keywords_batch(text)
        if pairs:
            self.txt_en.setText("；".join(show for show, _actual in pairs))
        else:
            self.txt_en.clear()
        self._update_total_target()

    def _on_random_idea(self) -> None:
        """随机灵感：追加一个随机搜索词到中文输入框（不联网）。"""
        category, en_term = keyword_engine.random_idea()
        # 查找对应中文词
        cn_display = ""
        for d in keyword_engine.DIRECTIONS:
            if d["cn"] == category:
                for cn_w, en_w in d["items"]:
                    if en_w == en_term:
                        cn_display = cn_w
                        break
                break
        terms = parse_search_terms(self.txt_cn.text())
        if len(terms) >= MAX_SEARCH_TERMS:
            self._notice(self, "提示", f"最多同时使用 {MAX_SEARCH_TERMS} 个搜索词。", level="warning")
            return
        if cn_display:
            self._set_search_terms(terms + [cn_display])

    def _on_select_keywords(self) -> None:
        """打开多搜索词勾选弹窗。"""
        popup = KeywordSelectPopup(self, initial_category=self.cmb_category.currentText())
        popup.keywordsSelected.connect(self._on_keywords_picked)
        pos = self.cmb_category.mapToGlobal(self.cmb_category.rect().bottomLeft())
        popup.move(pos)
        popup.show()

    def _on_keywords_picked(self, keywords: list[str]) -> None:
        """弹窗确认后，将选中的词追加到中文输入框。"""
        if not keywords:
            return
        self._set_search_terms(keywords)

    def current_search_keyword(self) -> str:
        """返回第一个搜索词的实际搜索值（兼容单词场景）。"""
        text = self.txt_cn.text().strip()
        if not text:
            return ""
        parts = parse_search_terms(text)
        if not parts:
            return ""
        _display, actual = keyword_engine.resolve_cn_keyword(parts[0])
        return actual

    # ------------------------------------------------------------------
    # 采集控制
    # ------------------------------------------------------------------

    def start_collect(self) -> None:
        """解析多搜索词，按分配目标串行采集。"""
        if not self._is_valid_platform():
            self._notice(
                self, "提示",
                "当前平台暂未接入，请选择 AliExpress Business。",
                level="warning",
            )
            return

        self._update_en_preview()
        per_keyword_count = self.spin_per_keyword.value()
        cn_text = self.txt_cn.text().strip()
        if not cn_text:
            self._notice(self, "提示", "请先选择或输入搜索词。")
            return

        # 解析搜索词
        parsed = keyword_engine.resolve_keywords_batch(cn_text)
        if not parsed:
            self._notice(self, "提示", "请先选择或输入搜索词。")
            return

        # 每个词严格使用用户设置的同一个目标数量；不再平均分配总数。
        cn_parts = parse_search_terms(cn_text)
        tasks: list[SearchTask] = []
        for i, (_show, actual) in enumerate(parsed[:MAX_SEARCH_TERMS]):
            source = "custom" if _show.startswith("—") else "builtin"
            cn_part = cn_parts[i] if i < len(cn_parts) else actual
            tasks.append(
                SearchTask(
                    display_cn=cn_part,
                    actual_query=actual,
                    source=source,
                    target_count=per_keyword_count,
                )
            )

        self._search_tasks = tasks
        self._current_task_idx = 0
        self._all_products = []
        self._seen_ids = set()
        self._task_statuses = []

        self.btn_start.setEnabled(False)
        self.lbl_status.setText("采集中…")
        self._update_task_status_label()
        self._start_next_task()

    def _update_task_status_label(self) -> None:
        total = len(self._search_tasks)
        if total > 1:
            idx = min(self._current_task_idx + 1, total)
            cn = self._search_tasks[self._current_task_idx].display_cn
            self.lbl_status.setText(f"正在执行 {idx}/{total}：{cn}")

    def _start_next_task(self) -> None:
        if self._current_task_idx >= len(self._search_tasks):
            self._finish_all_tasks()
            return
        task = self._search_tasks[self._current_task_idx]

        self._thread = QThread(self)
        self._worker = CollectWorker(
            task.actual_query, task.target_count, self._collector,
            log_dir=self._log_dir,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.reportReady.connect(self._on_task_report)
        self._worker.failed.connect(self._on_task_failed)
        self._worker.reportReady.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_task_report(self, report: CollectionReport) -> None:
        """按顺序累积，跨关键词 product_id 去重。"""
        for p in report.products:
            if p.product_id not in self._seen_ids:
                self._seen_ids.add(p.product_id)
                self._all_products.append(p)
        self._task_statuses.append(report.status)
        self._current_task_idx += 1
        self._start_next_task()

    def _on_task_failed(self, message: str) -> None:
        self._task_statuses.append("failed")
        self._current_task_idx += 1
        self._start_next_task()

    def _finish_all_tasks(self) -> None:
        self.btn_start.setEnabled(True)
        products = self._all_products
        total_target = sum(t.target_count for t in self._search_tasks)

        if not products:
            status = "failed"
        elif (
            all(s == "success" for s in self._task_statuses)
            and len(products) >= total_target
        ):
            status = "success"
        else:
            status = "partial"

        self.load_results(products)
        if status == "failed":
            self.lbl_status.setText("采集失败")
        elif status == "partial":
            self.lbl_status.setText("部分完成")
        else:
            self.lbl_status.setText("已完成")

        title, text, level = self._summary_for_multi_task(
            status, products, total_target,
        )
        self._notice(self, title, text, level=level)

    @staticmethod
    def _summary_for_multi_task(
        status: str,
        products: list[CandidateProduct],
        total_target: int,
    ) -> tuple[str, str, str]:
        if status == "success":
            return (
                "采集完成",
                f"共获得 {len(products)} 个商品。",
                "info",
            )
        if status == "partial":
            return (
                "采集未完全完成",
                f"目标 {total_target}，实际获得 {len(products)} 个商品。\n"
                f"详细原因已记录日志。",
                "warning",
            )
        return (
            "采集失败",
            "未获取到有效商品。\n详细原因已记录日志。",
            "error",
        )

    @staticmethod
    def _summary_for_report(report: CollectionReport) -> tuple[str, str, str]:
        """按三态生成用户可读弹窗文案（不暴露 API/JSON/堆栈细节）。"""
        if report.status == "success":
            return (
                "采集完成",
                (
                    f"本次随机扫描 {report.actual_pages} 页，"
                    f"从 {report.candidate_count} 个有效候选中"
                    f"抽取 {len(report.products)} 个商品。\n"
                    f"用时 {report.elapsed_seconds:.1f} 秒。"
                ),
                "info",
            )
        if report.status == "partial":
            return (
                "采集未完全完成",
                (
                    f"计划扫描 {report.planned_pages} 页，"
                    f"实际完成 {report.actual_pages} 页，"
                    f"已获得 {len(report.products)} 个商品。\n"
                    f"详细原因已记录日志。"
                ),
                "warning",
            )
        return (
            "采集失败",
            "未获取到有效商品。\n详细原因已记录日志。",
            "error",
        )

    # ------------------------------------------------------------------
    # 结果与卡片
    # ------------------------------------------------------------------

    def _open_product_url(self, product_url: str) -> None:
        if product_url:
            webbrowser.open(product_url)

    def _start_1688_image_search(self, image_url: str) -> None:
        if not image_url:
            self._notice(self, "提示", "当前商品没有可用图片。", level="warning")
            return
        if self._image_search_thread is not None and self._image_search_thread.isRunning():
            self._notice(self, "提示", "图片搜图正在进行，请稍候。", level="warning")
            return
        self._image_search_thread = QThread(self)
        self._image_search_worker = ImageSearchWorker(image_url)
        self._image_search_worker.moveToThread(self._image_search_thread)
        self._image_search_thread.started.connect(self._image_search_worker.run)
        self._image_search_worker.ready.connect(self._open_1688_result)
        self._image_search_worker.failed.connect(self._on_1688_image_search_failed)
        self._image_search_worker.ready.connect(self._image_search_thread.quit)
        self._image_search_worker.failed.connect(self._image_search_thread.quit)
        self._image_search_thread.finished.connect(self._image_search_worker.deleteLater)
        self._image_search_thread.finished.connect(self._image_search_thread.deleteLater)
        self._image_search_thread.finished.connect(
            lambda thread=self._image_search_thread: self._clear_image_search_task(thread)
        )
        self._image_search_thread.start()

    def _open_1688_result(self, result_url: str) -> None:
        webbrowser.open(result_url)

    def _on_1688_image_search_failed(self, _message: str) -> None:
        self._notice(self, "提示", "1688 图片搜图失败。", level="warning")

    def _clear_image_search_task(self, finished_thread: QThread) -> None:
        """仅清理刚结束的搜图任务，允许下一次创建新的 worker/thread。"""
        if self._image_search_thread is finished_thread:
            self._image_search_thread = None
            self._image_search_worker = None

    def load_results(self, products: list[CandidateProduct]) -> None:
        """一次性载入采集结果并构建卡片墙。"""
        for card in self._cards.values():
            card.deleteLater()
        self._cards = {}
        self._products = list(products)
        self._states = {p.product_id: KEEP for p in self._products}
        self._selected_ids = set()
        self._showing_removed = False
        self.btn_restore.setVisible(False)
        self.btn_view_removed.setText(f"查看已移除（0）")

        for product in self._products:
            card = ProductCard(product, self._network, self._fetch_images, self._container)
            card.selectionRequested.connect(self.set_selection)
            card.titleActivated.connect(self._open_product_url)
            card.imageSearchRequested.connect(self._start_1688_image_search)
            self._cards[product.product_id] = card

        self._update_stats()
        self._update_selection_buttons()
        self._update_risk_buttons_state()
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
        if self._showing_removed:
            return [
                c for pid, c in self._cards.items()
                if self._states[pid] == REMOVED
            ]
        return [
            card
            for product_id, card in self._cards.items()
            if self._states[product_id] == KEEP
        ]

    def _relayout_preserving_scroll(self) -> None:
        """重排卡片前保存滚动位置，布局完成后恢复，避免跳到页面底部。"""
        bar = self.scroll.verticalScrollBar()
        saved = bar.value()
        self._relayout_cards()
        QTimer.singleShot(0, lambda: bar.setValue(saved))

    # ------------------------------------------------------------------
    # 已移除视图
    # ------------------------------------------------------------------

    def _toggle_removed_view(self) -> None:
        self._showing_removed = not self._showing_removed
        self.clear_selection()
        if self._showing_removed:
            self.btn_view_removed.setText("返回商品视图")
            self.btn_restore.setVisible(True)
        else:
            self.btn_view_removed.setText(
                f"查看已移除（{self.removed_count()}）"
            )
            self.btn_restore.setVisible(False)
        self._update_stats()
        self._update_selection_buttons()
        self._relayout_cards()

    def _restore_selected(self) -> None:
        """将已移除视图中选中的商品恢复为 KEEP。"""
        for pid in list(self._selected_ids):
            if self._states.get(pid) == REMOVED:
                self._states[pid] = KEEP
        self._finish_batch_action()
        self._showing_removed = False
        self.btn_restore.setVisible(False)
        self.btn_view_removed.setText(
            f"查看已移除（{self.removed_count()}）"
        )
        self._relayout_cards()

    # ------------------------------------------------------------------
    # 选择与批量动作
    # ------------------------------------------------------------------

    def toggle_selection(self, product_id: str) -> None:
        """单击卡片：只切换 selected，不改变 KEEP / REMOVED，不重排。"""
        if product_id not in self._cards:
            return
        if product_id in self._selected_ids:
            self._selected_ids.discard(product_id)
            self._cards[product_id].set_selected(False)
        else:
            self._selected_ids.add(product_id)
            self._cards[product_id].set_selected(True)
        self._update_stats()
        self._update_selection_buttons()

    def set_selection(self, product_id: str, selected: bool) -> None:
        """按指定状态更新卡片选择；重复左键选中保持选中。"""
        if product_id not in self._cards:
            return
        if selected:
            self._selected_ids.add(product_id)
        else:
            self._selected_ids.discard(product_id)
        self._cards[product_id].set_selected(selected)
        self._update_stats()
        self._update_selection_buttons()

    def select_all_visible(self) -> None:
        """全部选择：只选择当前可见的 KEEP 商品（已移除商品绝不进入选择）。

        已移除视图中 _visible_cards() 返回 REMOVED 商品，
        此处以 KEEP 判断兜底，保证 REMOVED 不被选中。
        """
        for card in self._visible_cards():
            pid = card.product.product_id
            if self._states.get(pid) != KEEP:
                continue
            if pid not in self._selected_ids:
                self._selected_ids.add(pid)
                card.set_selected(True)
        self._update_stats()
        self._update_selection_buttons()

    def keep_only_selected(self) -> None:
        """仅保留选中：当前 KEEP 中未选中的全部转为 REMOVED。"""
        if not self._selected_ids:
            return
        for product_id, state in list(self._states.items()):
            if state == KEEP and product_id not in self._selected_ids:
                self._states[product_id] = REMOVED
        self._finish_batch_action()

    def remove_selected(self) -> None:
        """移除选中：选中的 KEEP 商品转为 REMOVED。"""
        if not self._selected_ids:
            return
        for product_id in self._selected_ids:
            if self._states.get(product_id) == KEEP:
                self._states[product_id] = REMOVED
        self._finish_batch_action()

    def clear_selection(self) -> None:
        """取消选择：只清空 selected，不改变 KEEP / REMOVED。"""
        for product_id in list(self._selected_ids):
            card = self._cards.get(product_id)
            if card is not None:
                card.set_selected(False)
        self._selected_ids = set()
        self._update_stats()
        self._update_selection_buttons()

    def _finish_batch_action(self) -> None:
        """批量动作收尾：清空选择、更新统计、保滚动位置重排。"""
        for product_id in list(self._selected_ids):
            card = self._cards.get(product_id)
            if card is not None:
                card.set_selected(False)
        self._selected_ids = set()
        self._update_stats()
        self._update_selection_buttons()
        self._relayout_preserving_scroll()

    def _update_selection_buttons(self) -> None:
        has_selection = bool(self._selected_ids)
        self.btn_keep_only.setEnabled(has_selection and not self._showing_removed)
        self.btn_remove_selected.setEnabled(has_selection and not self._showing_removed)
        self.btn_restore.setEnabled(has_selection and self._showing_removed)
        # 全部选择只作用于可见 KEEP 商品，已移除视图下禁用
        self.btn_select_all.setEnabled(not self._showing_removed)

    # ------------------------------------------------------------------
    # 复制链接
    # ------------------------------------------------------------------

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

    def selected_count(self) -> int:
        return len(self._selected_ids)

    def _update_stats(self) -> None:
        if self._showing_removed:
            self.lbl_total.setText(f"已移除 {self.removed_count()}")
        else:
            self.lbl_total.setText(f"商品 {self.keep_count()}")
        self.lbl_selected.setText(f"已选 {self.selected_count()}")
        self.btn_view_removed.setEnabled(self.removed_count() > 0)
        self.btn_view_removed.setText(
            f"查看已移除（{self.removed_count()}）"
            if not self._showing_removed
            else "返回商品视图"
        )

    # ------------------------------------------------------------------
    # AI 风险检测
    # ------------------------------------------------------------------

    def _update_risk_buttons_state(self) -> None:
        """根据 API 配置状态启用/禁用风险检测按钮。"""
        has_products = bool(self._products)
        has_store = self._api_profile_store is not None
        self.btn_title_check.setEnabled(has_products and has_store)
        self.btn_infringement_check.setEnabled(has_products and has_store)

    def _on_title_risk_check(self) -> None:
        """标题风险检测按钮点击。"""
        if self._title_risk_service is None:
            self._notice(self, "提示", "标题风险检测尚未配置，请先在设置中绑定文字API。", level="warning")
            return
        if not self._products:
            self._notice(self, "提示", "没有可检测的商品。")
            return
        if self._title_risk_thread is not None and self._title_risk_thread.isRunning():
            self._notice(self, "提示", "标题风险检测正在进行中，请稍候。", level="warning")
            return

        self.lbl_status.setText("标题风险检测中...")
        self.btn_title_check.setEnabled(False)

        # 构建标题列表
        titles = [
            {"id": p.product_id, "title": p.title}
            for p in self._products
            if self._states.get(p.product_id) == KEEP
        ]

        # 启动后台线程
        self._title_risk_thread = QThread(self)
        self._title_risk_worker = _TitleRiskWorker(self._title_risk_service, titles)
        self._title_risk_worker.moveToThread(self._title_risk_thread)
        self._title_risk_thread.started.connect(self._title_risk_worker.run)
        self._title_risk_worker.finished.connect(self._on_title_risk_finished)
        self._title_risk_worker.finished.connect(self._title_risk_thread.quit)
        self._title_risk_thread.finished.connect(self._title_risk_worker.deleteLater)
        self._title_risk_thread.finished.connect(self._title_risk_thread.deleteLater)
        self._title_risk_thread.finished.connect(
            lambda: setattr(self, '_title_risk_thread', None)
        )
        self._title_risk_thread.start()

    def _on_title_risk_finished(self, risks: list, error: str) -> None:
        """标题风险检测完成回调。"""
        self.btn_title_check.setEnabled(True)
        if error:
            self.lbl_status.setText("标题检测失败")
            self._notice(self, "标题风险检测失败", error, level="error")
            return

        # 更新卡片风险标签
        risk_map = {r.product_id: r for r in risks}
        for pid, card in self._cards.items():
            if pid in risk_map:
                risk = risk_map[pid]
                card.set_risk_labels(risk.labels, risk.result)
            else:
                card.set_risk_labels([])

        self.lbl_status.setText(f"标题检测完成，发现 {len(risks)} 个风险商品")
        if risks:
            self._notice(
                self, "标题风险检测完成",
                f"共检测 {len(self._products)} 个商品，发现 {len(risks)} 个风险商品。",
            )
        else:
            self._notice(self, "标题风险检测完成", "未发现风险商品。")

    def _on_image_risk_check(self) -> None:
        """图片风险检测按钮点击，弹出选择框。"""
        if self._image_risk_service is None:
            self._notice(self, "提示", "图片风险检测尚未配置，请先在设置中绑定视觉API。", level="warning")
            return
        if not self._products:
            self._notice(self, "提示", "没有可检测的商品。")
            return
        if self._image_risk_thread is not None and self._image_risk_thread.isRunning():
            self._notice(self, "提示", "图片风险检测正在进行中，请稍候。", level="warning")
            return

        # 弹出选择框
        selected_count = len(self._selected_ids)
        total_count = len([p for p in self._products if self._states.get(p.product_id) == KEEP])

        popup = _ImageRiskCheckPopup(selected_count, total_count, self)
        popup.checkRequested.connect(self._start_image_risk_check)
        popup.show()

    def _start_image_risk_check(self, scope: str) -> None:
        """启动图片风险检测。scope: 'selected' 或 'all'。"""
        if scope == "selected" and self._selected_ids:
            products = [
                {"id": p.product_id, "main_image": p.main_image}
                for p in self._products
                if p.product_id in self._selected_ids
            ]
        else:
            products = [
                {"id": p.product_id, "main_image": p.main_image}
                for p in self._products
                if self._states.get(p.product_id) == KEEP
            ]

        if not products:
            self._notice(self, "提示", "没有可检测的商品。")
            return

        self.lbl_status.setText("图片风险检测中...")
        self.btn_infringement_check.setEnabled(False)

        # 启动后台线程
        self._image_risk_thread = QThread(self)
        self._image_risk_worker = _ImageRiskWorker(self._image_risk_service, products)
        self._image_risk_worker.moveToThread(self._image_risk_thread)
        self._image_risk_thread.started.connect(self._image_risk_worker.run)
        self._image_risk_worker.finished.connect(self._on_image_risk_finished)
        self._image_risk_worker.finished.connect(self._image_risk_thread.quit)
        self._image_risk_thread.finished.connect(self._image_risk_worker.deleteLater)
        self._image_risk_thread.finished.connect(self._image_risk_thread.deleteLater)
        self._image_risk_thread.finished.connect(
            lambda: setattr(self, '_image_risk_thread', None)
        )
        self._image_risk_thread.start()

    def _on_image_risk_finished(self, risks: list, failed_count: int, error: str) -> None:
        """图片风险检测完成回调。"""
        self.btn_infringement_check.setEnabled(True)
        if error:
            self.lbl_status.setText("图片检测失败")
            self._notice(self, "图片风险检测失败", error, level="error")
            return

        # 更新卡片风险标签
        risk_map = {r.product_id: r for r in risks}
        for pid, card in self._cards.items():
            if pid in risk_map:
                risk = risk_map[pid]
                if risk.has_risk:
                    card.set_risk_labels([risk.display_label] if risk.display_label else [])
            # 不清除已有的标题风险标签

        total_checked = len(risks) + failed_count
        if failed_count > 0:
            self.lbl_status.setText(f"图片检测完成，{len(risks)} 个风险，{failed_count} 个失败")
            self._notice(
                self, "图片风险检测完成",
                f"共检测 {total_checked} 个商品，发现 {len(risks)} 个风险商品，{failed_count} 个检测失败。",
                level="warning",
            )
        elif risks:
            self.lbl_status.setText(f"图片检测完成，发现 {len(risks)} 个风险商品")
            self._notice(
                self, "图片风险检测完成",
                f"共检测 {total_checked} 个商品，发现 {len(risks)} 个风险商品。",
            )
        else:
            self.lbl_status.setText("图片检测完成")
            self._notice(self, "图片风险检测完成", "未发现风险商品。")


# ── AI 风险检测 Worker ──────────────────────────────────────────


class _TitleRiskWorker(QObject):
    """标题风险检测后台线程。"""

    finished = Signal(list, str)  # (risks, error)

    def __init__(self, service, titles: list) -> None:
        super().__init__()
        self._service = service
        self._titles = titles

    @Slot()
    def run(self) -> None:
        try:
            risks = self._service.scan(self._titles)
            self.finished.emit(risks, "")
        except Exception as exc:
            self.finished.emit([], str(exc))


class _ImageRiskWorker(QObject):
    """图片风险检测后台线程。"""

    finished = Signal(list, int, str)  # (risks, failed_count, error)

    def __init__(self, service, products: list) -> None:
        super().__init__()
        self._service = service
        self._products = products

    @Slot()
    def run(self) -> None:
        try:
            risks, failed_count = self._service.scan_batch(self._products)
            self.finished.emit(risks, failed_count, "")
        except Exception as exc:
            self.finished.emit([], 0, str(exc))


# ── 图片风险检测选择弹窗 ──────────────────────────────────────────


class _ImageRiskCheckPopup(QWidget):
    """图片风险检测范围选择弹窗。"""

    checkRequested = Signal(str)  # 'selected' 或 'all'

    def __init__(self, selected_count: int, total_count: int, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setFixedSize(320, 180)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("选择检测范围")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        if selected_count > 0:
            btn_selected = QPushButton(f"检测已选商品（{selected_count}个）")
            btn_selected.clicked.connect(lambda: self._on_click("selected"))
            layout.addWidget(btn_selected)

        btn_all = QPushButton(f"检测全部商品（{total_count}个）")
        btn_all.clicked.connect(lambda: self._on_click("all"))
        layout.addWidget(btn_all)

        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.close)
        layout.addWidget(btn_cancel)

    def _on_click(self, scope: str) -> None:
        self.checkRequested.emit(scope)
        self.close()
