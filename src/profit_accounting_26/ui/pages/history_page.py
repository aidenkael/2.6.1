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
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from profit_accounting_26.application import AppContext
from profit_accounting_26.application.calibration_export_service import (
    ExportIncompleteError,
)
from profit_accounting_26.application.data_contracts import record_from_payload
from profit_accounting_26.application.profit_scenario_codec import extract_profit_scenarios
from profit_accounting_26.ui.pages.calibration_feedback_dialog import CalibrationFeedbackDialog
from profit_accounting_26.ui.widgets import Card, ImagePreviewDialog, SectionHeader, confirm_action

_THUMB_SIZE = 48
_ROW_HEIGHT = 84
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


def _short_forwarder_name(name: str) -> str:
    """显示压缩：深圳货代→深圳、义乌货代→义乌；其它自定义货代不改名。"""
    if name in ("深圳货代", "义乌货代"):
        return name[:-2]
    return name


def _display_product_name(full_summary: str) -> str:
    """历史名称只显示完整商品摘要的第一段（第一个“；”之前）。

    底层仍保存完整摘要；这里只做显示层提取，不改动存储。
    无分隔符用完整字符串；为空保持“未命名商品”。
    """
    text = str(full_summary or "").strip()
    if not text:
        return "未命名商品"
    for separator in ("；", ";"):
        if separator in text:
            first = text.split(separator, 1)[0].strip()
            if first:
                return first
            break
    return text


_CALIBRATION_MAX_LINES = 3
_CALIBRATION_MAX_CHARS = 96


