"""编辑校准对话框（普通用户版，用户校准入口 B）。

与主页面“当前采用”（用户校准入口 A）更新同一条记录：
- 预填该记录 current_estimate 的长×宽×高/重量与已保存的用户修正；
- 保存时同步更新 current_estimate、suggested_package（恒为 user_suggested）
  与 user_note；同 record_id、同 feedback_id（无则创建后 link），绝不重复创建。
- 输入的是用户校准值，不是实际发货实测：绝不写 actual_logistics，
  也不标记 actual_measured；已有 feedback 中的 actual_logistics / structure
  原样保留。
- 顶部一行弱化显示第一次 AI 估算结果作为对照（只读参考）。
- 数字框默认真空，空 = 未知；0 是合法输入；单位显示在输入框右侧，
  不塞进输入框占位文字；无上下微调箭头；紧凑无滚动条。
后台数据合同（CalibrationFeedback V1 / HistoryRecord V2）不变。
"""

from __future__ import annotations

from typing import Any

from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog,
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

_DIM_KEYS = ("length_cm", "width_cm", "height_cm")


def _make_number_edit(maximum: float) -> QLineEdit:
    """数字输入：默认真空，空 = 未知；0 是合法输入。"""
    edit = QLineEdit()
    edit.setPlaceholderText("空 = 未知")
    edit.setFixedWidth(88)
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


def _set_optional(edit: QLineEdit, value: Any) -> None:
    if value is None:
        return
    try:
        edit.setText(f"{float(value):g}")
    except (TypeError, ValueError):
        return


def _dims_text(raw: dict[str, Any]) -> str:
    """参考行格式：27×17×4 cm / 30g；完全缺失返回空。"""
    parts = []
    for key in _DIM_KEYS:
        value = raw.get(key)
        parts.append(f"{float(value):g}" if value is not None else "—")
    weight = raw.get("weight_g")
    weight_text = f"{float(weight):g}g" if weight is not None else ""
    dims = "×".join(parts) + " cm"
    return f"{dims} / {weight_text}" if weight_text else dims


