"""CalibrationFeedbackService 测试：部分反馈可保存、0/空语义、导出状态。"""

from __future__ import annotations

from pathlib import Path

import pytest

from profit_accounting_26.application.calibration_feedback_service import CalibrationFeedbackService
from profit_accounting_26.storage import SQLiteStore


@pytest.fixture()
def service(tmp_path: Path):
    store = SQLiteStore(tmp_path / "app.sqlite3")
    store.initialize()
    feedback_service = CalibrationFeedbackService(store)
    feedback_service.initialize()
    return feedback_service


def test_note_only_feedback_saves(service):
    feedback_id = service.save({"record_id": "r-1", "user_note": "这个商品可以压缩"})
    feedback = service.load(feedback_id)
    assert feedback.user_note == "这个商品可以压缩"
    assert feedback.source == "user"
    assert feedback.created_at and feedback.updated_at


def test_single_tri_state_flag_saves(service):
    feedback_id = service.save({"record_id": "r-1", "structure": {"can_compress": True}})
    assert service.load(feedback_id).structure.can_compress is True


def test_feedback_without_actual_first_mile_saves(service):
    feedback_id = service.save({
        "record_id": "r-1",
        "structure": {"can_fold": True, "foldable_parts": ["handle"]},
        "suggested_package": {"length_cm": 20, "width_cm": 15, "height_cm": 3},
    })
    feedback = service.load(feedback_id)
    assert feedback.actual_logistics is None
    assert feedback.suggested_package.length_cm == 20
    assert feedback.suggested_package.evidence_level == "user_suggested"


def test_zero_first_mile_fee_is_valid_not_missing(service):
    feedback_id = service.save({
        "record_id": "r-1", "user_note": "包邮",
        "actual_logistics": {"actual_first_mile_fee_rmb": 0, "evidence_level": "actual_logistics"},
    })
    feedback = service.load(feedback_id)
    assert feedback.actual_logistics.actual_first_mile_fee_rmb == 0.0
    assert feedback.actual_logistics.actual_chargeable_weight_kg is None


def test_user_suggested_never_marked_measured(service):
    feedback_id = service.save({
        "record_id": "r-1",
        "suggested_package": {"length_cm": 10, "evidence_level": "actual_measured"},
    })
    assert service.load(feedback_id).suggested_package.evidence_level == "user_suggested"


def test_empty_feedback_is_rejected(service):
    with pytest.raises(ValueError, match="反馈内容为空"):
        service.save({"record_id": "r-1"})


def test_update_same_feedback_sets_updated_after_export_flag(service):
    feedback_id = service.save({"record_id": "r-1", "user_note": "v1"})
    service.mark_exported([feedback_id], batch_id="batch-1")
    exported = service.load(feedback_id)
    assert exported.calibration_exported_at
    assert exported.calibration_export_batch_id == "batch-1"
    assert exported.feedback_updated_after_export is False
    # 再次保存（修改）：不阻止，只标记状态
    service.save({"feedback_id": feedback_id, "record_id": "r-1", "user_note": "v2"})
    updated = service.load(feedback_id)
    assert updated.user_note == "v2"
    assert updated.feedback_updated_after_export is True
    # 状态不阻止再次导出/保存
    service.mark_exported([feedback_id], batch_id="batch-2")
    reexported = service.load(feedback_id)
    assert reexported.calibration_export_batch_id == "batch-2"
    # 重新成功导出后，修改标记必须恢复 false
    assert reexported.feedback_updated_after_export is False


def test_for_record_and_list_all(service):
    service.save({"record_id": "r-1", "user_note": "a"})
    service.save({"record_id": "r-1", "user_note": "b"})
    service.save({"record_id": "r-2", "user_note": "c"})
    assert len(service.for_record("r-1")) == 2
    assert len(service.list_all()) == 3
    assert all(item.record_id == "r-1" for item in service.for_record("r-1"))


def test_load_missing_feedback_raises(service):
    with pytest.raises(KeyError):
        service.load("missing")