def _truncate_multiline(text: str) -> str:
    """校准内容显示层截断：最多 3 行、总字符数受限，超出追加“…”。

    完整原文由 QLabel tooltip 承载；行高不被超长反馈无限撑高。
    """
    lines = text.split("\n")
    display_lines = lines[:_CALIBRATION_MAX_LINES]
    display = "\n".join(display_lines)
    truncated = len(lines) > _CALIBRATION_MAX_LINES
    if len(display) > _CALIBRATION_MAX_CHARS:
        display = display[:_CALIBRATION_MAX_CHARS].rstrip()
        truncated = True
    if truncated:
        display = display.rstrip() + "…"
    return display


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
        header = SectionHeader("历史记录管理")

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
        self.export_button = QPushButton("导出校准反馈")
        self.export_button.setProperty("primary", True)
        for button in (
            refresh, self.open_button, self.calibrate_button,
            self.delete_button, self.export_button,
        ):
            button.setFixedHeight(32)
        refresh.clicked.connect(self.refresh)
        self.open_button.clicked.connect(self.open_selected)
        self.calibrate_button.clicked.connect(self._open_calibration_dialog)
        self.delete_button.clicked.connect(self._delete_selected)
        self.export_button.clicked.connect(self._export_calibration)
        # 导出校准反馈按钮放在搜索框之前（阶段 3 参考布局）
        header.right_layout.insertWidget(0, self.export_button)
        self._header_right_layout = header.right_layout
        header.right_layout.addWidget(self.search)
        header.right_layout.addWidget(refresh)
        header.right_layout.addWidget(self.open_button)
        header.right_layout.addWidget(self.calibrate_button)
        header.right_layout.addWidget(self.delete_button)
        card_layout.addWidget(header)

        self.table = QTableWidget(0, self.COLUMN_COUNT)
        self.table.setHorizontalHeaderLabels(list(self.COLUMN_HEADERS))
        # 列宽重分配：序号/图片窄固定；名称与包装数据吃多余空间；校准内容不 Stretch
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(1, _THUMB_SIZE * 2 + 16)
        self.table.setColumnWidth(2, 290)
        self.table.setColumnWidth(3, 235)
        self.table.setColumnWidth(4, 150)
        self.table.setColumnWidth(5, 200)
        # 包装数据列：足够一行显示"17×32×17 / 720g"类标准数据，不挤不换行
        self.table.setColumnWidth(6, 185)
        # 校准内容列继续承担主要剩余伸展宽度（Stretch）
        self.table.setColumnWidth(7, 290)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(_ROW_HEIGHT)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        # 纵向分隔线：浅灰 1px，header 与数据区域视觉连续；不增加横向滚动条
        self.table.setShowGrid(False)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setStyleSheet(
            "QTableWidget::item { border-right: 1px solid #DDE3EA; }"
            "QHeaderView::section { border-right: 1px solid #DDE3EA; }"
            "QHeaderView::section:last { border-right: none; }"
        )
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
        # 内容填充完成后自动调整行高，使多行文本不被裁切
        self.table.resizeRowsToContents()
        # 保证最小行高不低于图片列高度，防止图片列被压缩
        min_row_h = _THUMB_SIZE + 16
        for row in range(self.table.rowCount()):
            if self.table.rowHeight(row) < min_row_h:
                self.table.setRowHeight(row, min_row_h)
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
        self.table.setCellWidget(row, 1, self._with_column_border(self._build_image_cell(payload)))
        self.table.setCellWidget(row, 2, self._with_column_border(self._build_name_cell(payload)))
        self.table.setCellWidget(row, 3, self._with_column_border(self._kv_cell(self._cost_rows(payload))))
        self.table.setCellWidget(row, 4, self._with_column_border(self._kv_cell(self._price_rows(payload))))
        self.table.setCellWidget(row, 5, self._with_column_border(self._kv_cell(self._profit_rows(payload))))
        self.table.setCellWidget(row, 6, self._with_column_border(self._kv_cell(self._packaging_rows(payload))))
        self.table.setCellWidget(row, 7, self._calibration_cell(payload))

    @staticmethod
    def _with_column_border(container: QWidget, *, last: bool = False) -> QWidget:
        """给非最后一列单元格容器加 1px 浅灰纵向分隔线（选中高亮下仍可辨）。"""
        if not last:
            container.setStyleSheet("border-right: 1px solid #DDE3EA;")
        return container

    @staticmethod
    def _multiline_cell(text: str, *, tooltip: str | None = None) -> QWidget:
        """多行文字单元格：所有文字列第一行从统一顶部基线开始，不垂直居中。"""
        label = QLabel(text)
        label.setWordWrap(True)
        if tooltip:
            label.setToolTip(tooltip)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        container = QWidget()
        column = QVBoxLayout(container)
        column.setContentsMargins(6, 4, 6, 4)
        column.setSpacing(0)
        column.addWidget(label)
        column.addStretch(1)
        return container

    @staticmethod
    def _kv_cell(rows: list[tuple]) -> QWidget:
        """局部轻量 key/value 行布局：左侧字段名、右侧数值，不用空格模拟对齐。

        行可为 (key, value) 或 (key, value, bold)，bold 仅强调字段名。
        """
        container = QWidget()
        column = QVBoxLayout(container)
        column.setContentsMargins(6, 4, 6, 4)
        column.setSpacing(1)
        for row_data in rows:
            key, value = row_data[0], row_data[1]
            bold = bool(row_data[2]) if len(row_data) > 2 else False
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            key_label = QLabel(key)
            if bold:
                key_label.setStyleSheet("font-weight: 600;")
            value_label = QLabel(value)
            value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(key_label)
            row.addStretch(1)
            row.addWidget(value_label)
            column.addWidget(row_widget)
        column.addStretch(1)
        return container

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
        full_summary = str(payload.get("product_name") or "")
        name = _display_product_name(full_summary)
        name_label = QLabel(name)
        name_label.setWordWrap(False)
        # 名称只显示首段；悬停可见完整商品摘要
        if full_summary.strip() and full_summary.strip() != name:
            name_label.setToolTip(full_summary.strip())
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
        # 与其他文字列一致：内容顶部对齐
        column.addStretch(1)
        return container

    # ---------------------------------------------------------------- texts

    def _cost_rows(self, payload: dict[str, Any]) -> list[tuple]:
        """成本四行全部读取保存快照；历史页不重新计算旧记录。"""
        layers = payload.get("layers") if isinstance(payload.get("layers"), dict) else {}
        calculated = layers.get("calculated") if isinstance(layers.get("calculated"), dict) else {}
        quote = calculated.get("logistics_quote") if isinstance(calculated.get("logistics_quote"), dict) else {}
        forwarder_name = str(calculated.get("forwarder_name") or "").strip()
        rate = _num(calculated.get("exchange_rate"))
        total_rmb = _num(calculated.get("system_cost_rmb"))
        if total_rmb is None:
            total_value = "—"
        elif rate and rate > 0:
            # USD 必须用保存记录中的汇率快照，禁止用当前设置汇率补算
            total_value = f"¥{total_rmb:.2f} / ${total_rmb / rate:.2f}"
        else:
            total_value = f"¥{total_rmb:.2f} / $—"
        product_cost = _num(payload.get("product_cost_rmb")) or 0.0
        domestic_shipping = _num(payload.get("domestic_shipping_rmb")) or 0.0
        domestic = _fmt_rmb(product_cost + domestic_shipping)
        if quote and forwarder_name:
            weight_fee = _num(quote.get("weight_fee_rmb")) or 0.0
            fixed_fee = _num(quote.get("fixed_fee_rmb")) or 0.0
            first_mile_label = f"总头程（{_short_forwarder_name(forwarder_name)}）"
            first_mile_value = _fmt_rmb(weight_fee + fixed_fee)
        else:
            first_mile_label = "总头程"
            first_mile_value = "—"
        tail_rmb = _num(quote.get("tail_fee_rmb")) if quote else None
        if tail_rmb is None:
            tail_value = "—"
        elif rate and rate > 0:
            tail_value = f"¥{tail_rmb:.2f} / ${tail_rmb / rate:.2f}"
        else:
            tail_value = f"¥{tail_rmb:.2f} / $—"
        return [
            ("总成本", total_value, True),
            ("国内成本", domestic),
            (first_mile_label, first_mile_value),
            ("尾程", tail_value),
        ]

    def _price_rows(self, payload: dict[str, Any]) -> list[tuple]:
        """售价三行全部读取保存快照，禁止用当前利润规则重新计算。"""
        scenarios = extract_profit_scenarios(payload) or {}
        no_activity = scenarios.get("no_activity") or {}
        activity = scenarios.get("activity") or {}
        return [
            ("SHEIN标价", _fmt_usd(no_activity.get("sale_price_usd")), True),
            ("活动售价", _fmt_usd(activity.get("sale_price_usd")), True),
            ("SHEIN核价", _fmt_usd(payload.get("shein_quote_usd"))),
        ]

    def _profit_rows(self, payload: dict[str, Any]) -> list[tuple]:
        """利润列：标价利润 / 活动利润，全部读取保存的 profit_scenarios 快照。"""
        scenarios = extract_profit_scenarios(payload) or {}
        legacy = bool(scenarios.get("_legacy_compatible") or scenarios.get("legacy_compatible"))
        no_activity = scenarios.get("no_activity") or {}
        activity = scenarios.get("activity") or {}
        layers = payload.get("layers") if isinstance(payload.get("layers"), dict) else {}
        calculated = layers.get("calculated") if isinstance(layers.get("calculated"), dict) else {}
        # 标价利率：优先用保存的 profit_rate_on_cost；新双场景记录若缺失则用
        # profit_rmb / calculation_total_cost_rmb 计算（小数形式，如 0.40 表示 40%）；
        # 旧 legacy 记录 fallback 到 layers.calculated.profit_rate_percent
        normal_rate = no_activity.get("profit_rate_on_cost")
        if normal_rate is None and not legacy:
            total_cost = float(scenarios.get("calculation_total_cost_rmb") or 0)
            normal_profit = float(no_activity.get("profit_rmb") or 0)
            if total_cost > 0:
                normal_rate = normal_profit / total_cost  # 小数形式
        if normal_rate is None:
            normal_rate_text = _fmt_percent(calculated.get("profit_rate_percent"), legacy_percent=True)
        else:
            normal_rate_text = _fmt_percent(normal_rate, legacy_percent=legacy)
        list_price_value = f"{_fmt_rmb(no_activity.get('profit_rmb'))} / {normal_rate_text}"
        if activity:
            activity_value = (
                f"{_fmt_rmb(activity.get('profit_rmb'))} / "
                f"{_fmt_percent(activity.get('profit_rate_on_cost'), legacy_percent=legacy)}"
            )
        else:
            activity_value = "—"
        return [
            ("标价利润", list_price_value, True),
            ("活动利润", activity_value, True),
        ]

    def _packaging_rows(self, payload: dict[str, Any]) -> list[tuple]:
        """包装数据列 key/value 行：裸品 / AI首次 / 当前，左侧标题、右侧尺寸重量。

        采用 _kv_cell 局部布局，三行标题左对齐、三行数据右对齐，
        不依赖空格模拟对齐，正常尺寸重量在列宽内不换行。
        """
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
        return [("裸品", bare), ("AI", ai_text), ("当前", current)]

    def _packaging_text(self, payload: dict[str, Any]) -> str:
        """保留：供 tooltip 或外部文本引用；单元格渲染改用 _packaging_rows + _kv_cell。"""
        rows = self._packaging_rows(payload)
        return "\n".join(f"{key} {value}" for key, value in rows)

    def _calibration_text(self, payload: dict[str, Any]) -> str:
        """用户层面只有两态：未反馈 / 已反馈 + dims + note + 真实头程。

        dims 优先级：实测 > 用户建议 > 当前采用。
        """
        v2 = record_from_payload(payload)
        if not v2.calibration_feedback_id:
            return "未反馈"
        try:
            feedback = self.context.calibration_feedback_service.load(v2.calibration_feedback_id)
        except KeyError:
            return "未反馈"
        has_user_content = (
            bool(feedback.user_note)
            or (feedback.suggested_package is not None and feedback.suggested_package.has_content())
            or (feedback.actual_logistics is not None and feedback.actual_logistics.has_content())
            or feedback.structure.has_content()
        )
        if not has_user_content:
            return "未反馈"
        dims_raw: dict[str, Any] | None = None
        actual = feedback.actual_logistics
        # 真实头程本身不代表存在实测包装。仅在实际包装尺寸或重量确实
        # 保存过时，才让它覆盖 suggested/current 的包装显示。
        if actual is not None and (
            actual.actual_package_dimensions is not None
            or actual.actual_package_weight_g is not None
        ):
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
        lines = ["已反馈"]
        dims_text = _dims_text(dims_raw)
        if dims_text != "—":
            lines.append(dims_text)
        note = str(feedback.user_note or "").strip().replace("\n", " ")
        if note:
            lines.append(note)
        if actual is not None and actual.actual_first_mile_fee_rmb is not None:
            forwarder = str(actual.actual_forwarder or "").rstrip("货代").strip() or "—"
            lines.append(f"真实头程：{forwarder} ¥{float(actual.actual_first_mile_fee_rmb):g}")
        return "\n".join(lines)

    def _calibration_cell(self, payload: dict[str, Any]) -> QWidget:
        """校准内容单元格：显示层截断 + tooltip 完整原文，不新增弹窗/详情页。"""
        full_text = self._calibration_text(payload)
        display = _truncate_multiline(full_text)
        tooltip = full_text if display != full_text else None
        return self._multiline_cell(display, tooltip=tooltip)

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

    def _delete_selected(self) -> None:
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

    def _export_calibration(self) -> None:
        """导出校准反馈：全部 / 自定义范围 / 未导出部分，三选一。"""
        dialog = QDialog(self)
        dialog.setWindowTitle("导出校准反馈")
        form = QFormLayout(dialog)
        mode_combo = QComboBox()
        mode_combo.addItem("全部", "all")
        mode_combo.addItem("自定义范围", "range")
        mode_combo.addItem("未导出部分", "pending")
        range_edit = QLineEdit()
        range_edit.setPlaceholderText("例如 1-30")
        range_edit.setEnabled(False)

        def _on_mode_changed(_index: int) -> None:
            range_edit.setEnabled(mode_combo.currentData() == "range")

        mode_combo.currentIndexChanged.connect(_on_mode_changed)
        form.addRow("导出模式", mode_combo)
        form.addRow("范围", range_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        mode = str(mode_combo.currentData() or "all")
        dataset = self._export_dataset(mode)
        if not dataset:
            QMessageBox.information(self, "导出校准反馈", "当前没有可导出的历史记录。")
            return
        parent = QFileDialog.getExistingDirectory(
            self, "选择导出目录", str(self.context.paths.data_dir)
        )
        if not parent:
            return
        try:
            result = self.context.calibration_export_service.export(
                dataset,
                mode,
                parent,
                seq_range=range_edit.text().strip() if mode == "range" else None,
            )
        except (ValueError, ExportIncompleteError) as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        message = f"导出完成：\n{result.output_dir}\n共 {len(result.record_ids)} 条记录"
        if result.warnings:
            message += "\n\n警告（缩略图 fallback）：\n" + "\n".join(result.warnings[:10])
        QMessageBox.information(self, "导出校准反馈", message)

    def _export_dataset(self, mode: str) -> list[dict[str, Any]]:
        """导出数据集选择：

        - all / pending：全部未归档历史记录，不受当前搜索框影响；
        - range：当前 HistoryPage 可见记录（显示序号 → record_id 映射）。
        """
        if mode in ("all", "pending"):
            return [
                payload
                for payload in self.context.record_service.list()
                if str(payload.get("status") or "active") != "archived"
            ]
        return list(self.records)

    # ---------------------------------------------------------------- helpers

    def _image_path(self, item: dict[str, Any], *, prefer_thumbnail: bool) -> Path | None:
        key = item.get("thumbnail_key") if prefer_thumbnail else None
        if not key:
            key = item.get("storage_key") or item.get("relative_path")
        if not key:
            return None
        path = self.context.paths.data_dir / key
        return path if path.is_file() else None
