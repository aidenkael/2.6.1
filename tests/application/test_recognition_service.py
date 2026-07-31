import json

from profit_accounting_26.application.recognition_service import RecognitionService


def test_parse_openai_compatible_vision_payload():
    content = {
        "observation": {
            "product_name": "测试商品",
            "material": "PVC",
            "rigidity": "soft",
            "product_cost_rmb": 12.5,
        },
        "packaging_proposal": None,
    }
    response = {
        "choices": [
            {"message": {"content": json.dumps(content, ensure_ascii=False)}}
        ]
    }
    observation, proposal = RecognitionService.parse_payload(response, model="vision-test")
    assert observation.product_name == "测试商品"
    assert observation.product_cost_rmb == 12.5
    assert observation.source == "vision_api"
    assert observation.model == "vision-test"
    assert proposal is None


def test_parse_main_image_packaging_candidates():
    content = {
        "observation": {
            "product_name": "收纳包",
            "length_cm": 28,
            "width_cm": 20,
            "height_cm": 8,
            "weight_g": 420,
            "confidence": "low",
        },
        "packaging_proposal": {
            "normal": {
                "label": "正常档",
                "packaging_state": "shape_retained",
                "packaging_method": "主图视觉估算包装",
                "length_cm": 30,
                "width_cm": 22,
                "height_cm": 10,
                "weight_g": 480,
                "reasoning_summary": "主图视觉估算，需复核",
                "confidence": "low",
                "needs_review": True,
            },
            "conservative": {
                "label": "保守档",
                "packaging_state": "shape_retained",
                "packaging_method": "主图视觉估算保护包装",
                "length_cm": 32,
                "width_cm": 24,
                "height_cm": 12,
                "weight_g": 550,
                "reasoning_summary": "主图视觉估算，需复核",
                "confidence": "low",
                "needs_review": True,
            },
            "proposal_source": "vision_api",
            "needs_review": True,
            "review_reasons": ["主图视觉估算，需复核"],
        },
    }
    response = {"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]}

    observation, proposal = RecognitionService.parse_payload(response, model="vision-test")

    assert observation.length_cm == 28
    assert observation.weight_g == 420
    assert proposal is not None
    assert proposal.normal.length_cm == 30
    assert proposal.conservative.weight_g == 550
    assert proposal.needs_review is True


def test_single_vision_response_keeps_the_first_observation_as_the_only_input():
    first = RecognitionService.parse_payload(
        {"choices": [{"message": {"content": json.dumps({"observation": {"product_name": "发圈", "material": "satin"}})}}]},
        model="vision-test",
    )[0]
    supplement = RecognitionService.parse_payload(
        {"choices": [{"message": {"content": json.dumps({"observation": {"product_name": "错误名称", "length_cm": 12, "width_cm": 12, "height_cm": 3, "weight_g": 35, "confidence": "low"}})}}]},
        model="vision-test",
    )[0]

    assert first.product_name == "发圈"
    assert supplement.length_cm == 12
