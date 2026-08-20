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
from pathlib import Path
from typing import Callable, List
from urllib.request import Request, urlopen

from PySide6.QtCore import QBuffer, QEvent, QIODevice, QObject, Qt, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QFontMetrics, QImage, QMouseEvent, QPainter, QPixmap
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

from .. import keyword_engine, product_risk_log
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
QPushButton#btnTitleCheck, QPushButton#btnInfringementCheck {
    background: #fff;
    border: 1px solid #4a90d9;
    color: #3a7bc8;
}
QPushButton#btnTitleCheck:hover, QPushButton#btnInfringementCheck:hover {
    background: #eef3fa;
}
QPushButton#btnDetectAll {
    background: #4a90d9;
    color: #fff;
    border: 1px solid #3a7bc8;
}
QPushButton#btnDetectAll:hover {
    background: #3a7bc8;
}
QPushButton#btnClearAll {
    background: #fff;
    color: #5a6b7e;
    border: 1px solid #d0d7e2;
}
QFrame#statusHintFrame {
    background: #eef3fa;
    border: 1px solid #dbe5f1;
    border-radius: 6px;
}
QLabel#lblStatus {
    background: transparent;
    border: none;
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


# ── 风险标签辅助函数 ────────────────────────────────────────────

# 需要清理的风险类型前缀
_RISK_PREFIXES = (
    "侵权风险｜",
    "SHEIN规则风险｜",
    "采集规则排除｜",
)

# 需要清理的来源描述前缀
_SOURCE_PREFIXES = (
    "标题包含",
    "标题含有",
    "标题明确为",
    "标题出现",
    "图片包含",
    "图片出现",
    "图片显示",
    "图片中出现",
    "图片明确显示",
    "检测到",
)


def _risk_display_summary(reason: str) -> str:
    """从完整 reason 中提取默认显示的核心信息。

    去除风险类型前缀和来源描述前缀，保留核心 IP / 品牌 / 风险内容。
    """
    text = reason
    # 去除风险类型前缀
    for prefix in _RISK_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    # 去除来源描述前缀
    for prefix in _SOURCE_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    return text.strip()


def _tokenize(text: str) -> list[str]:
    """将摘要文本拆成原子 token。

    - 连续英文/数字/连字符/拉丁扩展字符 → 一个 token（Spider-Man, Pokémon, IT）
    - 括号内容（含括号）→ 一个 token（（Marvel）, (IT)）
    - 单个中文字符 → 一个 token
    - 标点符号 → 各自独立 token
    """
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        # 中文括号内容
        if ch == "（":
            j = text.find("）", i + 1)
            if j != -1:
                tokens.append(text[i : j + 1])
                i = j + 1
                continue
        # 英文括号内容
        if ch == "(":
            j = text.find(")", i + 1)
            if j != -1:
                tokens.append(text[i : j + 1])
                i = j + 1
                continue
        # 连续英文/数字/连字符/拉丁扩展字符（如 Pokémon 中的 é）
        if _is_word_char(ch):
            j = i
            while j < n and _is_word_char(text[j]):
                j += 1
            tokens.append(text[i:j])
            i = j
            continue
        # 单个字符（中文、标点等）
        tokens.append(ch)
        i += 1
    return tokens


def _is_word_char(ch: str) -> bool:
    """判断字符是否属于英文单词字符（含拉丁扩展、连字符）。"""
    if ch.isascii():
        return ch.isalnum() or ch == "-"
    # 拉丁扩展字符（如 é, ö, ñ 等）
    cp = ord(ch)
    if 0x00C0 <= cp <= 0x024F:
        return True
    return False


