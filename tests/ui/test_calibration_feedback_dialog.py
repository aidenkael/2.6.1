"""极简实际校准 Dialog：只保留尺寸/重量/修正说明；同一 feedback_id 更新；保留原建议。

覆盖任务书第 23-25 项与对话框语义：
- 实际校准只要求尺寸、重量、修正说明；
- 数字输入默认真空，空 = 未知，0 是合法值；
- 更新同一个 feedback_id，不重复创建；
- 保留主界面已保存的 suggested_package / user_note 相关结构；
- revision 不因反馈改变；空反馈拒绝保存。
"""

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


def test_dialog_only_exposes_dims_weight_and_note(qapp, context):
    """第 23 项：对话框只有实际尺寸、实际重量、修正说明三类输入。"""
    record_id = _create_record(context)
    dialog = _dialog(context, record_id)
    for attr in ("length_edit", "width_edit", "height_edit", "weight_edit", "user_note"):
        assert hasattr(dialog, attr)
    # 复杂字段已从用户界面移除
    for attr in ("tri_state_combos", "suggested_spins", "actual_spins", "actual_forwarder"):
        assert not hasattr(dialog, attr)
    # 默认真空（空 = 未知）
    assert dialog.length_edit.text() == ""
    assert dialog.weight_edit.text() == ""
    payload = dialog.build_payload()
    assert "actual_logistics" not in payload


def test_zero_is_a_legal_measured_value(qapp, context):
    record_id = _create_record(context)
    dialog = _dialog(context, record_id)
    dialog.length_edit.setText("0")
    dialog.weight_edit.setText("0")
    payload = dialog.build_payload()
    actual = payload["actual_logistics"]
    assert actual["actual_package_dimensions"] == {"length_cm": 0.0}
    assert actual["actual_package_weight_g"] == 0.0
    assert actual["evidence_level"] == "actual_measured"


def test_actual_calibration_saves_and_links(qapp, context):
    record_id = _create_record(context)
    dialog = _dialog(context, record_id)
    dialog.length_edit.setText("23")
    dialog.width_edit.setText("14")
    dialog.height_edit.setText("3")
    dialog.weight_edit.setText("560")
    dialog.user_note.setPlainText("实际比估算小")
    feedback_id = dialog.save()
    feedback = context.calibration_feedback_service.load(feedback_id)
    assert feedback.actual_logistics.actual_package_dimensions == {
        "length_cm": 23.0,
        "width_cm": 14.0,
        "height_cm": 3.0,
    }
    assert feedback.actual_logistics.actual_package_weight_g == 560.0
    assert feedback.actual_logistics.evidence_level == "actual_measured"
    assert feedback.user_note == "实际比估算小"
    assert context.history_record_v2_service.load_v2(record_id).calibration_feedback_id == feedback_id


def test_update_same_feedback_id_without_duplicate(qapp, context):
    """第 24 项：实际校准更新同一个 feedback_id，不重复创建。"""
    record_id = _create_record(context)
    first = _dialog(context, record_id)
    first.user_note.setPlainText("v1")
    first_id = first.save()
    existing = context.calibration_feedback_service.load(first_id)
    second = _dialog(context, record_id, feedback=existing)
    second.length_edit.setText("30")
    second_id = second.save()
    assert second_id == first_id
    assert len(context.calibration_feedback_service.for_record(record_id)) == 1


def test_calibration_preserves_existing_suggested_package(qapp, context):
    """第 25 项：实际校准保留主界面已保存的 suggested_package。"""
    record_id = _create_record(context)
    # 主界面语义：先保存一条带 suggested_package / user_note 的反馈
    first_id = context.calibration_feedback_service.save(
        {
            "record_id": record_id,
            "source": "user",
            "user_note": "这个包可以压扁",
            "suggested_package": {
                "packaging_method": "压扁放平",
                "length_cm": 25.0,
                "width_cm": 18.0,
                "height_cm": 2.0,
                "weight_g": 300.0,
                "evidence_level": "user_suggested",
            },
        }
    )
    context.history_record_v2_service.link_feedback(record_id, first_id)
    existing = context.calibration_feedback_service.load(first_id)
    dialog = _dialog(context, record_id, feedback=existing)
    dialog.length_edit.setText("24")
    dialog.weight_edit.setText("310")
    second_id = dialog.save()
    assert second_id == first_id
    feedback = context.calibration_feedback_service.load(first_id)
    # suggested_package 与 user_note 保留，实测数据追加
    assert feedback.suggested_package is not None
    assert feedback.suggested_package.evidence_level == "user_suggested"
    assert feedback.suggested_package.length_cm == 25.0
    assert feedback.user_note == "这个包可以压扁"
    assert feedback.actual_logistics.actual_package_dimensions == {"length_cm": 24.0}
    assert feedback.actual_logistics.actual_package_weight_g == 310.0


def test_save_feedback_does_not_change_revision(qapp, context):
    record_id = _create_record(context)
    assert context.history_record_v2_service.load_v2(record_id).revision == 1
    dialog = _dialog(context, record_id)
    dialog.user_note.setPlainText("反馈不改变 revision")
    dialog.save()
    assert context.history_record_v2_service.load_v2(record_id).revision == 1


def test_empty_calibration_is_rejected(qapp, context):
    record_id = _create_record(context)
    dialog = _dialog(context, record_id)
    assert not dialog._has_input()
    with pytest.raises(ValueError, match="反馈内容为空"):
        dialog.save()
