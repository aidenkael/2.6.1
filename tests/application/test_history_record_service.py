"""HistoryRecordV2Service 测试：create / update same record / revision / ai_initial 不可变。"""

from __future__ import annotations

from pathlib import Path

import pytest

from profit_accounting_26.application.history_record_service import HistoryRecordV2Service
from profit_accounting_26.storage import SQLiteStore


@pytest.fixture()
def service(tmp_path: Path):
    store = SQLiteStore(tmp_path / "app.sqlite3")
    store.initialize()
    return HistoryRecordV2Service(store)


def _payload(name="示例商品") -> dict:
    return {
        "product_name": name,
        "layers": {"ai_raw": {"observation": {"length_cm": 12}}, "adopted": {}, "calculated": {}},
    }


def test_create_new_record_sets_revision_one_and_ai_initial(service):
    record_id = service.create_record(
        _payload(),
        ai_initial={"model": "m", "observation": {"length_cm": 12}, "estimated_package": {"weight_g": 100}},
        current_estimate={"weight_g": 100},
    )
    record = service.load_v2(record_id)
    assert record.revision == 1
    assert record.origin == "new_calculation"
    assert record.record_schema_version == "history-record-v2"
    assert record.ai_initial["model"] == "m"
    assert record.current_estimate["weight_g"] == 100


def test_create_twice_with_same_id_is_rejected(service):
    record_id = service.create_record(_payload(), ai_initial={})
    with pytest.raises(ValueError):
        service.create_record(_payload(), ai_initial={}, record_id=record_id)


def test_update_same_record_increments_revision_and_keeps_history(service):
    record_id = service.create_record(
        _payload(), ai_initial={"observation": {"length_cm": 12}}, current_estimate={"weight_g": 100},
    )
    service.update_record(record_id, _payload("修改后商品"), current_estimate={"weight_g": 150})
    record = service.load_v2(record_id)
    # update 同一条记录而不是生成新记录
    assert len(service.store.list_records()) == 1
    assert record.revision == 2
    assert record.origin == "history_edit"
    assert record.product_name == "修改后商品"
    assert record.current_estimate["weight_g"] == 150


def test_history_edit_never_overwrites_ai_initial(service):
    record_id = service.create_record(
        _payload(),
        ai_initial={"model": "first-model", "observation": {"length_cm": 12}},
        current_estimate={"weight_g": 100},
    )
    # 连续两次编辑，ai_initial 保持第一次 AI 判断
    service.update_record(record_id, _payload(), current_estimate={"weight_g": 150})
    service.update_record(record_id, _payload(), current_estimate={"weight_g": 200})
    record = service.load_v2(record_id)
    assert record.revision == 3
    assert record.ai_initial["model"] == "first-model"
    assert record.ai_initial["observation"] == {"length_cm": 12}


def test_save_dispatches_create_then_update(service):
    record_id = service.save(_payload(), ai_initial={"model": "m"}, current_estimate={"weight_g": 1})
    assert service.load_v2(record_id).revision == 1
    service.save(_payload(), record_id=record_id, current_estimate={"weight_g": 2})
    record = service.load_v2(record_id)
    assert record.revision == 2
    assert record.ai_initial == {"model": "m"}


def test_link_feedback_reference_only(service):
    record_id = service.create_record(_payload(), ai_initial={})
    service.link_feedback(record_id, "fb-001")
    assert service.load_v2(record_id).calibration_feedback_id == "fb-001"
    # 挂反馈不算一次内容编辑：revision 不变
    assert service.load_v2(record_id).revision == 1


def test_legacy_records_stay_readable_and_writable(service):
    # 旧生产路径直接写入的记录（无 _v2）
    legacy_id = service.store.save_new_record({
        "product_name": "旧商品",
        "layers": {
            "ai_raw": {"observation": {"length_cm": 5}},
            "adopted": {"bare": {"weight_g": 50}, "selected_packaging": "正常档",
                          "normal": {"packaging_method": "袋装", "length_cm": 6, "width_cm": 5,
                                       "height_cm": 2, "weight_g": 60}},
            "calculated": {"profit_rmb": 1.0},
        },
    })
    record = service.load_v2(legacy_id)
    assert record.record_schema_version == "2.6.1"
    assert record.current_estimate["packaging_method"] == "袋装"
    # 在旧记录上做 V2 编辑：旧字段保留，V2 字段附加
    service.update_record(legacy_id, {"product_name": "旧商品-修改"}, current_estimate={"weight_g": 70})
    payload = service.store.load_record(legacy_id)
    assert payload["layers"]["ai_raw"]["observation"]["length_cm"] == 5
    assert service.load_v2(legacy_id).revision == 2
    assert service.record_schema_version(legacy_id) == "history-record-v2"
