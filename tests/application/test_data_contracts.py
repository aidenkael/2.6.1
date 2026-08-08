"""HistoryRecord V2 / CalibrationFeedback V1 数据合同测试。

覆盖：序列化往返、旧记录兼容读取（V2 字段默认 null）、校验规则、
user_suggested 不升级为 measured、缺失数据不阻止构造。
"""

from __future__ import annotations

import pytest

from profit_accounting_26.application.data_contracts import (
    FEEDBACK_SCHEMA_VERSION,
    LEGACY_RECORD_SCHEMA_VERSION,
    RECORD_SCHEMA_VERSION,
    CalibrationFeedback,
    StructureFeedback,
    attach_v2_block,
    is_legacy_payload,
    record_from_payload,
    v2_block_from_payload,
)


# ---------------------------------------------------------------------------
# HistoryRecord V2
# ---------------------------------------------------------------------------


def _legacy_payload() -> dict:
    """模拟 2.6.1 旧记录：无 _v2 键，layers 结构。"""
    return {
        "id": "legacy-record-1",
        "product_name": "示例商品",
        "product_link": "https://example.com/item",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-02T00:00:00+00:00",
        "product_cost_rmb": 3.5,
        "domestic_shipping_rmb": 0.0,
        "images": [{"relative_path": "images/legacy-record-1/01_abc.png", "sha256": "a" * 64}],
        "layers": {
            "ai_raw": {"observation": {"length_cm": 12}, "packaging_proposal": {"normal": {}}},
            "adopted": {
                "bare": {"length_cm": 12, "width_cm": 10, "height_cm": 1.5, "weight_g": 80},
                "normal": {"packaging_method": "气泡袋", "length_cm": 13, "width_cm": 11,
                            "height_cm": 2.5, "weight_g": 100},
                "conservative": {"packaging_method": "气泡袋+硬纸板", "length_cm": 14,
                                  "width_cm": 12, "height_cm": 3.5, "weight_g": 115},
                "selected_packaging": "正常档",
            },
            "calculated": {"profit_rmb": 5.0, "exchange_rate": 7.2},
            "actual": {},
        },
        "profit_scenarios": {"no_activity": {"profit_rmb": 5.0}},
    }


def test_legacy_record_is_readable_with_v2_fields_null():
    payload = _legacy_payload()
    assert is_legacy_payload(payload)
    record = record_from_payload(payload)
    assert record.record_id == "legacy-record-1"
    assert record.record_schema_version == LEGACY_RECORD_SCHEMA_VERSION
    assert record.revision == 1
    assert record.sku is None and record.quantity is None
    # 裸品事实来自 layers.adopted.bare，且没有混入包装尺寸
    assert record.bare_product == {"length_cm": 12, "width_cm": 10, "height_cm": 1.5, "weight_g": 80}
    # current_estimate 从被选中的正常档派生
    assert record.current_estimate["packaging_method"] == "气泡袋"
    assert record.current_estimate["length_cm"] == 13
    # 利润快照复用现有结构
    assert record.calculation_snapshot["calculated"]["profit_rmb"] == 5.0
    assert record.calculation_snapshot["profit_scenarios"]["no_activity"]["profit_rmb"] == 5.0
    # 旧记录 AI 第一次判断只能近似（明确标注 legacy）
    assert record.ai_initial["legacy_layers_ai_raw"]["observation"]["length_cm"] == 12
    assert record.calibration_feedback_id is None


def test_v2_record_serialization_roundtrip():
    payload = _legacy_payload()
    attach_v2_block(
        payload, origin="new_calculation", revision=1,
        ai_initial={"provider": "openai", "model": "m", "prompt_version": "v8",
                     "observation": {"length_cm": 12}, "estimated_package": {"length_cm": 13},
                     "legacy_packaging_output": {"normal": {}, "conservative": {}}},
        current_estimate={"packaging_method": "气泡袋", "length_cm": 13, "width_cm": 11,
                           "height_cm": 2.5, "weight_g": 100},
        sku="SKU-001", quantity=2,
    )
    assert not is_legacy_payload(payload)
    record = record_from_payload(payload)
    assert record.record_schema_version == RECORD_SCHEMA_VERSION
    assert record.sku == "SKU-001" and record.quantity == 2
    assert record.ai_initial["model"] == "m"
    assert record.ai_initial["legacy_packaging_output"] == {"normal": {}, "conservative": {}}
    assert record.current_estimate["weight_g"] == 100
    serialized = record.to_dict()
    assert serialized["record_schema_version"] == RECORD_SCHEMA_VERSION
    assert serialized["ai_initial"] == record.ai_initial
    # _v2 附加块不删除任何旧字段
    assert payload["layers"]["adopted"]["selected_packaging"] == "正常档"
    assert payload["product_cost_rmb"] == 3.5


def test_attach_v2_block_rejects_bad_origin():
    with pytest.raises(ValueError):
        attach_v2_block({}, origin="import", revision=1, ai_initial={}, current_estimate={})


