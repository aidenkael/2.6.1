import json

from profit_accounting_26.application.recognition_service import RecognitionService


def test_prompt_scans_every_image_without_slot_restrictions():
    prompt = RecognitionService._prompt(2)
    assert "逐张查看全部图片" in prompt
    assert "图片顺序和图片框类型不代表字段职责" in prompt
    assert "页面运费" in prompt
    assert "confirmed_facts 是用户已经确认的数据，优先级最高" in prompt
    assert "体积重" in prompt and "利润率" in prompt
    # v1.4: rigidity is now an intentional structural field in the prompt
    assert "rigidity" in prompt
    assert "normal" not in prompt


def test_parse_keeps_evidence_money_types_and_normalized_category():
    payload = {
        "observation": {"product_name": "袜子", "product_type": "split toe socks", "product_cost_rmb": 5.8, "product_cost_value_type": "exact", "domestic_shipping_rmb": 4, "domestic_shipping_value_type": "estimated"},
        "field_evidence": {"product_cost_rmb": {"source_image_index": 1, "raw_text": "5.80", "confidence": "high"}, "domestic_shipping_rmb": {"source_image_index": 1, "raw_text": "estimated shipping 4", "confidence": "high"}},
        "packaging_proposal": None,
    }
    response = {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}
    observation, _ = RecognitionService.parse_payload(response, model="test")
    assert observation.product_cost_rmb == 5.8
    assert observation.domestic_shipping_rmb == 4
    assert observation.product_cost_value_type == "exact"
    assert observation.domestic_shipping_value_type == "estimated"
    assert observation.product_family_code == "hosiery"
    assert observation.raw_payload["field_evidence"]["product_cost_rmb"]["raw_text"] == "5.80"
