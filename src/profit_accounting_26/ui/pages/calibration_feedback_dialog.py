"""极简实际校准对话框（普通用户版）。

只保留三个输入：实际包装尺寸（长×宽×高 cm）、实际包装重量（g）、修正说明。
- 数字框默认真空，空 = 未知；不显示默认 0.00；没有上下微调箭头；
  用户明确输入 0 时仍按数据合同保存 0。
- 实际尺寸/重量写入 actual_logistics，evidence_level 使用实际测量语义；
  绝不把费用反推成尺寸。
- 已有 linked feedback 时更新同一个 feedback_id，并保留其中的
  suggested_package / structure / user_note，不重复创建反馈。
后台数据合同（CalibrationFeedback V1）不变，只是不再让普通用户填复杂字段。
"""

from __future__ import annotations

from typing import Any

from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from profit_accounting_26.application import AppContext
from profit_accounting_26.application.calibration_feedback_service import CalibrationFeedbackService
from profit_accounting_26.application.data_contracts import CalibrationFeedback
from profit_accounting_26.ui.widgets import Card, SectionHeader


def _make_number_edit(suffix_hint: str, maximum: float) -> QLineEdit:
    """无边框感数字输入：默认真空，空 = 未知；0 是合法输入。"""
    edit = QLineEdit()
    edit.setPlaceholderText(f"单位 {suffix_hint}，空 = 未知")
    edit.setFixedWidth(160)
    edit.setFixedHeight(30)
    validator = QDoubleValidator(0.0, maximum, 2, edit)
    validator.setNotation(QDoubleValidator.Notation.StandardNotation)
    edit.setValidator(validator)
    return edit


def _parse_optional(edit: QLineEdit) -> float | None:
    text = edit.text().strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


class CalibrationFeedbackDialog(QDialog):
    """发货后极简实际校准：实际尺寸、实际重量、修正说明。"""

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
        self.setWindowTitle("实际校准")
        self.setFixedWidth(460)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(SectionHeader("实际包装", "发货后实测；空 = 未知，0 是合法值"))
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(8)

        dims_row = QHBoxLayout()
        dims_row.setContentsMargins(0, 0, 0, 0)
        dims_row.setSpacing(6)
        self.length_edit = _make_number_edit("cm", 500)
        self.width_edit = _make_number_edit("cm", 500)
        self.height_edit = _make_number_edit("cm", 500)
        for index, edit in enumerate((self.length_edit, self.width_edit, self.height_edit)):
            dims_row.addWidget(edit)
            if index < 2:
                dims_row.addWidget(QLabel("×"))
        dims_label = QLabel("实际包装尺寸")
        dims_label.setProperty("muted", True)
        form.addRow(dims_label, dims_row)

        self.weight_edit = _make_number_edit("g", 100_000)
        weight_label = QLabel("实际包装重量")
        weight_label.setProperty("muted", True)
        form.addRow(weight_label, self.weight_edit)
        layout.addLayout(form)
        outer.addWidget(card)

        note_card = Card()
        note_layout = QVBoxLayout(note_card)
        note_layout.setContentsMargins(12, 10, 12, 12)
        note_layout.setSpacing(8)
        note_layout.addWidget(SectionHeader("修正说明", "自然语言，可留空"))
        self.user_note = QTextEdit()
        self.user_note.setPlaceholderText("例如：这个包可以压扁，肩带可以拆下来单独放")
        self.user_note.setFixedHeight(84)
        self.user_note.setAcceptRichText(False)
        note_layout.addWidget(self.user_note)
        outer.addWidget(note_card)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setFixedWidth(96)
        cancel.setFixedHeight(34)
        self.save_button = QPushButton("保存校准")
        self.save_button.setProperty("primary", True)
        self.save_button.setFixedWidth(120)
        self.save_button.setFixedHeight(34)
        actions.addWidget(cancel)
        actions.addWidget(self.save_button)
        cancel.clicked.connect(self.reject)
        self.save_button.clicked.connect(self._on_save)
        outer.addLayout(actions)

        self._load_existing(feedback)

    # ---------------------------------------------------------------- helpers

    def _load_existing(self, feedback: CalibrationFeedback | None) -> None:
        if feedback is None:
            return
        actual = feedback.actual_logistics
        if actual is not None:
            dimensions = actual.actual_package_dimensions or {}
            for edit, key in (
                (self.length_edit, "length_cm"),
                (self.width_edit, "width_cm"),
                (self.height_edit, "height_cm"),
            ):
                value = dimensions.get(key)
                if value is not None:
                    edit.setText(f"{float(value):g}")
            if actual.actual_package_weight_g is not None:
                self.weight_edit.setText(f"{float(actual.actual_package_weight_g):g}")
        self.user_note.setPlainText(feedback.user_note or "")

    # ---------------------------------------------------------------- payload

    def build_payload(self) -> dict[str, Any]:
        dimensions: dict[str, Any] = {}
        for edit, key in (
            (self.length_edit, "length_cm"),
            (self.width_edit, "width_cm"),
            (self.height_edit, "height_cm"),
        ):
            value = _parse_optional(edit)
            if value is not None:
                dimensions[key] = value
        weight = _parse_optional(self.weight_edit)
        payload: dict[str, Any] = {
            "record_id": self.record_id,
            "source": "user",
            "user_note": self.user_note.toPlainText().strip() or None,
        }
        if dimensions or weight is not None:
            # 实际尺寸/重量是真实测量：使用实际测量语义，不与费用互相推导
            payload["actual_logistics"] = {
                "actual_package_dimensions": dimensions or None,
                "actual_package_weight_g": weight,
                "evidence_level": "actual_measured",
            }
        # 保留主界面已保存的用户建议与结构反馈，实际校准只补充实测数据
        if self.existing is not None:
            payload["feedback_id"] = self.existing.feedback_id
            suggested = self.existing.suggested_package
            if suggested is not None and suggested.has_content():
                payload["suggested_package"] = suggested.to_dict()
            if self.existing.structure.has_content():
                payload["structure"] = self.existing.structure.to_dict()
        return payload

    def _has_input(self) -> bool:
        payload = self.build_payload()
        return bool(payload.get("actual_logistics") or payload.get("user_note"))

    # ---------------------------------------------------------------- save

    def save(self) -> str:
        """保存实际校准：已有反馈更新同一条 feedback_id，绝不新增重复。"""
        service: CalibrationFeedbackService = self.context.calibration_feedback_service
        feedback_id = service.save(self.build_payload(), record_id=self.record_id)
        self.context.history_record_v2_service.link_feedback(self.record_id, feedback_id)
        return feedback_id

    def _on_save(self) -> None:
        if not self._has_input():
            QMessageBox.warning(self, "无法保存", "请至少填写实际尺寸、实际重量或修正说明中的一项。")
            return
        try:
            self.save()
        except ValueError as exc:
            QMessageBox.warning(self, "无法保存", str(exc))
            return
        self.accept()
