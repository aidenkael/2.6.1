import json

from profit_accounting_26.application.recognition_service import RecognitionService


def test_prompt_scans_every_image_without_slot_restrictions():
    prompt = RecognitionService._prompt(2)
    assert "2 \u5f20\u56fe\u7247" in prompt
    assert "shipment" in prompt
    assert "\u8fd0\u8d39" in prompt or "\u4ef7\u683c" in prompt
    assert "\u4f18\u5148\u7ea7" in prompt
    assert "rigidity" in prompt
    assert "quantity_summary" in prompt


def test_parse_keeps_evidence_money_types_and_normalized_category():
    payload = {
        "observation": {"product_name": "\u889c\u5b50", "product_type": "split toe socks", "product_cost_rmb": 5.8, "product_cost_value_type": "exact", "domestic_shipping_rmb": 4, "domestic_shipping_value_type": "estimated"},
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
