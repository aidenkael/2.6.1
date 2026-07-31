import json
from profit_accounting_26.application.recognition_service import RecognitionService


def test_prompt_removes_image_type_restriction():
    prompt = RecognitionService._prompt(2)
    assert "不存在“主图只识别商品" in prompt
    assert "逐张扫描全部可见信息" in prompt
    assert "国内运费为0时返回0" in prompt


def test_parse_keeps_field_evidence_in_raw_payload():
    payload = {
        "observation": {"product_name":"袜子", "product_cost_rmb":5.8, "domestic_shipping_rmb":0},
        "field_evidence": {"product_cost_rmb":{"source_image_index":1,"raw_text":"¥5.80","confidence":"high"}},
        "packaging_proposal": None,
    }
    response = {"choices":[{"message":{"content":json.dumps(payload,ensure_ascii=False)}}]}
    observation, _ = RecognitionService.parse_payload(response, model="test")
    assert observation.product_cost_rmb == 5.8
    assert observation.domestic_shipping_rmb == 0
    assert observation.raw_payload["field_evidence"]["product_cost_rmb"]["raw_text"] == "¥5.80"