def _wrap_risk_badge_text(text: str, font_metrics: QFontMetrics, max_width: int, max_lines: int = 3) -> str:
    """基于 token 的贪心填充换行，最多 max_lines 行。

    算法：
    1. 将文本拆成原子 token（英文单词、括号内容、单字）；
    2. 每行从左到右贪心加入 token，直到下一个 token 会超出宽度才换行；
    3. 不因标点提前换行——先填满，再换行；
    4. 超过 max_lines 行时截断，第三行只放能完整装下的 token；
    5. 不显示省略号，不显示半截英文单词。
    """
    if not text:
        return text

    tokens = _tokenize(text)
    lines: list[str] = []
    token_idx = 0

    while token_idx < len(tokens) and len(lines) < max_lines:
        line_tokens: list[str] = []
        line_width = 0

        while token_idx < len(tokens):
            token = tokens[token_idx]
            token_width = font_metrics.horizontalAdvance(token)
            # 计算加入此 token 后的行宽（token 间无额外间距）
            new_width = line_width + token_width
            if new_width > max_width and line_tokens:
                # 下一个 token 会超出宽度，换行
                break
            line_tokens.append(token)
            line_width = new_width
            token_idx += 1

        if line_tokens:
            lines.append("".join(line_tokens))
        else:
            # 单个 token 就超出宽度（极长英文词），强制放入
            if token_idx < len(tokens):
                lines.append(tokens[token_idx])
                token_idx += 1
            else:
                break

    return "\n".join(lines)


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

        self.lbl_risk = QLabel(self)
        self.lbl_risk.setObjectName("productCardRiskLegacy")
        self.lbl_risk.hide()  # 永久隐藏，不再承担风险显示

        # 右上角"已选"角标（绝对定位，不参与布局）
        self.lbl_badge = QLabel("✓ 已选", self)
        self.lbl_badge.setObjectName("productCardBadge")
        self.lbl_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.lbl_badge.hide()

        # 标题风险 Overlay（绝对定位，不参与布局）
        # 注意：不设置 WA_TransparentForMouseEvents，以便接收 Hover 事件显示 Tooltip
        self.lbl_title_risk = QLabel(self)
        self.lbl_title_risk.setObjectName("productCardTitleRisk")
        self.lbl_title_risk.setWordWrap(False)
        self.lbl_title_risk.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.lbl_title_risk.hide()

        # 图片风险 Overlay（绝对定位，不参与布局）
        # 注意：不设置 WA_TransparentForMouseEvents，以便接收 Hover 事件显示 Tooltip
        self.lbl_image_risk = QLabel(self)
        self.lbl_image_risk.setObjectName("productCardImageRisk")
        self.lbl_image_risk.setWordWrap(False)
        self.lbl_image_risk.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.lbl_image_risk.hide()

        # 标题风险和图片风险独立存储（新格式）
        self._title_risk_data: dict | None = None  # {"risk": "...", "reason": "..."}
        self._image_risk_data: dict | None = None  # {"risk": "...", "reason": "..."}

        # 检测只读标记：检测期间拦截卡片级鼠标事件
        self._detecting: bool = False

        self._network = network

        # 风险标签需要接收 Hover 事件（已移除 WA_TransparentForMouseEvents），
        # 但双击事件需要转发到卡片，以保留标题/图片的双击功能。
        self.lbl_title_risk.installEventFilter(self)
        self.lbl_image_risk.installEventFilter(self)

        self._load_image()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt 命名)
        """事件过滤器：将风险标签的双击事件转发到卡片。

        风险标签需要接收 Hover 事件来显示 Tooltip，
        但双击事件应转发到卡片以保留标题打开链接和图片搜图功能。
        """
        if event.type() == QEvent.Type.MouseButtonDblClick:
            if obj in (self.lbl_title_risk, self.lbl_image_risk):
                # 将事件坐标转换到卡片坐标系，转发给卡片的双击处理
                pos = event.position().toPoint()
                # 将标签坐标转换为卡片坐标
                card_pos = obj.mapTo(self, pos)
                # 构造新事件并转发
                forward_event = QMouseEvent(
                    QEvent.Type.MouseButtonDblClick,
                    card_pos,
                    Qt.MouseButton.LeftButton,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                )
                # 直接调用卡片的双击处理
                self.mouseDoubleClickEvent(forward_event)
                return True
        return super().eventFilter(obj, event)

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

    def set_title_risk_data(self, risk: str, reason: str = "") -> None:
        """设置标题风险状态，不影响图片风险。"""
        if risk and risk != "none":
            self._title_risk_data = {"risk": risk, "reason": reason}
        else:
            self._title_risk_data = None
        self._refresh_risk_display()

    def set_image_risk_data(self, risk: str, reason: str = "") -> None:
        """设置图片风险状态，不影响标题风险。"""
        if risk and risk != "none":
            self._image_risk_data = {"risk": risk, "reason": reason}
        else:
            self._image_risk_data = None
        self._refresh_risk_display()

    def set_detecting(self, detecting: bool) -> None:
        """设置检测只读标记。检测期间拦截卡片级鼠标事件，不改变 selected。"""
        self._detecting = detecting

    # -- 风险样式常量 --
    _RISK_STYLE_PLATFORM = (
        "background:#FFF4E5;color:#C77600;border:1px solid #FFD59E;"
        "border-radius:4px;padding:4px 6px;font-size:11px;"
    )
    _RISK_STYLE_INFRINGEMENT = (
        "background:#FEE2E2;color:#B91C1C;border:1px solid #FCA5A5;"
        "border-radius:4px;padding:4px 6px;font-size:11px;"
    )
    # 风险标签固定宽度：标题 145px，图片 160px
    _TITLE_RISK_BADGE_WIDTH = 145
    _IMAGE_RISK_BADGE_WIDTH = 160
    # 风险标签固定行数
    _RISK_BADGE_MAX_LINES = 3
    # 风险标签水平方向 padding + border 总占用（padding 6px×2 + border 1px×2 = 14px）
    _RISK_BADGE_H_CHROME = 14

    def _badge_fixed_height(self) -> int:
        """计算风险标签的固定高度（3 行文字 + padding + border）。"""
        fm = QFontMetrics(self.lbl_title_risk.font())
        line_height = fm.height()
        # padding 4px top + 4px bottom = 8px；border 1px top + 1px bottom = 2px
        chrome_v = 10
        return line_height * self._RISK_BADGE_MAX_LINES + chrome_v

    def _refresh_risk_display(self) -> None:
        """分别更新标题风险和图片风险 Overlay。"""
        badge_h = self._badge_fixed_height()
        # 标题风险 Overlay
        title = self._title_risk_data
        if title and title.get("risk") != "none":
            risk = title["risk"]
            reason = title.get("reason", "")
            summary = _risk_display_summary(reason) if reason else risk
            # 按实际内容区域宽度换行（标签宽度 - padding - border），最多 3 行
            fm = QFontMetrics(self.lbl_title_risk.font())
            text_width = self._TITLE_RISK_BADGE_WIDTH - self._RISK_BADGE_H_CHROME
            wrapped = _wrap_risk_badge_text(summary, fm, text_width, self._RISK_BADGE_MAX_LINES)
            self.lbl_title_risk.setText(wrapped)
            # 固定尺寸
            self.lbl_title_risk.setFixedSize(self._TITLE_RISK_BADGE_WIDTH, badge_h)
            # Hover 显示完整信息
            risk_type_label = {
                "infringement": "侵权风险",
                "platform": "SHEIN规则风险",
            }.get(risk, risk)
            self.lbl_title_risk.setToolTip(
                f"来源：标题检测\n类型：{risk_type_label}\n完整信息：{reason}"
            )
            self.lbl_title_risk.setStyleSheet(
                self._RISK_STYLE_INFRINGEMENT if risk == "infringement" else self._RISK_STYLE_PLATFORM
            )
            self.lbl_title_risk.show()
        else:
            self.lbl_title_risk.hide()

        # 图片风险 Overlay
        image = self._image_risk_data
        if image and image.get("risk") != "none":
            risk = image["risk"]
            reason = image.get("reason", "")
            summary = _risk_display_summary(reason) if reason else risk
            fm = QFontMetrics(self.lbl_image_risk.font())
            text_width = self._IMAGE_RISK_BADGE_WIDTH - self._RISK_BADGE_H_CHROME
            wrapped = _wrap_risk_badge_text(summary, fm, text_width, self._RISK_BADGE_MAX_LINES)
            self.lbl_image_risk.setText(wrapped)
            # 固定尺寸
            self.lbl_image_risk.setFixedSize(self._IMAGE_RISK_BADGE_WIDTH, badge_h)
            risk_type_label = {
                "infringement": "侵权风险",
                "platform": "SHEIN规则风险",
            }.get(risk, risk)
            self.lbl_image_risk.setToolTip(
                f"来源：图片检测\n类型：{risk_type_label}\n完整信息：{reason}"
            )
            self.lbl_image_risk.setStyleSheet(
                self._RISK_STYLE_INFRINGEMENT if risk == "infringement" else self._RISK_STYLE_PLATFORM
            )
            self.lbl_image_risk.show()
        else:
            self.lbl_image_risk.hide()

        # 更新文字和显示状态后，重新计算 Overlay 几何位置
        self._layout_risk_overlays()

    def _layout_risk_overlays(self) -> None:
        """重新计算并设置两个风险 Overlay 的位置。

        在 resizeEvent() 和 _refresh_risk_display() 后调用，
        确保 Overlay 始终位于对应区域内。
        使用固定宽度和固定高度（3 行），位置不随内容变化。
        """
        badge_h = self._badge_fixed_height()
        # 标题风险 Overlay：覆盖在标题区域内部左下角，固定 145px 宽
        title_geo = self.lbl_title.geometry()
        self.lbl_title_risk.setFixedSize(self._TITLE_RISK_BADGE_WIDTH, badge_h)
        self.lbl_title_risk.move(
            title_geo.left() + 4,
            title_geo.bottom() - badge_h - 2,
        )
        # 图片风险 Overlay：覆盖在图片区内部左下角，固定 160px 宽
        img_geo = self.lbl_image.geometry()
        self.lbl_image_risk.setFixedSize(self._IMAGE_RISK_BADGE_WIDTH, badge_h)
        self.lbl_image_risk.move(
            img_geo.left() + 4,
            img_geo.bottom() - badge_h - 4,
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        super().resizeEvent(event)
        self.lbl_badge.move(self.width() - self.lbl_badge.width() - 8, 8)
        self._layout_risk_overlays()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        # 检测只读期间：拦截所有鼠标事件，不改变 selected
        if self._detecting:
            event.accept()
            return
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


class _CardGridDeleteKeyFilter(QObject):
    """商品卡片区域 Delete 键：直接复用 ``remove_selected()``（KEEP → REMOVED）。

    只监听发往 QScrollArea（卡片滚动区域）的按键事件；焦点在搜索词输入框、
    数量 SpinBox 等其它控件时，Delete 键事件不会到达滚动区域，天然安全。
    已移除视图下 Delete 不做任何事情（与按钮行为一致）。
    """

    def __init__(self, scroll: "QScrollArea", page: "ProductCollectionPage") -> None:
        super().__init__(scroll)
        self._page = page
        scroll.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if (
            event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Delete
            and not self._page._showing_removed
        ):
            self._page.remove_selected()
            return True
        return False


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
        """注入日志目录（由宿主应用调用）。

        log_dir 形如 <数据目录>/product_collector；
        同时配置独立商品风险检测日志（<数据目录>/logs/product_risk/product_risk.log）。
        """
        self._log_dir = log_dir
        if log_dir:
            from .. import product_risk_log

            product_risk_log.configure(Path(log_dir).parent)

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
        """加载 .ui 静态布局，绑定控件引用和信号。

        缩窗策略（页面外层负责横向滚动，商品区负责纵向滚动）：
        - 外层 QScrollArea 负责整页横向滚动：顶部搜索区/操作按钮/商品区在窗口
          变窄时都可横向访问，不把 760px 搜索框等核心控件强行压窄；
        - 商品卡片区 scrollProducts 继续负责商品列表纵向滚动；外层纵向滚动条
          固定关闭，避免两个纵向滚动条抢鼠标滚轮；
        - 页面自身最小尺寸设小，避免本页最小宽度把主窗口最小宽度撑出屏幕。
        """
        form = load_ui(self)
        # 页面外层横向滚动容器
        outer_scroll = QScrollArea()
        outer_scroll.setWidgetResizable(True)
        outer_scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        outer_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer_scroll.setWidget(form)
        # 整页设计最小宽度 = 布局真实最小宽度（搜索区/操作行控件最小宽度之和），
        # 低于该宽度时由外层横向滚动条提供访问；高度交给商品区 scrollProducts 纵向滚动。
        layout_min_w = form.layout().minimumSize().width() if form.layout() else 1520
        form.setMinimumWidth(max(int(layout_min_w), 1180))
        form.setMinimumHeight(0)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(outer_scroll)
        # 页面自身最小尺寸设小：窄窗口时由外层滚动条承担横向访问，
        # 不让本页的最小宽度把主窗口最小宽度撑出屏幕。
        self.setMinimumSize(320, 240)
        self._outer_scroll = outer_scroll
        self._form = form

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
        self.btn_detect_all = form.findChild(QWidget, "btnDetectAll")
        self.btn_copy = form.findChild(QWidget, "btnCopyLinks")
        self.btn_keep_only = form.findChild(QWidget, "btnKeepOnlySelected")
        self.btn_remove_selected = form.findChild(QWidget, "btnRemoveSelected")
        self.btn_select_all = form.findChild(QWidget, "btnSelectAll")
        self.btn_view_removed = form.findChild(QWidget, "btnViewRemoved")
        self.btn_restore = form.findChild(QWidget, "btnRestoreSelected")
        self.btn_clear_all = form.findChild(QWidget, "btnClearAll")
        self.status_hint_frame = form.findChild(QWidget, "statusHintFrame")
        self.scroll = form.findChild(QScrollArea, "scrollProducts")
        self._container = form.findChild(QWidget, "productGridHost")
        # Delete 键（卡片区域）：复用同一 remove_selected()，已移除视图下不做事
        self.scroll.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._card_grid_delete_filter = _CardGridDeleteKeyFilter(self.scroll, self)

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
        self.btn_clear_all.clicked.connect(self._on_clear_all)

        # 标题检测 / 图片检测 / 全部检测
        self.btn_title_check.clicked.connect(self._on_title_risk_check)
        self.btn_infringement_check.clicked.connect(self._on_image_risk_check)
        self.btn_detect_all.clicked.connect(self._on_detect_all)
        self._update_risk_buttons_state()
        self._update_selection_buttons()

        # 检测只读状态
        self._detecting_active = False
        self._cancel_requested = False
        # 检测快照：本次检测对象冻结列表
        self._detect_snapshot: list[CandidateProduct] | None = None
        # 全部检测：标题阶段失败数量（供最终状态合并显示）
        self._detect_all_title_failed = 0
        # 检测期间冻结的 KEEP 商品显示顺序（id），进入终态后清除再统一排序
        self._detect_display_order: list[str] | None = None
        # 本次检测批次进度统计（批次信号回主线程后累计）
        self._batch_times: list[float] = []
        self._detect_processed = 0
        self._detect_risks = 0
        self._detect_failed = 0

        # 容器尺寸变化时重排卡片
        self._container.installEventFilter(self)
        self.spin_target.installEventFilter(self)
        self.btn_random_idea.installEventFilter(self)
        self.btn_select_all.installEventFilter(self)
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
        # 全部选择按钮：左键全选（clicked 信号），右键取消全部选择
        if obj is self.btn_select_all and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.RightButton:
                self.clear_selection()
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
        self.btn_start.setText("采集中…")
        self._update_task_status_label()
        self._start_next_task()

    def _update_task_status_label(self) -> None:
        total = len(self._search_tasks)
        if total > 1:
            idx = min(self._current_task_idx + 1, total)
            cn = self._search_tasks[self._current_task_idx].display_cn
            self.lbl_status.setText(f"正在执行 {idx}/{total}：{cn}")
        else:
            self.lbl_status.setText(
                "<span style='color:#3a7bc8;font-weight:600;'>正在采集商品…</span>"
            )

    def _start_next_task(self) -> None:
        if self._current_task_idx >= len(self._search_tasks):
            self._finish_all_tasks()
            return
        task = self._search_tasks[self._current_task_idx]

        thread = QThread(self)
        worker = CollectWorker(
            task.actual_query, task.target_count, self._collector,
            log_dir=self._log_dir,
        )
        self._thread = thread
        self._worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.reportReady.connect(self._on_task_report)
        worker.failed.connect(self._on_task_failed)
        worker.reportReady.connect(thread.quit)
        worker.failed.connect(thread.quit)
        # 通过默认参数捕获本次 thread/worker 身份，避免多关键词时
        # 旧线程 finished 误清理刚创建的新线程/worker
        thread.finished.connect(
            lambda t=thread, w=worker: self._clear_collect_task(t, w)
        )
        thread.start()

    def _clear_collect_task(self, finished_thread: QThread, finished_worker: CollectWorker) -> None:
        """采集线程结束后安全清理。

        worker / thread 正常 deleteLater；通过对象 identity 判断，
        旧线程结束不会误清后续任务新建的线程/worker。
        """
        finished_worker.deleteLater()
        finished_thread.deleteLater()
        if self._thread is finished_thread:
            self._thread = None
        if self._worker is finished_worker:
            self._worker = None
        self._update_clear_button()

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
        self.btn_start.setText("开始采集")
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
        if self._image_search_thread is not None:
            try:
                running = self._image_search_thread.isRunning()
            except RuntimeError:
                # 旧线程 C++ 对象已被 deleteLater 销毁：视为已结束
                running = False
            if running:
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
        # 清理槽绑定页面自身：finished 信号跨线程投递时若绑定 QThread 自身，
        # 线程对象被 DeferredDelete 销毁后槽会丢失，导致引用残留（再次搜图崩溃）
        self._image_search_thread.finished.connect(self._clear_image_search_task)
        self._image_search_thread.start()

    def _open_1688_result(self, result_url: str) -> None:
        webbrowser.open(result_url)

    def _on_1688_image_search_failed(self, _message: str) -> None:
        self._notice(self, "提示", "1688 图片搜图失败。", level="warning")

    def _clear_image_search_task(self) -> None:
        """仅清理刚结束的搜图任务，允许下一次创建新的 worker/thread。

        receiver 为页面自身（而非 QThread 对象），finished 信号跨线程投递时
        即使线程对象已被 DeferredDelete 销毁，本槽仍能正常执行。
        注意：finished 到达时 QThread/worker 的 C++ 对象可能已被 deleteLater
        同步销毁（PySide6 事件处理时序竞争），因此本槽内禁止访问线程对象的
        任何 C++ 成员（sender()/isRunning() 等），只做 Python 引用清理。
        """
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
        self._apply_removed_view_style()

        for product in self._products:
            card = ProductCard(product, self._network, self._fetch_images, self._container)
            card.selectionRequested.connect(self.set_selection)
            card.titleActivated.connect(self._open_product_url)
            card.imageSearchRequested.connect(self._start_1688_image_search)
            self._cards[product.product_id] = card

        self._update_stats()
        self._update_selection_buttons()
        self._update_risk_buttons_state()
        self._update_clear_button()
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
            # 已移除页面不参与风险排序，保持原顺序
            return [
                c for pid, c in self._cards.items()
                if self._states[pid] == REMOVED
            ]
        visible = [
            card
            for product_id, card in self._cards.items()
            if self._states[product_id] == KEEP
        ]
        # 检测期间冻结显示顺序：批次结果逐步写入 / 窗口 resize 都不重排
        order = self._detect_display_order
        if order:
            by_id = {card.product.product_id: card for card in visible}
            ordered = [by_id[pid] for pid in order if pid in by_id]
            seen = {c.product.product_id for c in ordered}
            ordered.extend(c for c in visible if c.product.product_id not in seen)
            return ordered
        # 风险商品置顶：infringement > platform > none；
        # 稳定排序 + self._cards 插入序（即原始采集顺序），同级不漂移
        visible.sort(key=lambda card: -self._card_risk_rank(card))
        return visible

    def _card_risk_rank(self, card: ProductCard) -> int:
        """综合风险等级：标题/图片任一 infringement → 2；任一 platform → 1；否则 0。

        none 检测结果已由 set_*_risk_data 清除对应旧状态，
        未返回/失败的商品保留旧状态，因此这里始终反映当前有效风险。
        """
        t = card._title_risk_data
        i = card._image_risk_data
        t_risk = t.get("risk") if t else "none"
        i_risk = i.get("risk") if i else "none"
        if "infringement" in (t_risk, i_risk):
            return 2
        if "platform" in (t_risk, i_risk):
            return 1
        return 0

    def _sort_risk_pinned(self) -> None:
        """检测全部结束后重排一次：风险商品置顶，滚动条回到顶部。

        只改变卡片显示顺序，不修改 selected 集合与 KEEP/REMOVED 状态。
        """
        self._relayout_cards()
        bar = self.scroll.verticalScrollBar()
        if bar is not None:
            bar.setValue(0)

    def _relayout_preserving_scroll(self) -> None:
        """重排卡片前保存滚动位置，布局完成后恢复，避免跳到页面底部。"""
        bar = self.scroll.verticalScrollBar()
        saved = bar.value()
        self._relayout_cards()
        QTimer.singleShot(0, lambda: bar.setValue(saved))

    # ------------------------------------------------------------------
    # 已移除视图
    # ------------------------------------------------------------------

    def _apply_removed_view_style(self) -> None:
        """已移除视图：返回按钮文本与主蓝色样式；正常视图恢复中性样式。"""
        if self._showing_removed:
            self.btn_view_removed.setText("← 返回商品视图")
            self.btn_view_removed.setProperty("primary", True)
        else:
            self.btn_view_removed.setText(
                f"查看已移除（{self.removed_count()}）"
            )
            self.btn_view_removed.setProperty("primary", False)
        style = self.btn_view_removed.style()
        style.unpolish(self.btn_view_removed)
        style.polish(self.btn_view_removed)

    def _toggle_removed_view(self) -> None:
        self._showing_removed = not self._showing_removed
        self.clear_selection()
        self.btn_restore.setVisible(self._showing_removed)
        self._apply_removed_view_style()
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
        self._apply_removed_view_style()
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
        # 选中后让滚动区域获得焦点，使 Delete 键能触发移除选中
        if selected and self.scroll is not None:
            self.scroll.setFocus(Qt.FocusReason.OtherFocusReason)

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
        self._apply_removed_view_style()
        self._update_status_hint()

    def _update_status_hint(self) -> None:
        """刷新中央状态提示区默认文本（工作/完成状态优先，选择变化后回到计数）。"""
        if self._showing_removed:
            self.lbl_status.setText(
                "<span style='color:#C77600;font-weight:600;'>已移除商品视图</span>"
                f" · 共 {self.removed_count()} 个 · 已选 {self.selected_count()} 个 · 可选择后恢复"
            )
        else:
            self.lbl_status.setText(
                f"商品 {self.keep_count()} · 已选 {self.selected_count()} · 已移除 {self.removed_count()}"
            )

    def _update_clear_button(self) -> None:
        """清空本次按钮：有商品且非检测/采集中才可用。"""
        collecting = self._thread is not None and self._thread.isRunning()
        risk_running = (
            (self._title_risk_thread is not None and self._title_risk_thread.isRunning())
            or (self._image_risk_thread is not None and self._image_risk_thread.isRunning())
        )
        self.btn_clear_all.setEnabled(
            bool(self._products) and not self._detecting_active and not collecting and not risk_running
        )

    def _on_clear_all(self) -> None:
        """清空本次按钮点击：进行中禁止执行，确认一次后清空。"""
        collecting = self._thread is not None and self._thread.isRunning()
        if collecting or self._detecting_active:
            self._notice(self, "提示", "正在采集或风险检测中，暂不能清空本次。", level="warning")
            return
        if not self._products:
            return
        if self._confirm_clear_all():
            self._clear_all_results()

    def _confirm_clear_all(self) -> bool:
        """弹出一次确认框：确定清空本次采集结果吗？"""
        box = QMessageBox(self)
        box.setWindowTitle("清空本次")
        box.setText("确定清空本次采集结果吗？")
        box.setIcon(QMessageBox.Icon.Warning)
        btn_ok = box.addButton("确定清空", QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_cancel)
        box.exec()
        return box.clickedButton() is btn_ok

    def _clear_all_results(self) -> None:
        """清空当前一轮采集产生的全部运行期数据。

        清除：商品列表 / 卡片 / selected / KEEP-REMOVED / 标题与图片风险状态 /
        图片检测运行期缓存 / 页面引用 / 检测统计与提示状态。
        不清除：历史记录、API Profile、API Key、搜索词配置、汇率、
        软件设置、29 美元补贴规则等长期数据。
        """
        for card in self._cards.values():
            card.deleteLater()
        self._cards = {}
        self._products = []
        self._states = {}
        self._selected_ids = set()
        self._showing_removed = False
        self.btn_restore.setVisible(False)
        # 本轮采集期运行引用：不再持有 CandidateProduct / 任务数据
        self._all_products = []
        self._seen_ids = set()
        self._search_tasks = []
        self._task_statuses = []
        self._current_task_idx = 0
        # 页面当前引用与检测状态
        self._detect_snapshot = None
        self._detect_all_targets = None
        self._detect_all_phase = None
        self._detect_all_title_failed = 0
        self._detect_display_order = None
        self._batch_times = []
        self._detect_processed = 0
        self._detect_risks = 0
        self._detect_failed = 0
        # 图片检测运行期缓存（标题检测无运行期缓存）
        if self._image_risk_service is not None:
            self._image_risk_service.clear_cache()
        self._apply_removed_view_style()
        self._update_stats()
        self._update_selection_buttons()
        self._update_risk_buttons_state()
        self._update_clear_button()
        self._relayout_cards()

    # ------------------------------------------------------------------
    # AI 风险检测
    # ------------------------------------------------------------------

    def _update_risk_buttons_state(self) -> None:
        """根据 API 配置状态启用/禁用风险检测按钮。"""
        has_products = bool(self._products)
        has_store = self._api_profile_store is not None
        has_title_api = has_store
        has_image_api = has_store
        self.btn_title_check.setEnabled(has_products and has_title_api and not self._detecting_active)
        self.btn_infringement_check.setEnabled(has_products and has_image_api and not self._detecting_active)
        self.btn_detect_all.setEnabled(has_products and has_title_api and has_image_api and not self._detecting_active)

    # ------------------------------------------------------------------
    # 批次进度反馈（批次 Signal 回主线程后执行）
    # ------------------------------------------------------------------

    @staticmethod
    def _format_eta(seconds: float) -> str:
        """把秒数格式化为中文约数：'约 55秒' / '约 1分20秒' / '约 2分'。"""
        total = max(int(round(seconds)), 1)
        if total < 60:
            return f"约 {total}秒"
        minutes, secs = divmod(total, 60)
        if secs:
            return f"约 {minutes}分{secs}秒"
        return f"约 {minutes}分"

    def _update_detect_status(
        self,
        prefix: str,
        processed: int,
        total: int,
        risks: int,
        failed: int,
        batch_index: int,
        total_batches: int,
        eta_label: str,
    ) -> None:
        """更新中央状态栏：已完成/总数｜风险｜失败｜预计剩余（无新控件）。"""
        parts = [f"{prefix} {processed}/{total}", f"风险 {risks}", f"失败 {failed}"]
        # 初始(0,0)或进行中批次显示 ETA；最后一批完成后不再显示
        if batch_index < total_batches or total_batches == 0:
            if not self._batch_times:
                parts.append(f"{eta_label}：计算中…")
            else:
                avg = sum(self._batch_times) / len(self._batch_times)
                remaining = max(total_batches - batch_index, 0)
                # _format_eta 已带“约”，外层不再重复拼接，避免“约 约”
                parts.append(f"{eta_label}{self._format_eta(avg * remaining)}")
        self.lbl_status.setText("｜".join(parts))

    def _apply_batch(
        self,
        results: list,
        failed: int,
        batch_index: int,
        total_batches: int,
        elapsed_ms: float,
        prefix: str,
        eta_label: str,
        kind: str,
    ) -> None:
        """应用一个批次成功结果到快照卡片，并累计批次进度。

        kind: "title" | "image"，决定写入标题 / 图片风险。
        失败 / 缺失商品不覆盖旧状态，只计入失败数；已处理含成功 + 失败。
        """
        snapshot_ids = {p.product_id for p in (self._detect_snapshot or self._get_keep_products())}
        applied = 0
        batch_risks = 0
        for r in results:
            pid = r.product_id
            if pid not in snapshot_ids:
                continue
            card = self._cards.get(pid)
            if card is None:
                continue
            if kind == "image":
                card.set_image_risk_data(r.risk, r.reason)
            else:
                card.set_title_risk_data(r.risk, r.reason)
            applied += 1
            if r.risk != "none":
                batch_risks += 1
        self._batch_times.append(elapsed_ms / 1000.0)
        self._detect_processed += applied + failed
        self._detect_risks += batch_risks
        self._detect_failed += failed
        self._update_detect_status(
            prefix, self._detect_processed, len(snapshot_ids),
            self._detect_risks, self._detect_failed,
            batch_index, total_batches, eta_label,
        )

    def _preapply_image_cache(self, targets: list[CandidateProduct]) -> tuple[int, int]:
        """检测开始前预应用图片运行期缓存并统计缺图。

        返回 (missing_count, cache_hits)。
        缺图：计入失败；缓存命中：立即写卡片并计入已处理。
        仅接受真实 ImageRiskItem 缓存条目，避免把异常 / mock 返回值当结果。
        """
        from ..image_risk_scan import ImageRiskItem

        service = self._image_risk_service
        if service is None:
            return 0, 0
        missing = 0
        hits = 0
        for p in targets:
            card = self._cards.get(p.product_id)
            if card is None:
                continue
            img = str(p.main_image or "").strip()
            if not img:
                missing += 1
                continue
            cached = service.get_cached(p.product_id, img)
            if not isinstance(cached, ImageRiskItem):
                continue
            card.set_image_risk_data(cached.risk, cached.reason)
            hits += 1
            if cached.risk != "none":
                self._detect_risks += 1
        return missing, hits

    def _on_title_batch_result(self, results, failed, batch_index, total_batches, elapsed_ms) -> None:
        """标题检测：单批完成 → 立即写卡片 + 更新状态栏。"""
        self._apply_batch(results, failed, batch_index, total_batches, elapsed_ms,
                          "标题检测", "预计剩余", "title")

    def _on_image_batch_result(self, results, failed, batch_index, total_batches, elapsed_ms) -> None:
        """图片检测：单批完成 → 立即写卡片 + 更新状态栏。"""
        self._apply_batch(results, failed, batch_index, total_batches, elapsed_ms,
                          "图片检测", "预计剩余", "image")

    def _on_detect_all_title_batch_result(self, results, failed, batch_index, total_batches, elapsed_ms) -> None:
        """全部检测·标题阶段：单批完成 → 立即写卡片 + 更新状态栏。"""
        self._apply_batch(results, failed, batch_index, total_batches, elapsed_ms,
                          "全部检测·标题", "预计本阶段剩余", "title")

    def _on_detect_all_image_batch_result(self, results, failed, batch_index, total_batches, elapsed_ms) -> None:
        """全部检测·图片阶段：单批完成 → 立即写卡片 + 更新状态栏。"""
        self._apply_batch(results, failed, batch_index, total_batches, elapsed_ms,
                          "全部检测·图片", "预计本阶段剩余", "image")

    def _on_title_risk_thread_cleanup(self) -> None:
        """标题风险检测线程结束：释放引用并刷新清空按钮。"""
        self._title_risk_thread = None
        self._update_clear_button()

    def _on_image_risk_thread_cleanup(self) -> None:
        """图片风险检测线程结束：释放引用并刷新清空按钮。"""
        self._image_risk_thread = None
        self._update_clear_button()

    # ------------------------------------------------------------------
    # 检测只读模式
    # ------------------------------------------------------------------

    def _enter_detecting(self, targets: list[CandidateProduct] | None = None) -> None:
        """进入检测只读模式：禁用选择/全选/移除/恢复/视图切换/重新采集/启动其他检测。

        targets: 本次实际检测的商品列表，用作检测快照。
                 如果不传，则默认全部 KEEP 商品。
        """
        self._detecting_active = True
        self._cancel_requested = False
        # 冻结本次实际检测对象快照
        if targets is not None:
            self._detect_snapshot = list(targets)
        else:
            self._detect_snapshot = [
                p for p in self._products
                if self._states.get(p.product_id) == KEEP
            ]
        # 冻结当前 KEEP 商品显示顺序：检测期间不因批次结果 / 窗口 resize 重排
        # 先清空再取，确保取到的是真实排序后的当前顺序
        self._detect_display_order = None
        self._detect_display_order = [c.product.product_id for c in self._visible_cards()]
        # 本次检测批次进度统计
        self._batch_times = []
        self._detect_processed = 0
        self._detect_risks = 0
        self._detect_failed = 0
        # 禁用所有非检测操作按钮
        for btn in (
            self.btn_select_all, self.btn_keep_only, self.btn_remove_selected,
            self.btn_view_removed, self.btn_restore, self.btn_start,
            self.btn_title_check, self.btn_infringement_check, self.btn_detect_all,
            self.btn_clear_all,
        ):
            if btn:
                btn.setEnabled(False)
        # 禁用卡片级鼠标事件
        for card in self._cards.values():
            card.set_detecting(True)

    def _exit_detecting(self) -> None:
        """退出检测只读模式：恢复所有操作，并清除冻结显示顺序。"""
        self._detecting_active = False
        self._detect_snapshot = None
        self._detect_display_order = None
        # 恢复卡片级鼠标事件
        for card in self._cards.values():
            card.set_detecting(False)
        # 恢复按钮状态
        self._update_risk_buttons_state()
        self._update_selection_buttons()
        self.btn_start.setEnabled(True)
        self._update_clear_button()

    # ------------------------------------------------------------------
    # 确认框
    # ------------------------------------------------------------------

    def _get_keep_products(self) -> list[CandidateProduct]:
        """返回所有 KEEP 商品。"""
        return [p for p in self._products if self._states.get(p.product_id) == KEEP]

    def _get_selected_keep_products(self) -> list[CandidateProduct]:
        """返回已选中的 KEEP 商品。"""
        return [
            p for p in self._products
            if p.product_id in self._selected_ids and self._states.get(p.product_id) == KEEP
        ]

    def _show_detect_confirm(self, detect_type: str) -> tuple[list[CandidateProduct], bool] | None:
        """显示检测确认框。

        detect_type: "标题" | "图片" | "标题 + 图片"
        返回 (products_to_detect, confirmed) 或 None（取消）。
        """
        selected = self._get_selected_keep_products()
        all_keep = self._get_keep_products()
        if not all_keep:
            self._notice(self, "提示", "没有可检测的商品。")
            return None

        if selected:
            msg = f"已选择 {len(selected)} 个商品\n检测：{detect_type}风险"
            target = selected
        else:
            msg = f"将检测全部保留商品，共 {len(all_keep)} 个。\n检测：{detect_type}风险"
            target = all_keep

        from PySide6.QtWidgets import QDialog, QLabel as QLbl, QPushButton as QBtn, QVBoxLayout as VBL
        dlg = QDialog(self)
        dlg.setWindowTitle(f"确认{detect_type}检测")
        dlg.setFixedSize(380, 160)
        v = VBL(dlg)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)
        lbl = QLbl(msg)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 13px;")
        v.addWidget(lbl)
        v.addStretch()
        btn_row = QHBoxLayout()
        btn_start = QBtn("开始检测")
        btn_start.setStyleSheet("background:#4a90d9;color:#fff;border-radius:6px;padding:6px 20px;")
        btn_cancel = QBtn("取消")
        result = [False]
        def on_start():
            result[0] = True
            dlg.accept()
        def on_cancel():
            dlg.reject()
        btn_start.clicked.connect(on_start)
        btn_cancel.clicked.connect(on_cancel)
        btn_row.addStretch()
        btn_row.addWidget(btn_start)
        btn_row.addWidget(btn_cancel)
        v.addLayout(btn_row)
        dlg.exec()
        if result[0]:
            return (target, True)
        return None

    # ------------------------------------------------------------------
    # 标题检测
    # ------------------------------------------------------------------

    def _on_title_risk_check(self) -> None:
        """标题风险检测按钮点击。"""
        if self._title_risk_service is None:
            self._notice(self, "提示", "标题风险检测尚未配置，请先在设置中绑定文字API。", level="warning")
            return
        if self._detecting_active:
            return
        result = self._show_detect_confirm("标题")
        if result is None:
            return
        targets, _ = result
        self._start_title_risk_check(targets)

    def _start_title_risk_check(self, targets: list[CandidateProduct]) -> None:
        """启动标题风险检测（按 20/批 顺序执行，批次结果逐批回 UI）。"""
        self._enter_detecting(targets)
        self._update_detect_status("标题检测", 0, len(targets), 0, 0, 0, 0, "预计剩余")
        self.btn_title_check.setText("取消标题检测")
        self.btn_title_check.setEnabled(True)
        self.btn_title_check.setStyleSheet("background:#FFF4E5;color:#C77600;border:1px solid #FFD59E;border-radius:6px;")
        self.btn_title_check.clicked.disconnect()
        self.btn_title_check.clicked.connect(self._cancel_current_detect)

        titles = [{"id": p.product_id, "title": p.title} for p in targets]
        self._cancel_requested = False

        self._title_risk_thread = QThread(self)
        self._title_risk_worker = _TitleRiskWorker(self._title_risk_service, titles, cancel_requested=lambda: self._cancel_requested)
        self._title_risk_worker.moveToThread(self._title_risk_thread)
        self._title_risk_thread.started.connect(self._title_risk_worker.run)
        self._title_risk_worker.finished.connect(self._on_title_risk_finished)
        self._title_risk_worker.finished.connect(self._title_risk_thread.quit)
        batch_signal = getattr(self._title_risk_worker, "batch_result", None)
        if batch_signal is not None:
            batch_signal.connect(self._on_title_batch_result)
        self._title_risk_thread.finished.connect(self._title_risk_worker.deleteLater)
        self._title_risk_thread.finished.connect(self._title_risk_thread.deleteLater)
        self._title_risk_thread.finished.connect(self._on_title_risk_thread_cleanup)
        self._title_risk_thread.start()

    def _cancel_current_detect(self) -> None:
        """协作式取消当前检测。"""
        self._cancel_requested = True
        self.lbl_status.setText(
            "<span style='color:#3a7bc8;font-weight:600;'>正在取消检测…</span>"
        )

    def _on_title_risk_finished(self, risks: list, error: str) -> None:
        """标题风险检测完成回调（终态：应用结果 → 解冻 → 排序一次）。"""
        # 恢复按钮文字和连接
        self.btn_title_check.setText("标题检测")
        self.btn_title_check.setStyleSheet("")
        try:
            self.btn_title_check.clicked.disconnect()
        except RuntimeError:
            pass
        self.btn_title_check.clicked.connect(self._on_title_risk_check)

        snapshot_ids = {p.product_id for p in (self._detect_snapshot or self._get_keep_products())}
        if error:
            self.lbl_status.setText("标题检测失败")
            self._notice(self, "标题风险检测失败", error, level="error")
        else:
            # 无论是否取消，先应用本次成功结果（批次已应用，此处幂等兜底）
            risk_map = {r.product_id: r for r in risks}
            for pid, card in self._cards.items():
                if pid not in snapshot_ids:
                    continue
                if pid in risk_map:
                    r = risk_map[pid]
                    card.set_title_risk_data(r.risk, r.reason)
            risk_count = sum(1 for r in risks if r.risk != "none")
            # 缺失/非法结果统计为失败（返回结果数 < 送检数）
            title_failed = len(snapshot_ids - set(risk_map))
            # 根据取消状态显示不同消息
            if self._cancel_requested:
                self.lbl_status.setText(
                    f"检测已取消 · 已完成 {self._detect_processed}/{len(snapshot_ids)} · 已按现有结果排序"
                )
            elif title_failed > 0 and not risk_map:
                self.lbl_status.setText("检测失败 · 已按现有有效结果排序")
                self._notice(self, "标题风险检测完成",
                             f"共处理 {len(snapshot_ids)} 个商品，{title_failed} 个失败，未获得新的有效结果。")
            elif title_failed > 0:
                self.lbl_status.setText(
                    "检测完成 · "
                    f"<span style='color:#C62828;font-weight:600;'>失败 {title_failed} 个</span>"
                    " · 风险商品已置顶"
                )
                self._notice(self, "标题风险检测完成",
                             f"共处理 {len(snapshot_ids)} 个商品，{title_failed} 个失败，发现 {risk_count} 个风险商品。")
            else:
                self.lbl_status.setText("检测完成 · 风险商品已置顶")
                if risk_count > 0:
                    self._notice(self, "标题风险检测完成", f"共检测 {len(risks)} 个商品，发现 {risk_count} 个风险商品。")
                else:
                    self._notice(self, "标题风险检测完成", "未发现风险商品。")

        # 终态统一：先解冻（清除冻结显示顺序），再按当前有效结果排序一次
        self._exit_detecting()
        self._sort_risk_pinned()

    # ------------------------------------------------------------------
    # 图片检测
    # ------------------------------------------------------------------

    def _on_image_risk_check(self) -> None:
        """图片风险检测按钮点击。"""
        if self._image_risk_service is None:
            self._notice(self, "提示", "图片风险检测尚未配置，请先在设置中绑定图片检测API。", level="warning")
            return
        if self._detecting_active:
            return
        result = self._show_detect_confirm("图片")
        if result is None:
            return
        targets, _ = result
        self._start_image_risk_check(targets)

    def _start_image_risk_check(self, targets: list[CandidateProduct]) -> None:
        """启动图片风险检测（保持 10/批，批次结果逐批回 UI）。"""
        self._enter_detecting(targets)
        # 预应用运行期缓存 + 统计缺图，进度从实际剩余 API 商品开始
        missing, hits = self._preapply_image_cache(targets)
        self._detect_processed += missing + hits
        self._detect_failed += missing
        self._update_detect_status(
            "图片检测", self._detect_processed, len(targets),
            self._detect_risks, self._detect_failed, 0, 0, "预计剩余",
        )
        self.btn_infringement_check.setText("取消图片检测")
        self.btn_infringement_check.setEnabled(True)
        self.btn_infringement_check.setStyleSheet("background:#FFF4E5;color:#C77600;border:1px solid #FFD59E;border-radius:6px;")
        self.btn_infringement_check.clicked.disconnect()
        self.btn_infringement_check.clicked.connect(self._cancel_current_detect)

        products = [
            {"id": p.product_id, "title": p.title, "main_image": p.main_image}
            for p in targets
        ]
        self._cancel_requested = False

        self._image_risk_thread = QThread(self)
        self._image_risk_worker = _ImageRiskWorker(
            self._image_risk_service, products, force_refresh=False,
            cancel_requested=lambda: self._cancel_requested,
        )
        self._image_risk_worker.moveToThread(self._image_risk_thread)
        self._image_risk_thread.started.connect(self._image_risk_worker.run)
        self._image_risk_worker.finished.connect(self._on_image_risk_finished)
        self._image_risk_worker.finished.connect(self._image_risk_thread.quit)
        batch_signal = getattr(self._image_risk_worker, "batch_result", None)
        if batch_signal is not None:
            batch_signal.connect(self._on_image_batch_result)
        self._image_risk_thread.finished.connect(self._image_risk_worker.deleteLater)
        self._image_risk_thread.finished.connect(self._image_risk_thread.deleteLater)
        self._image_risk_thread.finished.connect(self._on_image_risk_thread_cleanup)
        self._image_risk_thread.start()

    def _on_image_risk_finished(self, risks: list, stats: dict, error: str) -> None:
        """图片风险检测完成回调（终态：应用结果 → 解冻 → 排序一次）。"""
        # 恢复按钮文字和连接
        self.btn_infringement_check.setText("图片检测")
        self.btn_infringement_check.setStyleSheet("")
        try:
            self.btn_infringement_check.clicked.disconnect()
        except RuntimeError:
            pass
        self.btn_infringement_check.clicked.connect(self._on_image_risk_check)

        snapshot_ids = {p.product_id for p in (self._detect_snapshot or self._get_keep_products())}
        if error:
            self.lbl_status.setText("图片检测失败")
            self._notice(self, "图片风险检测失败", error, level="error")
        else:
            # 无论是否取消，先应用本次成功结果（批次已应用，此处幂等兜底）
            all_checked = stats.get("all_checked", [])
            checked_map = {r.product_id: r for r in all_checked}
            for pid, card in self._cards.items():
                if pid not in snapshot_ids:
                    continue
                if pid in checked_map:
                    item = checked_map[pid]
                    card.set_image_risk_data(item.risk, item.reason)
            risk_count = stats.get("risk_count", 0)
            failed = stats.get("failed_count", 0)
            # 根据取消状态显示不同消息
            if self._cancel_requested:
                self.lbl_status.setText(
                    f"检测已取消 · 已完成 {self._detect_processed}/{len(snapshot_ids)} · 已按现有结果排序"
                )
            elif failed > 0 and not all_checked and stats.get("cached_count", 0) == 0:
                self.lbl_status.setText("检测失败 · 已按现有有效结果排序")
            elif failed > 0:
                self.lbl_status.setText(
                    "检测完成 · "
                    f"<span style='color:#C62828;font-weight:600;'>失败 {failed} 个</span>"
                    " · 风险商品已置顶"
                )
            else:
                self.lbl_status.setText("检测完成 · 风险商品已置顶")
            if not self._cancel_requested and failed == 0 and risk_count > 0:
                self._notice(self, "图片风险检测完成", f"共处理 {stats.get('requested_count', 0)} 个商品，发现 {risk_count} 个风险商品。")
            elif not self._cancel_requested and failed == 0:
                self._notice(self, "图片风险检测完成", "未发现风险商品。")
            elif not self._cancel_requested and failed > 0 and all_checked:
                self._notice(self, "图片风险检测完成",
                             f"共处理 {stats.get('requested_count', 0)} 个商品，{failed} 个失败，发现 {risk_count} 个风险商品。")
            elif not self._cancel_requested and failed > 0 and not all_checked and stats.get("cached_count", 0) == 0:
                self._notice(self, "图片风险检测完成",
                             f"共处理 {stats.get('requested_count', 0)} 个商品，{failed} 个失败，未获得新的有效结果。")

        # 终态统一：先解冻（清除冻结显示顺序），再按当前有效结果排序一次
        self._exit_detecting()
        self._sort_risk_pinned()

    # ------------------------------------------------------------------
    # 全部检测（标题 + 图片顺序执行）
    # ------------------------------------------------------------------

    def _on_detect_all(self) -> None:
        """全部检测按钮点击：先标题检测，完成后图片检测。"""
        if self._title_risk_service is None:
            self._notice(self, "提示", "标题风险检测尚未配置，请先在设置中绑定文字API。", level="warning")
            return
        if self._image_risk_service is None:
            self._notice(self, "提示", "图片风险检测尚未配置，请先在设置中绑定图片检测API。", level="warning")
            return
        if self._detecting_active:
            return
        result = self._show_detect_confirm("标题 + 图片")
        if result is None:
            return
        targets, _ = result
        self._detect_all_targets = targets
        self._detect_all_phase = "title"
        self._detect_all_title_failed = 0
        self._start_title_risk_check_for_all(targets)

    def _start_title_risk_check_for_all(self, targets: list[CandidateProduct]) -> None:
        """全部检测的标题阶段（20/批，阶段结束不断开冻结直接进图片阶段）。"""
        self._enter_detecting(targets)
        self._update_detect_status("全部检测·标题", 0, len(targets), 0, 0, 0, 0, "预计本阶段剩余")
        self.btn_detect_all.setText("取消全部检测")
        self.btn_detect_all.setEnabled(True)
        self.btn_detect_all.setStyleSheet("background:#FFF4E5;color:#C77600;border:1px solid #FFD59E;border-radius:6px;")
        self.btn_detect_all.clicked.disconnect()
        self.btn_detect_all.clicked.connect(self._cancel_current_detect)

        titles = [{"id": p.product_id, "title": p.title} for p in targets]
        self._cancel_requested = False

        self._title_risk_thread = QThread(self)
        self._title_risk_worker = _TitleRiskWorker(self._title_risk_service, titles, cancel_requested=lambda: self._cancel_requested)
        self._title_risk_worker.moveToThread(self._title_risk_thread)
        self._title_risk_thread.started.connect(self._title_risk_worker.run)
        self._title_risk_worker.finished.connect(self._on_detect_all_title_finished)
        self._title_risk_worker.finished.connect(self._title_risk_thread.quit)
        batch_signal = getattr(self._title_risk_worker, "batch_result", None)
        if batch_signal is not None:
            batch_signal.connect(self._on_detect_all_title_batch_result)
        self._title_risk_thread.finished.connect(self._title_risk_worker.deleteLater)
        self._title_risk_thread.finished.connect(self._title_risk_thread.deleteLater)
        self._title_risk_thread.finished.connect(self._on_title_risk_thread_cleanup)
        self._title_risk_thread.start()

    def _on_detect_all_title_finished(self, risks: list, error: str) -> None:
        """全部检测的标题阶段完成。

        标题阶段结束：不排序、不解冻，直接进入图片阶段（除非 error / 用户取消）。
        """
        snapshot_ids = {p.product_id for p in (self._detect_snapshot or self._get_keep_products())}
        if error:
            self.lbl_status.setText("标题检测失败")
            self._notice(self, "标题风险检测失败", error, level="error")
            self._restore_detect_all_button()
            # 终态统一：先解冻再排序一次
            self._exit_detecting()
            self._sort_risk_pinned()
            return

        # 更新标题风险（批次已应用，此处幂等兜底）
        risk_map = {r.product_id: r for r in risks}
        for pid, card in self._cards.items():
            if pid not in snapshot_ids:
                continue
            if pid in risk_map:
                r = risk_map[pid]
                card.set_title_risk_data(r.risk, r.reason)
        # 缺失/非法结果统计为失败（不中止，继续图片检测）
        self._detect_all_title_failed = len(snapshot_ids - set(risk_map))

        # 检查取消
        if self._cancel_requested:
            self.lbl_status.setText(
                f"检测已取消 · 已完成 {self._detect_processed}/{len(snapshot_ids)} · 已按现有结果排序"
            )
            self._restore_detect_all_button()
            # 终态统一：先解冻再排序一次
            self._exit_detecting()
            self._sort_risk_pinned()
            return

        # 继续图片检测阶段（保持冻结，不排序、不解冻、不重建卡片）
        self._detect_all_phase = "image"
        # 重置阶段进度统计（标题失败数保留供最终合并）
        self._batch_times = []
        self._detect_processed = 0
        self._detect_risks = 0
        self._detect_failed = 0
        targets = self._detect_all_targets or []
        missing, hits = self._preapply_image_cache(targets)
        self._detect_processed += missing + hits
        self._detect_failed += missing
        self._update_detect_status(
            "全部检测·图片", self._detect_processed, len(targets),
            self._detect_risks, self._detect_failed, 0, 0, "预计本阶段剩余",
        )
        products = [
            {"id": p.product_id, "title": p.title, "main_image": p.main_image}
            for p in targets
        ]

        self._image_risk_thread = QThread(self)
        self._image_risk_worker = _ImageRiskWorker(
            self._image_risk_service, products, force_refresh=False,
            cancel_requested=lambda: self._cancel_requested,
        )
        self._image_risk_worker.moveToThread(self._image_risk_thread)
        self._image_risk_thread.started.connect(self._image_risk_worker.run)
        self._image_risk_worker.finished.connect(self._on_detect_all_image_finished)
        self._image_risk_worker.finished.connect(self._image_risk_thread.quit)
        batch_signal = getattr(self._image_risk_worker, "batch_result", None)
        if batch_signal is not None:
            batch_signal.connect(self._on_detect_all_image_batch_result)
        self._image_risk_thread.finished.connect(self._image_risk_worker.deleteLater)
        self._image_risk_thread.finished.connect(self._image_risk_thread.deleteLater)
        self._image_risk_thread.finished.connect(self._on_image_risk_thread_cleanup)
        self._image_risk_thread.start()

    def _on_detect_all_image_finished(self, risks: list, stats: dict, error: str) -> None:
        """全部检测的图片阶段完成（终态：应用结果 → 解冻 → 综合排序一次）。"""
        snapshot_ids = {p.product_id for p in (self._detect_snapshot or self._get_keep_products())}
        if error:
            self.lbl_status.setText("图片检测失败")
            self._notice(self, "图片风险检测失败", error, level="error")
        else:
            # 无论是否取消，先应用本次成功结果（批次已应用，此处幂等兜底）
            all_checked = stats.get("all_checked", [])
            checked_map = {r.product_id: r for r in all_checked}
            for pid, card in self._cards.items():
                if pid not in snapshot_ids:
                    continue
                if pid in checked_map:
                    item = checked_map[pid]
                    card.set_image_risk_data(item.risk, item.reason)

            failed = stats.get("failed_count", 0)
            title_failed = getattr(self, "_detect_all_title_failed", 0)
            # 根据取消状态和失败数量显示不同消息（标题失败 + 图片失败合并为一条）
            if self._cancel_requested:
                self.lbl_status.setText(
                    f"检测已取消 · 已完成 {self._detect_processed}/{len(snapshot_ids)} · 已按现有结果排序"
                )
            else:
                parts = []
                if title_failed > 0:
                    parts.append(f"标题失败 {title_failed} 个")
                if failed > 0:
                    parts.append(f"图片失败 {failed} 个")
                if not parts:
                    self.lbl_status.setText("检测完成 · 风险商品已置顶")
                else:
                    parts.append("风险商品已置顶")
                    self.lbl_status.setText("检测完成 · " + " · ".join(parts))
                if not self._cancel_requested and (title_failed > 0 or failed > 0):
                    self._notice(self, "风险检测完成",
                                 f"标题失败 {title_failed} 个，图片失败 {failed} 个。")

        self._restore_detect_all_button()
        # 终态统一：先解冻（清除冻结显示顺序），再综合排序一次并回到顶部
        self._exit_detecting()
        self._sort_risk_pinned()

    def _restore_detect_all_button(self) -> None:
        """恢复全部检测按钮状态。"""
        self.btn_detect_all.setText("全部检测")
        self.btn_detect_all.setStyleSheet("")
        try:
            self.btn_detect_all.clicked.disconnect()
        except RuntimeError:
            pass
        self.btn_detect_all.clicked.connect(self._on_detect_all)