def test_update_semantics_never_overwrites_ai_initial():
    payload = _legacy_payload()
    attach_v2_block(payload, origin="new_calculation", revision=1,
                    ai_initial={"observation": {"length_cm": 12}}, current_estimate={"weight_g": 100})
    # 编辑路径：ai_initial=None 表示保留
    attach_v2_block(payload, origin="history_edit", revision=2,
                    ai_initial=None, current_estimate={"weight_g": 150})
    block = v2_block_from_payload(payload)
    assert block["revision"] == 2
    assert block["origin"] == "history_edit"
    assert block["ai_initial"] == {"observation": {"length_cm": 12}}
    assert block["current_estimate"] == {"weight_g": 150}


def test_record_payload_must_be_object_with_id():
    with pytest.raises(ValueError):
        record_from_payload({"product_name": "无 id"})
    with pytest.raises(ValueError):
        record_from_payload("not-a-dict")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# CalibrationFeedback V1
# ---------------------------------------------------------------------------


def test_feedback_only_user_note_is_valid():
    feedback = CalibrationFeedback.from_dict({
        "feedback_id": "fb-1", "record_id": "r-1", "source": "user",
        "user_note": "这个商品可以压缩",
    })
    assert feedback.validate() == []
    assert feedback.structure.can_compress == "unknown"
    assert feedback.has_content()


def test_feedback_partial_structure_is_valid():
    feedback = CalibrationFeedback.from_dict({
        "feedback_id": "fb-2", "record_id": "r-1",
        "structure": {"can_compress": True, "compressible_parts": ["body"]},
    })
    assert feedback.validate() == []
    assert feedback.structure.can_compress is True
    assert feedback.structure.can_fold == "unknown"
    assert feedback.structure.compressible_parts == ["body"]


def test_feedback_without_actual_logistics_is_valid():
    feedback = CalibrationFeedback.from_dict({
        "feedback_id": "fb-3", "record_id": "r-1",
        "structure": {"can_fold": True, "foldable_parts": ["handle"]},
    })
    assert feedback.actual_logistics is None
    assert feedback.validate() == []


def test_feedback_roundtrip_keeps_all_sections():
    data = {
        "feedback_id": "fb-4", "record_id": "r-1", "source": "developer",
        "structure": {
            "can_fold": True, "can_compress": False, "can_coil": "unknown",
            "can_disassemble": True, "requires_shape_retention": False,
            "foldable_parts": ["handle"], "compressible_parts": [],
            "coilable_parts": [], "detachable_parts": ["strap"], "rigid_parts": [],
            "axis_behavior": {"length": "preserve", "width": "fold", "height": "compress"},
        },
        "suggested_package": {"length_cm": 20, "width_cm": 15, "height_cm": 3,
                                "weight_g": 120, "packaging_method": "袋装"},
        "actual_logistics": {"actual_first_mile_fee_rmb": 12.5,
                               "actual_chargeable_weight_kg": 0.2,
                               "actual_forwarder": "某货代",
                               "evidence_level": "actual_logistics"},
        "user_note": "提手可以折下去",
    }
    feedback = CalibrationFeedback.from_dict(data)
    assert feedback.validate() == []
    restored = CalibrationFeedback.from_dict(feedback.to_dict())
    assert restored == feedback
    assert restored.feedback_schema_version == FEEDBACK_SCHEMA_VERSION
    assert restored.structure.axis_behavior == {"length": "preserve", "width": "fold", "height": "compress"}


def test_suggested_package_can_never_become_measured():
    feedback = CalibrationFeedback.from_dict({
        "feedback_id": "fb-5", "record_id": "r-1",
        "suggested_package": {"length_cm": 20, "evidence_level": "actual_measured"},
    })
    # from_dict 强制归一为 user_suggested
    assert feedback.suggested_package.evidence_level == "user_suggested"
    assert feedback.validate() == []


def test_structure_from_dict_normalizes_bad_values_to_unknown():
    structure = StructureFeedback.from_dict({
        "can_fold": "yes", "axis_behavior": {"length": "shrink", "height": "preserve"},
        "foldable_parts": [1, "handle"],
    })
    assert structure.can_fold == "unknown"
    assert structure.axis_behavior == {"length": "unknown", "width": "unknown", "height": "preserve"}
    assert structure.foldable_parts == ["handle"]


def test_feedback_rejects_empty_content_and_bad_source():
    feedback = CalibrationFeedback.from_dict({"feedback_id": "fb-6", "record_id": "r-1"})
    assert any("反馈内容为空" in issue for issue in feedback.validate())
    with pytest.raises(ValueError):
        CalibrationFeedback.from_dict({"feedback_id": "fb-7", "record_id": "r-1", "source": "robot",
                                        "user_note": "x"})
    with pytest.raises(ValueError):
        CalibrationFeedback.from_dict({"record_id": "r-1", "user_note": "x"})


def test_feedback_actual_logistics_evidence_levels():
    for level in ("actual_measured", "actual_logistics", "user_observation", "user_estimate", "unknown"):
        feedback = CalibrationFeedback.from_dict({
            "feedback_id": f"fb-{level}", "record_id": "r-1",
            "actual_logistics": {"actual_chargeable_weight_kg": 0.2, "evidence_level": level},
        })
        assert feedback.actual_logistics.evidence_level == level
    feedback = CalibrationFeedback.from_dict({
        "feedback_id": "fb-bad", "record_id": "r-1",
        "actual_logistics": {"actual_chargeable_weight_kg": 0.2, "evidence_level": "guessed"},
    })
    assert feedback.actual_logistics.evidence_level == "unknown"