class CalibrationFeedbackDialog(QDialog):
    """编辑校准：长×宽×高、包装后重量、用户修正；同步当前采用与反馈。"""

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
        self.setWindowTitle("编辑校准")
        self.setFixedWidth(460)
        v2 = self.context.history_record_v2_service.load_v2(record_id)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(SectionHeader("当前采用包装", "空 = 未知，0 是合法值"))

        # 第一次 AI 估算参考（只读对照，弱化一行）
        ai_reference = ""
        ai_initial = v2.ai_initial if isinstance(v2.ai_initial, dict) else {}
        if isinstance(ai_initial, dict) and "legacy_layers_ai_raw" not in ai_initial:
            adopted_packaging = ai_initial.get("adopted_packaging")
            if isinstance(adopted_packaging, dict):
                normal = adopted_packaging.get("normal")
                if isinstance(normal, dict):
                    ai_reference = _dims_text(normal)
        reference_label = QLabel(f"AI首次：{ai_reference}" if ai_reference else "AI首次：—")
        reference_label.setProperty("muted", True)
        layout.addWidget(reference_label)

        # 尺寸行：标签独立一行，输入框与单位分离，无微调箭头
        dims_label = QLabel("包装尺寸（长 × 宽 × 高）")
        dims_label.setProperty("muted", True)
        layout.addWidget(dims_label)
        dims_row = QHBoxLayout()
        dims_row.setContentsMargins(0, 0, 0, 0)
        dims_row.setSpacing(6)
        self.length_edit = _make_number_edit(500)
        self.width_edit = _make_number_edit(500)
        self.height_edit = _make_number_edit(500)
        for index, edit in enumerate((self.length_edit, self.width_edit, self.height_edit)):
            dims_row.addWidget(edit)
            if index < 2:
                separator = QLabel("×")
                separator.setProperty("muted", True)
                dims_row.addWidget(separator)
        cm_unit = QLabel("cm")
        cm_unit.setProperty("muted", True)
        dims_row.addWidget(cm_unit)
        dims_row.addStretch(1)
        layout.addLayout(dims_row)

        # 重量行：标签独立一行，单位在输入框右侧
        weight_label = QLabel("包装后重量")
        weight_label.setProperty("muted", True)
        layout.addWidget(weight_label)
        weight_row = QHBoxLayout()
        weight_row.setContentsMargins(0, 0, 0, 0)
        weight_row.setSpacing(6)
        self.weight_edit = _make_number_edit(100_000)
        weight_row.addWidget(self.weight_edit)
        gram_unit = QLabel("g")
        gram_unit.setProperty("muted", True)
        weight_row.addWidget(gram_unit)
        weight_row.addStretch(1)
        layout.addLayout(weight_row)
        outer.addWidget(card)

        note_card = Card()
        note_layout = QVBoxLayout(note_card)
        note_layout.setContentsMargins(12, 10, 12, 12)
        note_layout.setSpacing(8)
        note_layout.addWidget(SectionHeader("用户修正", "自然语言，可留空"))
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

        self._prefill(v2.current_estimate, feedback)

    # ---------------------------------------------------------------- helpers

    def _prefill(self, current_estimate: dict[str, Any], feedback: CalibrationFeedback | None) -> None:
        """预填 current_estimate 尺寸/重量与已保存的用户修正（入口 A/B 双向一致）。"""
        estimate = current_estimate if isinstance(current_estimate, dict) else {}
        # 旧记录没有 current_estimate 时回退已有反馈中的建议值，不伪造数据
        if not any(estimate.get(key) is not None for key in (*_DIM_KEYS, "weight_g")):
            suggested = feedback.suggested_package if feedback is not None else None
            if suggested is not None and suggested.has_content():
                estimate = suggested.to_dict()
        for edit, key in (
            (self.length_edit, "length_cm"),
            (self.width_edit, "width_cm"),
            (self.height_edit, "height_cm"),
        ):
            _set_optional(edit, estimate.get(key))
        _set_optional(self.weight_edit, estimate.get("weight_g"))
        if feedback is not None:
            self.user_note.setPlainText(feedback.user_note or "")

    # ---------------------------------------------------------------- payload

    def _estimate_dict(self) -> dict[str, Any]:
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
        return {**dimensions, "weight_g": weight}

    def build_payload(self) -> dict[str, Any]:
        estimate = self._estimate_dict()
        payload: dict[str, Any] = {
            "record_id": self.record_id,
            "source": "user",
            "user_note": self.user_note.toPlainText().strip() or None,
        }
        if any(value is not None for value in estimate.values()):
            # 用户校准值不是实测数据：恒标记 user_suggested，绝不写 actual_logistics
            suggested = {
                "packaging_method": None,
                "length_cm": estimate.get("length_cm"),
                "width_cm": estimate.get("width_cm"),
                "height_cm": estimate.get("height_cm"),
                "weight_g": estimate.get("weight_g"),
                "evidence_level": "user_suggested",
            }
            payload["suggested_package"] = suggested
        # 已有反馈：更新同一条 feedback_id，保留其中的实测数据与结构反馈
        if self.existing is not None:
            payload["feedback_id"] = self.existing.feedback_id
            if "suggested_package" not in payload and self.existing.suggested_package is not None and self.existing.suggested_package.has_content():
                payload["suggested_package"] = self.existing.suggested_package.to_dict()
            actual = self.existing.actual_logistics
            if actual is not None and actual.has_content():
                payload["actual_logistics"] = actual.to_dict()
            if self.existing.structure.has_content():
                payload["structure"] = self.existing.structure.to_dict()
        return payload

    def _has_input(self) -> bool:
        payload = self.build_payload()
        return bool(payload.get("suggested_package") or payload.get("user_note"))

    # ---------------------------------------------------------------- save

    def save(self) -> str:
        """保存校准：已有反馈更新同一条 feedback_id，绝不新增重复。"""
        service: CalibrationFeedbackService = self.context.calibration_feedback_service
        feedback_id = service.save(self.build_payload(), record_id=self.record_id)
        self.context.history_record_v2_service.link_feedback(self.record_id, feedback_id)
        # 入口 B 同步 current_estimate：与主页面“当前采用”更新同一条
        estimate = self._estimate_dict()
        if any(value is not None for value in estimate.values()):
            self.context.history_record_v2_service.update_current_estimate(
                self.record_id,
                {
                    "packaging_method": None,
                    "length_cm": estimate.get("length_cm"),
                    "width_cm": estimate.get("width_cm"),
                    "height_cm": estimate.get("height_cm"),
                    "weight_g": estimate.get("weight_g"),
                },
            )
        return feedback_id

    def _on_save(self) -> None:
        if not self._has_input():
            QMessageBox.warning(self, "无法保存", "请至少填写包装尺寸、重量或用户修正中的一项。")
            return
        try:
            self.save()
        except ValueError as exc:
            QMessageBox.warning(self, "无法保存", str(exc))
            return
        self.accept()