# ── AI 风险检测 Worker ──────────────────────────────────────────


class _TitleRiskWorker(QObject):
    """标题风险检测后台线程。"""

    finished = Signal(list, str)  # (risks, error)
    # 每批完成：
    # (batch_results, batch_failed, batch_index, total_batches, elapsed_ms)
    batch_result = Signal(list, int, int, int, float)

    def __init__(self, service, titles: list, *, cancel_requested: callable | None = None) -> None:
        super().__init__()
        self._service = service
        self._titles = titles
        self._cancel_requested = cancel_requested

    @Slot()
    def run(self) -> None:
        cancelled_logged = False

        def log_cancel_once() -> None:
            """每次 worker 最多记录一次用户取消。"""
            nonlocal cancelled_logged
            if not cancelled_logged:
                product_risk_log.title_scan_cancelled()
                cancelled_logged = True

        def emit_batch(results, failed, batch_index, total_batches, elapsed_ms) -> None:
            """批次结果跨线程转发到 UI 主线程（不直接碰 QWidget）。"""
            self.batch_result.emit(results, failed, batch_index, total_batches, elapsed_ms)

        try:
            # 标题检测分批次顺序执行，取消在批次开始前检查
            if self._cancel_requested and self._cancel_requested():
                log_cancel_once()
                self.finished.emit([], "")
                return
            risks = self._service.scan(
                self._titles,
                cancel_requested=self._cancel_requested,
                on_batch=emit_batch,
            )
            if self._cancel_requested and self._cancel_requested():
                # 请求进行期间用户点击取消：请求自然完成，但取消行为必须记录
                log_cancel_once()
            self.finished.emit(risks, "")
        except Exception as exc:
            # 请求进行期间用户取消且请求异常（超时/HTTP/网络/解析等）：
            # 取消日志同样不能丢，且只记录一次
            if self._cancel_requested and self._cancel_requested():
                log_cancel_once()
            self.finished.emit([], str(exc))


