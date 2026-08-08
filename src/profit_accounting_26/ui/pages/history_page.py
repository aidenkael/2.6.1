"""历史页：单一大表格（8 个视觉列），全部读取保存时的快照，不重新计算。

列（从左到右）：序号 / 图片 / 名称 / 成本 / 售价 / 利润 / 包装数据 / 校准内容。
- 序号仅用于查看排序，不是 record_id；
- 图片单元格固定显示两个缩略图，第二张缺失时显示等尺寸占位框；
- 名称下方显示原始商品链接（只读、无边框，可光标移动查看完整 URL）；
- 校准内容区分“用户主观修正（待实测）”与“真实发货实测（已校准）”。

删除为永久删除：记录 + 快照 + 绑定校准反馈 + 独占图片；
内容寻址共享图片仅当无其他记录引用时才物理删除，不实现回收站。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from profit_accounting_26.application import AppContext
from profit_accounting_26.application.data_contracts import record_from_payload
from profit_accounting_26.application.profit_scenario_codec import extract_profit_scenarios
from profit_accounting_26.ui.pages.calibration_feedback_dialog import CalibrationFeedbackDialog
from profit_accounting_26.ui.widgets import Card, ImagePreviewDialog, SectionHeader, confirm_action

_THUMB_SIZE = 48
_ROW_HEIGHT = 76
_PLACEHOLDER_COLOR = QColor("#E7ECF3")
_RECORD_ID_ROLE = 256

# 轻量本地近义词组：输入组内任一词可命中同组其他名称。需要扩充时直接维护这里。
_SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("挂绳", "手机绳", "腕带", "手机链", "挂饰", "挂件", "包挂"),
    ("袜子", "袜", "短袜", "长袜", "五指袜"),
    ("胸针", "别针", "徽章"),
    ("钥匙扣", "钥匙链", "钥匙圈"),
    ("镜子", "化妆镜", "随身镜", "梳妆镜"),
    ("手套", "半指手套", "健身手套"),
    ("帽子", "帽", "鸭舌帽", "针织帽"),
    ("钱包", "零钱包", "卡包", "长钱包"),
    ("腰带", "皮带", "裤带"),
    ("扇子", "折扇", "团扇"),
    ("项链", "锁骨链", "吊坠"),
    ("手链", "手串", "手镯"),
    ("耳环", "耳钉", "耳饰"),
    ("戒指", "指环"),
    ("发夹", "发箍", "发饰", "发绳"),
)


def expand_search_terms(query: str) -> list[str]:
    """把查询词扩展为本地近义词集合（包含匹配，命中组内任一词即返回整组）。"""
    text = query.strip().lower()
    if not text:
        return []
    terms = {text}
    for group in _SYNONYM_GROUPS:
        if any(text == term or text in term or term in text for term in group):
            terms.update(group)
    return sorted(terms)


def _placeholder_icon(size: int = _THUMB_SIZE) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(_PLACEHOLDER_COLOR)
    return QIcon(pixmap)


def _icon_from_path(path: Path | None, size: int = _THUMB_SIZE) -> QIcon:
    if path is None or not path.is_file():
        return _placeholder_icon(size)
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return _placeholder_icon(size)
    return QIcon(
        pixmap.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "—"
    return f"{number:g}"


def _fmt_usd(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "—"
    return f"${number:.2f}"


def _fmt_rmb(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "—"
    return f"¥{number:.2f}"


def _fmt_percent(value: Any, *, legacy_percent: bool) -> str:
    number = _num(value)
    if number is None:
        return "—"
    return f"{number:.2f}%" if legacy_percent else f"{number * 100:.2f}%"


def _dims_text(raw: dict[str, Any] | None) -> str:
    """格式：L×W×H / 重量g；完全缺失返回 —。"""
    if not isinstance(raw, dict):
        return "—"
    parts = [_fmt(raw.get("length_cm")), _fmt(raw.get("width_cm")), _fmt(raw.get("height_cm"))]
    weight = raw.get("weight_g")
    if all(part == "—" for part in parts) and _num(weight) is None:
        return "—"
    dims = "×".join(parts)
    return f"{dims} / {_fmt(weight)}g" if _num(weight) is not None else dims


class HistoryPage(QWidget):
    recordRequested = Signal(str)

    COLUMN_COUNT = 8
    COLUMN_HEADERS = ("序号", "图片", "名称", "成本", "售价", "利润", "包装数据", "校准内容")

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.records: list[dict[str, Any]] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 18)
        layout.setSpacing(12)

        card = Card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(10)
        header = SectionHeader("历史记录管理", "裸品 → AI估算 → 当前采用 → 保存 → 实际校准")

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索商品……")
        self.search.setFixedWidth(240)
        self.search.setFixedHeight(32)
        self.search.returnPressed.connect(self.refresh)
        self.search.textChanged.connect(lambda _text: self.refresh())
        refresh = QPushButton("刷新")
        self.open_button = QPushButton("返回测算页编辑")
        self.open_button.setProperty("primary", True)
        self.calibrate_button = QPushButton("编辑校准")
        self.delete_button = QPushButton("删除")
        for button in (refresh, self.open_button, self.calibrate_button, self.delete_button):
            button.setFixedHeight(32)
        refresh.clicked.connect(self.refresh)
        self.open_button.clicked.connect(self.open_selected)
        self.calibrate_button.clicked.connect(self._open_calibration_dialog)
        self.delete_button.clicked.connect(self._archive_selected)
        header.right_layout.addWidget(self.search)
        header.right_layout.addWidget(refresh)
        header.right_layout.addWidget(self.open_button)
        header.right_layout.addWidget(self.calibrate_button)
        header.right_layout.addWidget(self.delete_button)
        card_layout.addWidget(header)

        self.table = QTableWidget(0, self.COLUMN_COUNT)
        self.table.setHorizontalHeaderLabels(list(self.COLUMN_HEADERS))
        # 列宽重分配：序号/图片窄固定；名称与包装数据吃多余空间；不 Stretch 尾列
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 52)
        self.table.setColumnWidth(1, _THUMB_SIZE * 2 + 24)
        self.table.setColumnWidth(2, 260)
        self.table.setColumnWidth(3, 250)
        self.table.setColumnWidth(4, 120)
        self.table.setColumnWidth(5, 160)
        self.table.setColumnWidth(6, 200)
        self.table.setColumnWidth(7, 190)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(_ROW_HEIGHT)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._update_action_states)
        self.table.cellDoubleClicked.connect(lambda _row, _col: self.open_selected())
        card_layout.addWidget(self.table)
        layout.addWidget(card, 1)
        self._update_action_states()
        self.refresh()

    # ---------------------------------------------------------------- list

    def refresh(self) -> None:
        payloads = self.context.record_service.list()
        terms = expand_search_terms(self.search.text())
        self.records = [
            payload
            for payload in payloads
            if str(payload.get("status") or "active") != "archived"
            and self._matches(payload, terms)
        ]
        self.table.setRowCount(0)
        for payload in self.records:
            self._append_row(payload)
        self._update_action_states()
        if self.records:
            self.table.selectRow(0)

    @staticmethod
    def _matches(payload: dict[str, Any], terms: list[str]) -> bool:
        if not terms:
            return True
        haystack = " ".join(
            (
                str(payload.get("product_name") or ""),
                str(payload.get("product_link") or ""),
                str(payload.get("id") or ""),
            )
        ).lower()
        return any(term in haystack for term in terms)

    def _append_row(self, payload: dict[str, Any]) -> None:
        record_id = str(payload.get("id") or "")
        row = self.table.rowCount()
        self.table.insertRow(row)
        anchor = QTableWidgetItem(str(row + 1))
        anchor.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        anchor.setData(_RECORD_ID_ROLE, record_id)
        self.table.setItem(row, 0, anchor)
        self.table.setCellWidget(row, 1, self._build_image_cell(payload))
        self.table.setCellWidget(row, 2, self._build_name_cell(payload))
        self.table.setCellWidget(row, 3, self._multiline_cell(self._cost_text(payload)))
        self.table.setCellWidget(row, 4, self._multiline_cell(self._price_text(payload)))
        self.table.setCellWidget(row, 5, self._multiline_cell(self._profit_text(payload)))
        self.table.setCellWidget(row, 6, self._multiline_cell(self._packaging_text(payload)))
        self.table.setCellWidget(row, 7, self._multiline_cell(self._calibration_text(payload)))

    @staticmethod
    def _multiline_cell(text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setContentsMargins(6, 4, 6, 4)
        return label

    # ---------------------------------------------------------------- cells

    def _build_image_cell(self, payload: dict[str, Any]) -> QWidget:
        container = QWidget()
        row_layout = QHBoxLayout(container)
        row_layout.setContentsMargins(6, 4, 6, 4)
        row_layout.setSpacing(6)
        images = [item for item in (payload.get("images") or []) if isinstance(item, dict)]
        images.sort(key=lambda item: item.get("order", 0))
        # 固定两个缩略图位置：第二张缺失时显示等尺寸占位框，保持所有行对齐
        for index in range(2):
            item = images[index] if index < len(images) else None
            button = QPushButton()
            button.setFixedSize(_THUMB_SIZE, _THUMB_SIZE)
            button.setIconSize(QSize(_THUMB_SIZE - 8, _THUMB_SIZE - 8))
            original = self._image_path(item, prefer_thumbnail=False) if item else None
            thumbnail = self._image_path(item, prefer_thumbnail=True) if item else None
            if original is None and thumbnail is None:
                button.setIcon(_placeholder_icon(_THUMB_SIZE - 8))
            else:
                button.setIcon(_icon_from_path(thumbnail or original, _THUMB_SIZE - 8))
                target = original or thumbnail
                button.clicked.connect(
                    lambda _checked=False, path=target: ImagePreviewDialog(path, self).exec()
                )
            row_layout.addWidget(button)
        row_layout.addStretch(1)
        return container

    def _build_name_cell(self, payload: dict[str, Any]) -> QWidget:
        container = QWidget()
        column = QVBoxLayout(container)
        column.setContentsMargins(6, 4, 6, 4)
        column.setSpacing(2)
        name = str(payload.get("product_name") or "未命名商品")
        name_label = QLabel(name)
        name_label.setWordWrap(False)
        column.addWidget(name_label)
        link = str(payload.get("product_link") or "").strip()
        if link:
            link_edit = QLineEdit(link)
            link_edit.setReadOnly(True)
            link_edit.setFrame(False)
            link_edit.setProperty("muted", True)
            link_edit.setFixedHeight(20)
            link_edit.setToolTip(link)
            column.addWidget(link_edit)
        else:
            placeholder = QLabel("—")
            placeholder.setProperty("muted", True)
            column.addWidget(placeholder)
        return container

    # ---------------------------------------------------------------- texts

    def _cost_text(self, payload: dict[str, Any]) -> str:
        """成本四行全部读取保存快照；历史页不重新计算旧记录。"""
        layers = payload.get("layers") if isinstance(payload.get("layers"), dict) else {}
        calculated = layers.get("calculated") if isinstance(layers.get("calculated"), dict) else {}
        quote = calculated.get("logistics_quote") if isinstance(calculated.get("logistics_quote"), dict) else {}
        forwarder_name = str(calculated.get("forwarder_name") or "").strip()
        total = _fmt_rmb(calculated.get("system_cost_rmb"))
        domestic = f"{_fmt_rmb(payload.get('product_cost_rmb'))} + {_fmt_rmb(payload.get('domestic_shipping_rmb'))}"
        if quote and forwarder_name:
            first_mile = f"{forwarder_name}  {_fmt_rmb(quote.get('weight_fee_rmb'))} + {_fmt_rmb(quote.get('fixed_fee_rmb'))}"
        else:
            first_mile = "—"
        tail_rmb = _num(quote.get("tail_fee_rmb")) if quote else None
        rate = _num(calculated.get("exchange_rate"))
        if tail_rmb is None:
            tail = "—"
        elif rate:
            tail = f"${tail_rmb / rate:.2f} / ¥{tail_rmb:.2f}"
        else:
            tail = f"— / ¥{tail_rmb:.2f}"
        return f"总成本    {total}\n国内成本  {domestic}\n头程      {first_mile}\n尾程      {tail}"

    def _price_text(self, payload: dict[str, Any]) -> str:
        scenarios = extract_profit_scenarios(payload) or {}
        no_activity = scenarios.get("no_activity") or {}
        activity = scenarios.get("activity") or {}
        quote_usd = _fmt_usd(payload.get("shein_quote_usd"))
        return (
            f"核价      {quote_usd}\n"
            f"标价      {_fmt_usd(no_activity.get('sale_price_usd'))}\n"
            f"活动后    {_fmt_usd(activity.get('sale_price_usd'))}"
        )

    def _profit_text(self, payload: dict[str, Any]) -> str:
        scenarios = extract_profit_scenarios(payload) or {}
        legacy = bool(scenarios.get("_legacy_compatible") or scenarios.get("legacy_compatible"))
        no_activity = scenarios.get("no_activity") or {}
        activity = scenarios.get("activity") or {}
        layers = payload.get("layers") if isinstance(payload.get("layers"), dict) else {}
        calculated = layers.get("calculated") if isinstance(layers.get("calculated"), dict) else {}
        normal_rate = no_activity.get("profit_rate_on_cost")
        if normal_rate is None:
            normal_rate_text = _fmt_percent(calculated.get("profit_rate_percent"), legacy_percent=True)
        else:
            normal_rate_text = _fmt_percent(normal_rate, legacy_percent=legacy)
        normal = f"{_fmt_rmb(no_activity.get('profit_rmb'))} / {normal_rate_text}"
        if activity:
            activity_text = (
                f"{_fmt_rmb(activity.get('profit_rmb'))} / "
                f"{_fmt_percent(activity.get('profit_rate_on_cost'), legacy_percent=legacy)}"
            )
        else:
            activity_text = "—"
        return f"普通      {normal}\n活动      {activity_text}"

    def _packaging_text(self, payload: dict[str, Any]) -> str:
        layers = payload.get("layers") if isinstance(payload.get("layers"), dict) else {}
        adopted = layers.get("adopted") if isinstance(layers.get("adopted"), dict) else {}
        bare = _dims_text(adopted.get("bare"))
        v2 = record_from_payload(payload)
        ai_text = "—"
        ai_initial = v2.ai_initial
        # 旧记录没有 ai_initial 时安全 fallback，不伪造第一次 AI 数据
        if isinstance(ai_initial, dict) and "legacy_layers_ai_raw" not in ai_initial:
            adopted_packaging = ai_initial.get("adopted_packaging")
            if isinstance(adopted_packaging, dict):
                ai_text = _dims_text(adopted_packaging.get("normal"))
        current = _dims_text(v2.current_estimate)
        return f"裸品    {bare}\nAI      {ai_text}\n当前    {current}"

    def _calibration_text(self, payload: dict[str, Any]) -> str:
        """用户层面只有两态：未校准 / 已校准 + dims + note。

        dims 优先级：实测 > 用户建议 > 当前采用。
        """
        v2 = record_from_payload(payload)
        if not v2.calibration_feedback_id:
            return "未校准"
        try:
            feedback = self.context.calibration_feedback_service.load(v2.calibration_feedback_id)
        except KeyError:
            return "未校准"
        dims_raw: dict[str, Any] | None = None
        actual = feedback.actual_logistics
        if actual is not None and actual.has_content():
            dims_raw = {
                **(actual.actual_package_dimensions or {}),
                "weight_g": actual.actual_package_weight_g,
            }
        suggested = feedback.suggested_package
        if dims_raw is None and suggested is not None and suggested.has_content():
            dims_raw = {
                "length_cm": suggested.length_cm,
                "width_cm": suggested.width_cm,
                "height_cm": suggested.height_cm,
                "weight_g": suggested.weight_g,
            }
        if dims_raw is None and isinstance(v2.current_estimate, dict):
            dims_raw = dict(v2.current_estimate)
        lines = ["已校准"]
        dims_text = _dims_text(dims_raw)
        if dims_text != "—":
            lines.append(dims_text)
        note = str(feedback.user_note or "").strip().replace("\n", " ")
        if note:
            lines.append(note[:40])
        return "\n".join(lines)

    # ---------------------------------------------------------------- actions

    def selected_record_id(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return str(item.data(_RECORD_ID_ROLE)) if item and item.data(_RECORD_ID_ROLE) else None

    def _update_action_states(self) -> None:
        enabled = self.selected_record_id() is not None
        self.open_button.setEnabled(enabled)
        self.calibrate_button.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)

    def open_selected(self) -> None:
        record_id = self.selected_record_id()
        if not record_id:
            return
        self.recordRequested.emit(record_id)

    def _open_calibration_dialog(self) -> None:
        record_id = self.selected_record_id()
        if not record_id:
            return
        feedback = None
        v2 = self.context.history_record_v2_service.load_v2(record_id)
        if v2.calibration_feedback_id:
            try:
                feedback = self.context.calibration_feedback_service.load(v2.calibration_feedback_id)
            except KeyError:
                feedback = None
        dialog = CalibrationFeedbackDialog(self.context, record_id, feedback=feedback, parent=self)
        if dialog.exec():
            self.refresh()

    def _archive_selected(self) -> None:
        """永久删除：记录 + 绑定校准反馈 + 独占图片；不实现回收站。"""
        record_id = self.selected_record_id()
        if not record_id:
            return
        confirmed = confirm_action(
            self,
            "删除记录",
            "确定永久删除这条历史记录吗？删除后无法恢复。",
            confirm_text="删除",
            danger=True,
        )
        if not confirmed:
            return
        self.context.record_service.delete_record(record_id)
        self.context.diagnostic_logger.event("record_deleted", record_id=record_id)
        self.refresh()

    # ---------------------------------------------------------------- helpers

    def _image_path(self, item: dict[str, Any], *, prefer_thumbnail: bool) -> Path | None:
        key = item.get("thumbnail_key") if prefer_thumbnail else None
        if not key:
            key = item.get("storage_key") or item.get("relative_path")
        if not key:
            return None
        path = self.context.paths.data_dir / key
        return path if path.is_file() else None
