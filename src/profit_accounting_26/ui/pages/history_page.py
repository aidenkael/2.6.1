from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from profit_accounting_26.application import AppContext
from profit_accounting_26.application.data_contracts import HistoryRecordV2, record_from_payload
from profit_accounting_26.application.profit_scenario_codec import extract_profit_scenarios
from profit_accounting_26.ui.pages.calibration_feedback_dialog import CalibrationFeedbackDialog
from profit_accounting_26.ui.widgets import Card, ImagePreviewDialog, SectionHeader

_THUMB_COLUMN_WIDTH = 64
_ROW_HEIGHT = 56
_PLACEHOLDER_COLOR = QColor("#E7ECF3")

_STRUCTURE_CN = (
    ("can_fold", "可以折叠"),
    ("can_compress", "可以压缩"),
    ("can_coil", "可以缠绕"),
    ("can_disassemble", "可以拆开"),
    ("requires_shape_retention", "需要保形"),
)


def _placeholder_icon(size: int = 48) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(_PLACEHOLDER_COLOR)
    return QIcon(pixmap)


def _icon_from_path(path: Path | None, size: int = 48) -> QIcon:
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


def _fmt_money(value: Any) -> str:
    try:
        return f"¥{float(value):.2f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_dimensions(values: dict[str, Any]) -> str:
    parts = [values.get(key) for key in ("length_cm", "width_cm", "height_cm")]
    if not any(value is not None for value in parts):
        return "—"
    text = "×".join(str(float(value)) if value is not None else "?" for value in parts)
    return f"{text} cm"


def _fmt_weight(value: Any) -> str:
    if value is None:
        return "—"
    return f"{float(value)} g"


def _rate_text(value: Any, *, legacy_percent: bool) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if legacy_percent:
        return f"{number:.2f}%"
    return f"{number * 100:.2f}%"


