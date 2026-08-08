from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from profit_accounting_26.application import AppContext
from profit_accounting_26.application.calibration_feedback_service import CalibrationFeedbackService
from profit_accounting_26.application.data_contracts import CalibrationFeedback
from profit_accounting_26.application.settings_service import SettingsService
from profit_accounting_26.ui.widgets import Card, SectionHeader

_TRI_STATE_LABELS = (
    "是否可以折叠",
    "是否可以压缩",
    "是否可以缠绕",
    "是否可以拆开",
    "是否需要保形",
)
_TRI_STATE_KEYS = (
    "can_fold",
    "can_compress",
    "can_coil",
    "can_disassemble",
    "requires_shape_retention",
)
_TRI_STATE_ITEMS = ("未确认", "是", "否")
_TRI_STATE_VALUES = ("unknown", True, False)

_SUGGESTED_LABELS = {
    "length_cm": ("建议长", " cm", 500),
    "width_cm": ("建议宽", " cm", 500),
    "height_cm": ("建议高", " cm", 500),
    "weight_g": ("建议重量", " g", 100_000),
}

_ACTUAL_LABELS = {
    "length_cm": ("实际包装长", " cm", 500),
    "width_cm": ("实际包装宽", " cm", 500),
    "height_cm": ("实际包装高", " cm", 500),
    "weight_g": ("实际包装重量", " g", 100_000),
    "actual_chargeable_weight_kg": ("实际计费重", " kg", 500),
    "actual_first_mile_fee_rmb": ("实际头程费用", " RMB", 1_000_000),
}


