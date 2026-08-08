"""AppContext 正确初始化 CalibrationFeedbackService（复用同一个 SQLiteStore）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from profit_accounting_26.application import AppContext
from profit_accounting_26.application.calibration_feedback_service import CalibrationFeedbackService


@pytest.fixture()
def context(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


def test_app_context_initializes_calibration_feedback_service(context):
    service = context.calibration_feedback_service
    assert isinstance(service, CalibrationFeedbackService)
    assert service.store is context.store


def test_feedback_service_initialized_read_write_on_same_store(context):
    service = context.calibration_feedback_service
    feedback_id = service.save({"record_id": "r-1", "user_note": "同一个数据库"})
    assert service.load(feedback_id).user_note == "同一个数据库"
    # 反馈写入独立的 calibration_feedback 表，不触碰 records 表
    assert context.store.record_exists("r-1") is False