class HistoryPage(QWidget):
    recordRequested = Signal(str)

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._detail_values: dict[str, QLabel] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 18)
        layout.setSpacing(12)

        card = Card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(10)
        header = SectionHeader("历史记录管理", "查看历史记录、首次 AI 判断与校准反馈")
        self.search = QLineEdit()
        self.search.setPlaceholderText("按商品名称、记录ID或状态搜索")
        self.search.setFixedWidth(260)
        self.search.returnPressed.connect(self.refresh)
        refresh = QPushButton("刷新")
        feedback_button = QPushButton("录入反馈")
        open_button = QPushButton("返回测算页编辑")
        open_button.setProperty("primary", True)
        for button in (refresh, feedback_button, open_button):
            button.setFixedHeight(32)
        refresh.clicked.connect(self.refresh)
        feedback_button.clicked.connect(self._open_feedback_dialog)
        open_button.clicked.connect(self.open_selected)
        header.right_layout.addWidget(self.search)
        header.right_layout.addWidget(refresh)
        header.right_layout.addWidget(feedback_button)
        header.right_layout.addWidget(open_button)
        card_layout.addWidget(header)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["缩略图", "商品名称", "更新时间", "当前包装", "利润", "反馈状态"]
        )
        self.table.setColumnWidth(0, _THUMB_COLUMN_WIDTH)
        self.table.setColumnWidth(1, 230)
        self.table.setColumnWidth(2, 170)
        self.table.setColumnWidth(3, 150)
        self.table.setColumnWidth(4, 110)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(_ROW_HEIGHT)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self.show_details)
        self.table.cellDoubleClicked.connect(lambda _row, _col: self.open_selected())
        card_layout.addWidget(self.table)
        layout.addWidget(card, 3)

        details_card = Card()
        details_layout = QVBoxLayout(details_card)
        details_layout.setContentsMargins(14, 12, 14, 12)
        details_layout.setSpacing(8)
        details_layout.addWidget(SectionHeader("记录详情", "结构化只读详情"))
        self.details_scroll = QScrollArea()
        self.details_scroll.setWidgetResizable(True)
        self.details_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.details_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.details_body = QWidget()
        self.details_body_layout = QVBoxLayout(self.details_body)
        self.details_body_layout.setContentsMargins(0, 0, 0, 0)
        self.details_body_layout.setSpacing(8)
        self.details_scroll.setWidget(self.details_body)
        details_layout.addWidget(self.details_scroll)
        layout.addWidget(details_card, 2)
        self.refresh()

    # ---------------------------------------------------------------- list

    def refresh(self) -> None:
        self.records = self.context.record_service.list(search=self.search.text())
        self.table.setRowCount(0)
        for payload in self.records:
            v2 = record_from_payload(payload)
            row = self.table.rowCount()
            self.table.insertRow(row)
            thumb = QTableWidgetItem()
            thumb.setIcon(self._record_icon(v2))
            thumb.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb.setData(256, v2.record_id)
            self.table.setItem(row, 0, thumb)
            self.table.setItem(row, 1, QTableWidgetItem(v2.product_name or "未命名商品"))
            self.table.setItem(row, 2, QTableWidgetItem(v2.updated_at or ""))
            self.table.setItem(row, 3, QTableWidgetItem(self._packaging_text(v2)))
            self.table.setItem(row, 4, QTableWidgetItem(self._profit_text(payload)))
            self.table.setItem(row, 5, QTableWidgetItem(self._feedback_status(v2)))
        if self.records:
            self.table.selectRow(0)

    def selected_record_id(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return str(item.data(256)) if item and item.data(256) else None

    def open_selected(self) -> None:
        record_id = self.selected_record_id()
        if not record_id:
            QMessageBox.information(self, "未选择", "请先选择一条记录。")
            return
        self.recordRequested.emit(record_id)

    def _open_feedback_dialog(self) -> None:
        record_id = self.selected_record_id()
        if not record_id:
            QMessageBox.information(self, "未选择", "请先选择一条记录。")
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
            self.show_details()

    # ---------------------------------------------------------------- details

    def show_details(self) -> None:
        record_id = self.selected_record_id()
        self._clear_details()
        if not record_id:
            return
        payload = self.context.record_service.load(record_id)
        v2 = record_from_payload(payload)
        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(10)
        left = self._build_column()
        right = self._build_column()
        self._add_product_section(left, v2)
        self._add_images_section(left, v2)
        self._add_current_estimate_section(left, v2)
        self._add_ai_section(right, v2)
        self._add_profit_section(right, payload)
        self._add_feedback_section(right, v2)
        columns.addWidget(left, 1)
        columns.addWidget(right, 1)
        self.details_body_layout.addLayout(columns)
        self.details_body_layout.addStretch(1)

    def _clear_details(self) -> None:
        self._detail_values.clear()
        while self.details_body_layout.count():
            item = self.details_body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            layout = item.layout()
            if layout is not None:
                while layout.count():
                    child = layout.takeAt(0)
                    child_widget = child.widget()
                    if child_widget is not None:
                        child_widget.deleteLater()

    def _build_column(self) -> QWidget:
        column = QWidget()
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(6)
        column.setProperty("columnLayout", column_layout)
        return column

    def _add_section(self, column: QWidget, title: str, subtitle: str = "") -> QFormLayout:
        layout: QVBoxLayout = column.property("columnLayout")
        layout.addWidget(SectionHeader(title, subtitle))
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(2)
        layout.addLayout(form)
        return form

    def _add_row(self, form: QFormLayout, key: str, label: str, value: str) -> None:
        label_widget = QLabel(label)
        label_widget.setProperty("muted", True)
        value_widget = QLabel(value)
        value_widget.setWordWrap(True)
        value_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        form.addRow(label_widget, value_widget)
        self._detail_values[key] = value_widget

    def _add_product_section(self, column: QWidget, v2: HistoryRecordV2) -> None:
        form = self._add_section(column, "商品")
        self._add_row(form, "product_name", "商品名称", v2.product_name or "—")
        self._add_row(form, "product_link", "商品链接", v2.product_link or "—")
        self._add_row(form, "created_at", "创建时间", v2.created_at or "—")
        self._add_row(form, "updated_at", "更新时间", v2.updated_at or "—")
        self._add_row(form, "revision", "revision", str(v2.revision))

    def _add_images_section(self, column: QWidget, v2: HistoryRecordV2) -> None:
        layout: QVBoxLayout = column.property("columnLayout")
        layout.addWidget(SectionHeader("图片", "点击缩略图查看原图"))
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        images = [item for item in (v2.images or []) if isinstance(item, dict)]
        images.sort(key=lambda item: item.get("order", 0))
        if not images:
            row_layout.addWidget(QLabel("无图片"))
        for item in images:
            original = self._image_path(item, prefer_thumbnail=False)
            thumbnail = self._image_path(item, prefer_thumbnail=True)
            button = QPushButton()
            button.setFixedSize(64, 64)
            button.setIconSize(QSize(56, 56))
            if original is None and thumbnail is None:
                button.setIcon(_placeholder_icon(56))
                button.setEnabled(False)
            else:
                button.setIcon(_icon_from_path(thumbnail or original, 56))
                target = original or thumbnail
                button.clicked.connect(lambda _checked=False, path=target: ImagePreviewDialog(path, self).exec())
            row_layout.addWidget(button)
        row_layout.addStretch(1)
        layout.addLayout(row_layout)

    def _add_ai_section(self, column: QWidget, v2: HistoryRecordV2) -> None:
        form = self._add_section(column, "第一次 AI 判断")
        ai = v2.ai_initial
        if ai is None or "legacy_layers_ai_raw" in ai:
            self._add_row(form, "ai_note", "说明", "旧记录：首次 AI 结果不可完整追溯")
            fallback = self._legacy_ai_fallback(ai)
            if fallback:
                self._add_row(form, "ai_fallback", "可获得的旧信息", fallback)
            return
        observation = ai.get("observation") if isinstance(ai.get("observation"), dict) else {}
        self._add_row(form, "ai_model", "模型", str(ai.get("model") or ai.get("provider") or "—"))
        self._add_row(form, "ai_summary", "商品/结构摘要", self._observation_summary(observation))
        self._add_row(form, "ai_bare_spec", "裸品尺寸重量", self._bare_spec_text(observation))
        self._add_row(form, "ai_packaging", "包装判断", self._ai_packaging_text(ai))

    def _add_current_estimate_section(self, column: QWidget, v2: HistoryRecordV2) -> None:
        form = self._add_section(column, "当前采用估算")
        estimate = v2.current_estimate or {}
        self._add_row(
            form, "est_method", "包装方式",
            str(estimate.get("packaging_method") or "—"),
        )
        self._add_row(form, "est_dims", "长宽高", _fmt_dimensions(estimate))
        self._add_row(form, "est_weight", "重量", _fmt_weight(estimate.get("weight_g")))
        self._add_row(
            form, "est_tier", "当前采用档",
            str(estimate.get("selected_packaging") or "—"),
        )

    def _add_profit_section(self, column: QWidget, payload: dict[str, Any]) -> None:
        form = self._add_section(column, "利润快照", "只读保存值，不重新计算")
        scenarios = extract_profit_scenarios(payload) or {}
        legacy = bool(
            scenarios.get("_legacy_compatible") or scenarios.get("legacy_compatible")
        )
        no_activity = scenarios.get("no_activity") or {}
        activity = scenarios.get("activity") or {}
        calculated = {}
        layers = payload.get("layers")
        if isinstance(layers, dict):
            calculated = layers.get("calculated") or {}
        self._add_row(form, "profit_no_activity", "无活动利润", _fmt_money(no_activity.get("profit_rmb")))
        no_rate = no_activity.get("profit_rate_on_cost")
        if no_rate is None:
            no_rate = calculated.get("profit_rate_percent")
            self._add_row(form, "profit_no_activity_rate", "无活动利润率", _rate_text(no_rate, legacy_percent=True))
        else:
            self._add_row(form, "profit_no_activity_rate", "无活动利润率", _rate_text(no_rate, legacy_percent=legacy))
        self._add_row(form, "profit_activity", "活动场景利润", _fmt_money(activity.get("profit_rmb")))
        self._add_row(
            form, "profit_activity_rate", "活动场景利润率",
            _rate_text(activity.get("profit_rate_on_cost"), legacy_percent=legacy),
        )
        hint = self._subsidy_hint(activity)
        if hint:
            self._add_row(form, "profit_hint", "活动/补贴", hint)

    def _add_feedback_section(self, column: QWidget, v2: HistoryRecordV2) -> None:
        form = self._add_section(column, "用户反馈")
        status = self._feedback_status(v2)
        self._add_row(form, "feedback_status", "状态", status)
        if not v2.calibration_feedback_id:
            self._add_row(form, "feedback_summary", "内容摘要", "—")
            return
        try:
            feedback = self.context.calibration_feedback_service.load(v2.calibration_feedback_id)
        except KeyError:
            self._add_row(form, "feedback_summary", "内容摘要", "已关联反馈，但数据缺失")
            return
        summary = self._feedback_summary(feedback)
        self._add_row(form, "feedback_summary", "内容摘要", summary)
        self._add_row(form, "feedback_note", "备注", feedback.user_note or "—")

    # ---------------------------------------------------------------- helpers

    def _image_path(self, item: dict[str, Any], *, prefer_thumbnail: bool) -> Path | None:
        key = item.get("thumbnail_key") if prefer_thumbnail else None
        if not key:
            key = item.get("storage_key") or item.get("relative_path")
        if not key:
            return None
        path = self.context.paths.data_dir / key
        return path if path.is_file() else None

    def _record_icon(self, v2: HistoryRecordV2) -> QIcon:
        for item in (v2.images or []):
            if not isinstance(item, dict):
                continue
            path = self._image_path(item, prefer_thumbnail=True) or self._image_path(item, prefer_thumbnail=False)
            if path is not None:
                return _icon_from_path(path, 44)
        return _placeholder_icon(44)

    def _packaging_text(self, v2: HistoryRecordV2) -> str:
        estimate = v2.current_estimate or {}
        method = str(estimate.get("packaging_method") or "")
        dims = _fmt_dimensions(estimate)
        if method and dims != "—":
            return f"{method} {dims}"
        return method or dims

    def _profit_text(self, payload: dict[str, Any]) -> str:
        scenarios = extract_profit_scenarios(payload) or {}
        no_activity = scenarios.get("no_activity") or {}
        return _fmt_money(no_activity.get("profit_rmb"))

    def _feedback_status(self, v2: HistoryRecordV2) -> str:
        if not v2.calibration_feedback_id:
            return "未反馈"
        try:
            feedback = self.context.calibration_feedback_service.load(v2.calibration_feedback_id)
        except KeyError:
            return "已反馈"
        if feedback.calibration_exported_at and feedback.feedback_updated_after_export:
            return "已更新 · 待导出"
        if feedback.calibration_exported_at:
            return "已导出"
        return "已反馈"

    def _observation_summary(self, observation: dict[str, Any]) -> str:
        summary = str(observation.get("display_product_summary") or "").strip()
        if summary:
            return summary
        parts = [
            str(observation.get("product_name") or "").strip(),
            str(observation.get("product_type") or "").strip(),
            str(observation.get("material") or "").strip(),
        ]
        return "、".join(part for part in parts if part) or "—"

    def _bare_spec_text(self, observation: dict[str, Any]) -> str:
        dims = _fmt_dimensions(observation)
        weight = _fmt_weight(observation.get("weight_g"))
        if dims == "—" and weight == "—":
            return "—"
        return f"{dims}，{weight}"

    def _ai_packaging_text(self, ai: dict[str, Any]) -> str:
        proposal = ai.get("external_ai_packaging_proposal")
        if isinstance(proposal, dict):
            scenario = proposal.get("normal")
            if isinstance(scenario, dict):
                return self._scenario_text(scenario)
        adopted = ai.get("adopted_packaging")
        if isinstance(adopted, dict):
            return self._scenario_text(adopted)
        return "—"

    def _scenario_text(self, scenario: dict[str, Any]) -> str:
        method = str(scenario.get("packaging_method") or "").strip()
        dims = _fmt_dimensions(scenario)
        weight = _fmt_weight(scenario.get("weight_g"))
        reasoning = str(scenario.get("reasoning_summary") or "").strip()
        parts = [part for part in (method, dims, weight) if part != "—"]
        text = "；".join(parts) if parts else "—"
        if reasoning:
            text = f"{text}（{reasoning[:120]}）"
        return text

    def _legacy_ai_fallback(self, ai: dict[str, Any] | None) -> str:
        if not ai or not isinstance(ai.get("legacy_layers_ai_raw"), dict):
            return ""
        observation = ai["legacy_layers_ai_raw"].get("observation")
        if not isinstance(observation, dict):
            return ""
        return self._observation_summary(observation)

    def _subsidy_hint(self, activity: dict[str, Any]) -> str:
        rules = activity.get("rule_status") or {}
        rule_list = rules.get("rules") if isinstance(rules, dict) else None
        names = [
            str(rule.get("name") or "").strip()
            for rule in (rule_list or [])
            if isinstance(rule, dict)
        ]
        subsidy_names = [name for name in names if "补贴" in name]
        if subsidy_names:
            return "活动/补贴：" + "、".join(subsidy_names[:3])
        if activity.get("profit_rmb"):
            return "记录包含活动场景利润快照"
        return ""

    def _feedback_summary(self, feedback: Any) -> str:
        parts: list[str] = []
        structure = feedback.structure
        for key, label in _STRUCTURE_CN:
            value = getattr(structure, key)
            if value is True:
                parts.append(f"{label}=是")
            elif value is False:
                parts.append(f"{label}=否")
        suggested = feedback.suggested_package
        if suggested is not None and suggested.has_content():
            method = str(suggested.packaging_method or "").strip()
            dims = _fmt_dimensions(
                {
                    "length_cm": suggested.length_cm,
                    "width_cm": suggested.width_cm,
                    "height_cm": suggested.height_cm,
                }
            )
            weight = _fmt_weight(suggested.weight_g)
            suggested_text = "建议包装：" + "、".join(
                part for part in (method, dims, weight) if part != "—"
            )
            if suggested_text != "建议包装：":
                parts.append(suggested_text)
        actual = feedback.actual_logistics
        if actual is not None and actual.has_content():
            fee = _fmt_money(actual.actual_first_mile_fee_rmb)
            chargeable = (
                f"{float(actual.actual_chargeable_weight_kg)} kg"
                if actual.actual_chargeable_weight_kg is not None
                else ""
            )
            actual_parts = [
                f"实际头程 {fee}" if fee != "—" else "",
                chargeable,
                f"货代 {actual.actual_forwarder}" if actual.actual_forwarder else "",
            ]
            actual_text = "实际物流：" + "、".join(part for part in actual_parts if part)
            if actual_text != "实际物流：":
                parts.append(actual_text)
        return "；".join(parts) or "—"