class CalibrationFeedbackDialog(QDialog):
    """普通用户校准反馈表单（V1）。

    只记录真实经验：不自动修改包装结果、不重新计算利润、不触发 AI。
    结构反馈保留三态（未确认/是/否），建议包装恒为 user_suggested，
    实际物流的 0 是合法值，不会被转换成 None。
    """

    def __init__(
        self,
        context: AppContext,
        record_id: str,
        feedback: CalibrationFeedback | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.record_id = record_id
        self.existing = feedback
        self.setWindowTitle("录入校准反馈")
        self.resize(720, 880)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(12)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self._build_structure_section()
        self._build_suggested_section()
        self._build_actual_section()
        self._build_note_section()
        self._build_actions()
        self._load_existing(feedback)

    # ---------------------------------------------------------------- sections

    def _build_structure_section(self) -> None:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(SectionHeader("商品结构反馈", "未确认不会当作“否”"))
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(8)
        self.tri_state_combos: dict[str, QComboBox] = {}
        for key, label in zip(_TRI_STATE_KEYS, _TRI_STATE_LABELS):
            combo = QComboBox()
            combo.addItems(_TRI_STATE_ITEMS)
            combo.setFixedWidth(140)
            label_widget = QLabel(label)
            label_widget.setProperty("muted", True)
            form.addRow(label_widget, combo)
            self.tri_state_combos[key] = combo
        layout.addLayout(form)
        self.body_layout.addWidget(card)

    def _build_suggested_section(self) -> None:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(SectionHeader("用户建议包装（可选）", "仅记录建议，不会被当成实测"))
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(8)
        method_label = QLabel("包装方式")
        method_label.setProperty("muted", True)
        self.suggested_method = QLineEdit()
        self.suggested_method.setPlaceholderText("例如：气泡袋 / 纸箱 / 折叠后放平")
        self.suggested_method.setMaximumWidth(320)
        form.addRow(method_label, self.suggested_method)
        self.suggested_spins: dict[str, QDoubleSpinBox] = {}
        for key, (label, suffix, maximum) in _SUGGESTED_LABELS.items():
            spin = self._make_optional_spin(suffix, maximum, special_text="空")
            label_widget = QLabel(label)
            label_widget.setProperty("muted", True)
            form.addRow(label_widget, spin)
            self.suggested_spins[key] = spin
        layout.addLayout(form)
        self.body_layout.addWidget(card)

    def _build_actual_section(self) -> None:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(SectionHeader("实际包装 / 物流（可选）", "0 是合法值，不会被当作未填写"))
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(8)
        method_label = QLabel("实际包装方式")
        method_label.setProperty("muted", True)
        self.actual_method = QLineEdit()
        self.actual_method.setPlaceholderText("例如：收到的实际包装")
        self.actual_method.setMaximumWidth(320)
        form.addRow(method_label, self.actual_method)
        self.actual_spins: dict[str, QDoubleSpinBox] = {}
        for key, (label, suffix, maximum) in _ACTUAL_LABELS.items():
            spin = self._make_optional_spin(suffix, maximum)
            spin.valueChanged.connect(lambda _value, key=key: self._mark_actual_touched(key))
            label_widget = QLabel(label)
            label_widget.setProperty("muted", True)
            form.addRow(label_widget, spin)
            self.actual_spins[key] = spin
        forwarder_label = QLabel("实际货代")
        forwarder_label.setProperty("muted", True)
        self.actual_forwarder = QComboBox()
        self.actual_forwarder.addItem("（未选择）", None)
        for forwarder in self._enabled_forwarders():
            self.actual_forwarder.addItem(forwarder.name, forwarder.id)
        self.actual_forwarder.setMaximumWidth(320)
        form.addRow(forwarder_label, self.actual_forwarder)
        layout.addLayout(form)
        self.body_layout.addWidget(card)

    def _build_note_section(self) -> None:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(SectionHeader("备注", "只写一句话也可以保存"))
        self.user_note = QTextEdit()
        self.user_note.setPlaceholderText("例如：这个商品厚度可以明显压缩 / 肩带可以拆下来单独放")
        self.user_note.setFixedHeight(84)
        layout.addWidget(self.user_note)
        self.body_layout.addWidget(card)

    def _build_actions(self) -> None:
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setFixedWidth(96)
        cancel.setFixedHeight(34)
        self.save_button = QPushButton("保存反馈")
        self.save_button.setProperty("primary", True)
        self.save_button.setFixedWidth(120)
        self.save_button.setFixedHeight(34)
        actions.addWidget(cancel)
        actions.addWidget(self.save_button)
        cancel.clicked.connect(self.reject)
        self.save_button.clicked.connect(self._on_save)
        self.body_layout.addLayout(actions)

    # ---------------------------------------------------------------- helpers

    def _enabled_forwarders(self) -> list[Any]:
        settings = self.context.settings_service.load()
        forwarders = SettingsService.forwarders_from_settings(settings)
        return [item for item in forwarders if item.enabled and not item.archived]

    @staticmethod
    def _make_optional_spin(suffix: str, maximum: float, *, special_text: str = "") -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, maximum)
        spin.setDecimals(2)
        spin.setSuffix(suffix)
        spin.setFixedWidth(150)
        if special_text:
            spin.setSpecialValueText(special_text)
        return spin

    def _load_existing(self, feedback: CalibrationFeedback | None) -> None:
        if feedback is None:
            return
        for key, combo in self.tri_state_combos.items():
            value = getattr(feedback.structure, key)
            combo.setCurrentIndex(_TRI_STATE_VALUES.index(value))
        suggested = feedback.suggested_package
        if suggested is not None:
            self.suggested_method.setText(suggested.packaging_method or "")
            for key, spin in self.suggested_spins.items():
                value = getattr(suggested, key)
                spin.setValue(float(value) if value is not None else 0.0)
        actual = feedback.actual_logistics
        if actual is not None:
            self.actual_method.setText(actual.actual_packaging_method or "")
            dimensions = actual.actual_package_dimensions or {}
            for key, spin in self.actual_spins.items():
                if key in ("length_cm", "width_cm", "height_cm"):
                    value = dimensions.get(key)
                elif key == "weight_g":
                    value = actual.actual_package_weight_g
                else:
                    value = getattr(actual, key)
                if value is not None:
                    spin.setValue(float(value))
                    self._mark_actual_touched(key)
            if actual.actual_forwarder:
                index = self.actual_forwarder.findData(actual.actual_forwarder)
                if index >= 0:
                    self.actual_forwarder.setCurrentIndex(index)
        self.user_note.setPlainText(feedback.user_note or "")

    def _mark_actual_touched(self, key: str) -> None:
        if not hasattr(self, "_actual_touched"):
            self._actual_touched: set[str] = set()
        self._actual_touched.add(key)

    def _current_actual_value(self, key: str) -> float | None:
        touched = getattr(self, "_actual_touched", set())
        if key not in touched:
            return None
        return float(self.actual_spins[key].value())

    # ---------------------------------------------------------------- payload

    def build_payload(self) -> dict[str, Any]:
        structure = {
            key: _TRI_STATE_VALUES[self.tri_state_combos[key].currentIndex()]
            for key in _TRI_STATE_KEYS
        }
        suggested: dict[str, Any] = {
            "packaging_method": self.suggested_method.text().strip() or None,
            "length_cm": self._optional_suggested("length_cm"),
            "width_cm": self._optional_suggested("width_cm"),
            "height_cm": self._optional_suggested("height_cm"),
            "weight_g": self._optional_suggested("weight_g"),
            "evidence_level": "user_suggested",
        }
        dimensions: dict[str, Any] = {}
        for key in ("length_cm", "width_cm", "height_cm"):
            value = self._current_actual_value(key)
            if value is not None:
                dimensions[key] = value
        actual: dict[str, Any] = {
            "actual_packaging_method": self.actual_method.text().strip() or None,
            "actual_package_dimensions": dimensions or None,
            "actual_package_weight_g": self._current_actual_value("weight_g"),
            "actual_chargeable_weight_kg": self._current_actual_value("actual_chargeable_weight_kg"),
            "actual_first_mile_fee_rmb": self._current_actual_value("actual_first_mile_fee_rmb"),
            "actual_forwarder": self.actual_forwarder.currentData() or None,
            "evidence_level": "actual_logistics",
        }
        payload: dict[str, Any] = {
            "record_id": self.record_id,
            "source": "user",
            "structure": structure,
            "suggested_package": suggested if self._suggested_has_content(suggested) else None,
            "actual_logistics": actual if self._actual_has_content(actual) else None,
            "user_note": self.user_note.toPlainText().strip() or None,
        }
        if self.existing is not None:
            payload["feedback_id"] = self.existing.feedback_id
        return payload

    @staticmethod
    def _optional_suggested_value(spin: QDoubleSpinBox) -> float | None:
        value = float(spin.value())
        return value if value > 0 else None

    def _optional_suggested(self, key: str) -> float | None:
        return self._optional_suggested_value(self.suggested_spins[key])

    @staticmethod
    def _suggested_has_content(suggested: dict[str, Any]) -> bool:
        return any(
            value is not None
            for value in (
                suggested.get("packaging_method"),
                suggested.get("length_cm"),
                suggested.get("width_cm"),
                suggested.get("height_cm"),
                suggested.get("weight_g"),
            )
        )

    @staticmethod
    def _actual_has_content(actual: dict[str, Any]) -> bool:
        return any(
            value is not None
            for value in (
                actual.get("actual_packaging_method"),
                actual.get("actual_package_dimensions"),
                actual.get("actual_package_weight_g"),
                actual.get("actual_chargeable_weight_kg"),
                actual.get("actual_first_mile_fee_rmb"),
                actual.get("actual_forwarder"),
            )
        )

    # ---------------------------------------------------------------- save

    def save(self) -> str:
        """保存反馈并挂接到 HistoryRecordV2；已有反馈更新同一条，绝不新增重复。"""
        service: CalibrationFeedbackService = self.context.calibration_feedback_service
        feedback_id = service.save(self.build_payload(), record_id=self.record_id)
        self.context.history_record_v2_service.link_feedback(self.record_id, feedback_id)
        return feedback_id

    def _on_save(self) -> None:
        try:
            self.save()
        except ValueError as exc:
            QMessageBox.warning(self, "无法保存", str(exc))
            return
        self.accept()