class _ImageRiskWorker(QObject):
    """图片风险检测后台线程。"""

    finished = Signal(list, dict, str)  # (risky_items, stats_dict, error)
    # 每批完成：
    # (batch_results, batch_failed, batch_index, total_batches, elapsed_ms)
    batch_result = Signal(list, int, int, int, float)

    def __init__(self, service, products: list, *, force_refresh: bool = False,
                 cancel_requested: callable | None = None) -> None:
        super().__init__()
        self._service = service
        self._products = products
        self._force_refresh = force_refresh
        self._cancel_requested = cancel_requested

    @Slot()
    def run(self) -> None:
        def emit_batch(results, failed, batch_index, total_batches, elapsed_ms) -> None:
            """批次结果跨线程转发到 UI 主线程（不直接碰 QWidget）。"""
            self.batch_result.emit(results, failed, batch_index, total_batches, elapsed_ms)

        try:
            risky_items, stats_obj, all_checked = self._service.scan_batch(
                self._products, force_refresh=self._force_refresh,
                cancel_requested=self._cancel_requested,
                on_batch=emit_batch,
            )
            stats = {
                "requested_count": stats_obj.requested_count,
                "cached_count": stats_obj.cached_count,
                "checked_count": stats_obj.checked_count,
                "risk_count": stats_obj.risk_count,
                "failed_count": stats_obj.failed_count,
                "all_checked": all_checked,
            }
            self.finished.emit(risky_items, stats, "")
        except Exception as exc:
            self.finished.emit([], {"requested_count": 0, "cached_count": 0, "checked_count": 0, "risk_count": 0, "failed_count": 0, "all_checked": []}, str(exc))
