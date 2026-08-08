"""校准反馈 Dialog：三态映射 / 建议包装 / 实际物流 0 语义 / 防重复 / revision 不变。"""

from __future__ import annotations

from pathlib import Path

import pytest

from profit_accounting_26.application import AppContext
from profit_accounting_26.ui.pages.calibration_feedback_dialog import CalibrationFeedbackDialog

pytest.importorskip("PySide6")


@pytest.fixture()
def context(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


def _create_record(context) -> str:
    payload = {
        "product_name": "反馈商品",
        "created_at": "2026-08-08T00:00:00Z",
        "layers": {
            "adopted": {
                "selected_packaging": "正常档",
                "normal": {
                    "packaging_method": "气泡袋",
                    "length_cm": 20,
                    "width_cm": 15,
                    "height_cm": 3,
                    "weight_g": 120,
                },
            },
            "calculated": {},
        },
    }
    return context.record_service.save(payload, images=[], ai_initial={})


def _dialog(context, record_id, feedback=None) -> CalibrationFeedbackDialog:
    return CalibrationFeedbackDialog(context, record_id, feedback=feedback)


def test_tri_state_mapping_unknown_true_false(qapp, context):
    record_id = _create_record(context)
    dialog = _dialog(context, record_id)
    payload = dialog.build_payload()
    assert payload["structure"] == {
        "can_fold": "unknown",
        "can_compress": "unknown",
        "can_coil": "unknown",
        "can_disassemble": "unknown",
        "requires_shape_retention": "unknown",
    }
    dialog.tri_state_combos["can_compress"].setCurrentIndex(1)
    dialog.tri_state_combos["can_fold"].setCurrentIndex(2)
    payload = dialog.build_payload()
    assert payload["structure"]["can_compress"] is True
    assert payload["structure"]["can_fold"] is False
    assert payload["structure"]["can_coil"] == "unknown"


def test_note_only_feedback_saves_and_links(qapp, context):
    record_id = _create_record(context)
    dialog = _dialog(context, record_id)
    dialog.user_note.setPlainText("只写一句备注也必须可以保存")
    feedback_id = dialog.save()
    assert len(context.calibration_feedback_service.for_record(record_id)) == 1
    feedback = context.calibration_feedback_service.load(feedback_id)
    assert feedback.user_note == "只写一句备注也必须可以保存"
    assert feedback.source == "user"
    assert context.history_record_v2_service.load_v2(record_id).calibration_feedback_id == feedback_id


def test_compress_only_feedback_saves(qapp, context):
    record_id = _create_record(context)
    dialog = _dialog(context, record_id)
    dialog.tri_state_combos["can_compress"].setCurrentIndex(1)
    feedback_id = dialog.save()
    feedback = context.calibration_feedback_service.load(feedback_id)
    assert feedback.structure.can_compress is True
    assert feedback.structure.can_fold == "unknown"


def test_edit_same_feedback_keeps_id_without_duplicate(qapp, context):
    record_id = _create_record(context)
    first = _dialog(context, record_id)
    first.user_note.setPlainText("v1")
    first_id = first.save()
    existing = context.calibration_feedback_service.load(first_id)
    second = _dialog(context, record_id, feedback=existing)
    second.user_note.setPlainText("v2")
    second_id = second.save()
    assert second_id == first_id
    assert len(context.calibration_feedback_service.for_record(record_id)) == 1
    assert context.calibration_feedback_service.load(first_id).user_note == "v2"


def test_suggested_package_evidence_is_user_suggested(qapp, context):
    record_id = _create_record(context)
    dialog = _dialog(context, record_id)
    dialog.suggested_method.setText("气泡袋")
    dialog.suggested_spins["length_cm"].setValue(20.0)
    payload = dialog.build_payload()
    assert payload["suggested_package"]["evidence_level"] == "user_suggested"
    feedback_id = dialog.save()
    feedback = context.calibration_feedback_service.load(feedback_id)
    assert feedback.suggested_package.evidence_level == "user_suggested"
    assert feedback.suggested_package.length_cm == 20.0


def test_actual_logistics_zero_preserved_and_empty_is_none(qapp, context):
    record_id = _create_record(context)
    dialog = _dialog(context, record_id)
    empty = dialog.build_payload()
    assert empty["actual_logistics"] is None
    fee = dialog.actual_spins["actual_first_mile_fee_rmb"]
    fee.setValue(5.0)
    fee.setValue(0.0)
    chargeable = dialog.actual_spins["actual_chargeable_weight_kg"]
    chargeable.setValue(1.0)
    chargeable.setValue(0.0)
    payload = dialog.build_payload()
    actual = payload["actual_logistics"]
    assert actual["actual_first_mile_fee_rmb"] == 0.0
    assert actual["actual_chargeable_weight_kg"] == 0.0
    assert actual["actual_package_dimensions"] is None
    assert actual["evidence_level"] == "actual_logistics"
    feedback_id = dialog.save()
    feedback = context.calibration_feedback_service.load(feedback_id)
    assert feedback.actual_logistics.actual_first_mile_fee_rmb == 0.0
    assert feedback.actual_logistics.actual_chargeable_weight_kg == 0.0


def test_save_feedback_does_not_change_revision(qapp, context):
    record_id = _create_record(context)
    assert context.history_record_v2_service.load_v2(record_id).revision == 1
    dialog = _dialog(context, record_id)
    dialog.user_note.setPlainText("反馈不改变 revision")
    dialog.save()
    assert context.history_record_v2_service.load_v2(record_id).revision == 1


def test_empty_feedback_is_rejected(qapp, context):
    record_id = _create_record(context)
    dialog = _dialog(context, record_id)
    with pytest.raises(ValueError, match="反馈内容为空"):
        dialog.save()
