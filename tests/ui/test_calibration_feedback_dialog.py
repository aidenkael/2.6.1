"""编辑校准 Dialog（用户校准入口 B）：与主页面当前采用更新同一条记录。

覆盖任务书第八/十三/十四节与对话框语义：
- 预填 current_estimate 长宽高/重量与已保存的用户修正；
- 保存写 suggested_package（恒 user_suggested）+ user_note，并同步 current_estimate；
- 数字输入默认真空，空 = 未知，0 是合法值；单位不塞进输入框；
- 更新同一个 feedback_id，不重复创建；
- 保留已有反馈中的 actual_logistics / structure（legacy 兼容读取不删）；
- 绝不写 actual_logistics、绝不标记 actual_measured；
- revision 不因校准改变；空反馈拒绝保存。
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


def _create_record(context, *, current_estimate=None) -> str:
    # adopted 无完整尺寸 → 派生的 current_estimate 为空，对话框默认空白
    payload = {
        "product_name": "反馈商品",
        "created_at": "2026-08-08T00:00:00Z",
        "layers": {
            "adopted": {
                "selected_packaging": "正常档",
                "normal": {"packaging_method": None},
            },
            "calculated": {},
        },
    }
    record_id = context.record_service.save(payload, images=[], ai_initial={})
    if current_estimate is not None:
        context.history_record_v2_service.update_current_estimate(record_id, current_estimate)
    return record_id


def _dialog(context, record_id, feedback=None) -> CalibrationFeedbackDialog:
    return CalibrationFeedbackDialog(context, record_id, feedback=feedback)


def test_dialog_only_exposes_dims_weight_and_note(qapp, context):
    """对话框只有尺寸、重量、用户修正三类输入；单位独立于输入框。"""
    record_id = _create_record(context)
    dialog = _dialog(context, record_id)
    for attr in ("length_edit", "width_edit", "height_edit", "weight_edit", "user_note"):
        assert hasattr(dialog, attr)
    # 复杂字段已从用户界面移除
    for attr in ("tri_state_combos", "suggested_spins", "actual_spins", "actual_forwarder"):
        assert not hasattr(dialog, attr)
    # 默认真空（空 = 未知），占位文字不再塞单位说明
    assert dialog.length_edit.text() == ""
    assert dialog.weight_edit.text() == ""
    assert "单位" not in dialog.length_edit.placeholderText()
    payload = dialog.build_payload()
    assert "actual_logistics" not in payload


def test_prefills_current_estimate_and_note(qapp, context):
    """第 8 项：对话框预填 current_estimate 长宽高/重量与已保存用户修正。"""
    record_id = _create_record(
        context,
        current_estimate={
            "packaging_method": None,
            "length_cm": 27.0,
            "width_cm": 17.0,
            "height_cm": 4.0,
            "weight_g": 30.0,
        },
    )
    first_id = context.calibration_feedback_service.save(
        {"record_id": record_id, "source": "user", "user_note": "可以压扁"}
    )
    context.history_record_v2_service.link_feedback(record_id, first_id)
    existing = context.calibration_feedback_service.load(first_id)
    dialog = _dialog(context, record_id, feedback=existing)
    assert dialog.length_edit.text() == "27"
    assert dialog.width_edit.text() == "17"
    assert dialog.height_edit.text() == "4"
    assert dialog.weight_edit.text() == "30"
    assert dialog.user_note.toPlainText() == "可以压扁"


def test_zero_is_a_legal_value(qapp, context):
    """第 14 项相关：0 是合法输入；写入 suggested_package，不是实测。"""
    record_id = _create_record(context)
    dialog = _dialog(context, record_id)
    dialog.length_edit.setText("0")
    dialog.weight_edit.setText("0")
    payload = dialog.build_payload()
    assert "actual_logistics" not in payload
    suggested = payload["suggested_package"]
    assert suggested["length_cm"] == 0.0
    assert suggested["weight_g"] == 0.0
    assert suggested["evidence_level"] == "user_suggested"


def test_calibration_saves_suggested_links_and_syncs_current_estimate(qapp, context):
    """第 9 项：历史页校准保存同步 current_estimate + suggested_package + user_note。"""
    record_id = _create_record(context)
    dialog = _dialog(context, record_id)
    dialog.length_edit.setText("23")
    dialog.width_edit.setText("14")
    dialog.height_edit.setText("3")
    dialog.weight_edit.setText("560")
    dialog.user_note.setPlainText("实际比估算小")
    feedback_id = dialog.save()
    feedback = context.calibration_feedback_service.load(feedback_id)
    assert feedback.suggested_package is not None
    assert feedback.suggested_package.length_cm == 23.0
    assert feedback.suggested_package.weight_g == 560.0
    assert feedback.suggested_package.evidence_level == "user_suggested"
    assert feedback.actual_logistics is None
    assert feedback.user_note == "实际比估算小"
    v2 = context.history_record_v2_service.load_v2(record_id)
    assert v2.calibration_feedback_id == feedback_id
    assert v2.current_estimate["length_cm"] == 23.0
    assert v2.current_estimate["weight_g"] == 560.0


def test_update_same_feedback_id_without_duplicate(qapp, context):
    """第 15 项：编辑校准更新同一个 feedback_id，不重复创建。"""
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


def test_calibration_preserves_legacy_actual_logistics(qapp, context):
    """legacy 兼容：已有反馈中的 actual_logistics / structure 更新时原样保留。"""
    record_id = _create_record(context)
    first_id = context.calibration_feedback_service.save(
        {
            "record_id": record_id,
            "source": "user",
            "user_note": "旧备注",
            "actual_logistics": {
                "actual_package_dimensions": {"length_cm": 24.0},
                "actual_package_weight_g": 310.0,
                "evidence_level": "actual_measured",
            },
        }
    )
    context.history_record_v2_service.link_feedback(record_id, first_id)
    existing = context.calibration_feedback_service.load(first_id)
    dialog = _dialog(context, record_id, feedback=existing)
    dialog.length_edit.setText("25")
    dialog.user_note.setPlainText("新备注")
    second_id = dialog.save()
    assert second_id == first_id
    feedback = context.calibration_feedback_service.load(first_id)
    # 新输入更新 suggested_package 与 user_note
    assert feedback.suggested_package is not None
    assert feedback.suggested_package.length_cm == 25.0
    assert feedback.suggested_package.evidence_level == "user_suggested"
    assert feedback.user_note == "新备注"
    # legacy 实测数据保留不删
    assert feedback.actual_logistics is not None
    assert feedback.actual_logistics.actual_package_dimensions == {"length_cm": 24.0}
    assert feedback.actual_logistics.actual_package_weight_g == 310.0


def test_save_feedback_does_not_change_revision(qapp, context):
    record_id = _create_record(context)
    assert context.history_record_v2_service.load_v2(record_id).revision == 1
    dialog = _dialog(context, record_id)
    dialog.user_note.setPlainText("校准不改变 revision")
    dialog.save()
    assert context.history_record_v2_service.load_v2(record_id).revision == 1


def test_empty_calibration_is_rejected(qapp, context):
    record_id = _create_record(context)
    dialog = _dialog(context, record_id)
    assert not dialog._has_input()
    with pytest.raises(ValueError, match="反馈内容为空"):
        dialog.save()
