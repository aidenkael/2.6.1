import json

import pytest

from profit_accounting_26.application.diagnostic_logger import DiagnosticLogger
from profit_accounting_26.application.recognition_service import RecognitionResponseError, RecognitionService


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


def test_multi_image_payload_order_is_stable_for_product_and_weight_evidence(tmp_path):
    product = tmp_path / "product.png"
    weight = tmp_path / "weight.png"
    product.write_bytes(b"product-evidence")
    weight.write_bytes(b"weight-evidence")

    forward = RecognitionService._stable_paths([{"path": str(product)}, {"path": str(weight)}])
    reversed_order = RecognitionService._stable_paths([{"path": str(weight)}, {"path": str(product)}])

    assert forward == reversed_order
    prompt = RecognitionService._prompt(2)
    assert "Merge product, price, dimensions, weight, structure, and packaging evidence" in prompt
    assert "image sequence and image slot have no semantic meaning" in prompt


def test_ambiguous_bare_dimension_is_ignored_and_reported_without_losing_weight():
    content = {
        "observation": {
            "product_name": "structured item",
            "length_cm": "45-65-75",
            "width_cm": "20",
            "height_cm": "5",
            "weight_g": "100",
        },
        "packaging_proposal": None,
    }
    observation, proposal = RecognitionService.parse_payload(
        {"choices": [{"message": {"content": json.dumps(content)}}]}, model="vision-test"
    )
    assert proposal is None
    assert observation.length_cm is None
    assert observation.weight_g == 100
    issue = observation.raw_payload["numeric_parse_issues"]["observation.length_cm"]
    assert issue["raw_value"] == "45-65-75"
    assert issue["reason"] == "ambiguous_or_non_numeric"


def test_bad_packaging_number_is_ignored_while_other_candidate_data_continues():
    content = {
        "observation": {
            "product_name": "structured item", "overall_form": "soft_flat",
            "length_cm": 20, "width_cm": 10, "height_cm": 2, "weight_g": 100,
        },
        "packaging_proposal": {
            "normal": {"length_cm": "45-65-75", "width_cm": 12, "height_cm": 3, "weight_g": 110},
            "conservative": {"length_cm": 24, "width_cm": 14, "height_cm": 4, "weight_g": 130},
        },
    }
    observation, proposal = RecognitionService.parse_payload(
        {"choices": [{"message": {"content": json.dumps(content)}}]}, model="vision-test"
    )
    assert observation.raw_payload["numeric_parse_issues"]["packaging_proposal.normal.length_cm"]["raw_value"] == "45-65-75"
    assert proposal is not None
    assert proposal.normal.is_complete()
    assert proposal.conservative.is_complete()


def test_numeric_strings_and_simple_units_are_normalized():
    content = {
        "observation": {
            "product_name": "structured item", "product_cost_rmb": "100", "domestic_shipping_rmb": "55.0",
            "length_cm": "55cm", "width_cm": "20", "height_cm": "5", "weight_g": "100 g",
        },
        "packaging_proposal": None,
    }
    observation, _ = RecognitionService.parse_payload(
        {"choices": [{"message": {"content": json.dumps(content)}}]}, model="vision-test"
    )
    assert (observation.product_cost_rmb, observation.domestic_shipping_rmb) == (100, 55)
    assert (observation.length_cm, observation.width_cm, observation.height_cm, observation.weight_g) == (55, 20, 5, 100)


def test_parse_failure_retains_sanitized_raw_response_and_traceback(tmp_path, monkeypatch):
    class Settings:
        def load(self):
            return {"vision_api_endpoint": "https://example.invalid", "vision_api_key": "test-key", "vision_api_model": "test-model"}

    image = tmp_path / "product.png"
    image.write_bytes(b"image")
    raw_response = {"choices": [{"message": {"content": "not json"}}]}
    service = RecognitionService(Settings())
    monkeypatch.setattr(service, "_request_payload", lambda **_kwargs: raw_response)
    operation = DiagnosticLogger(tmp_path, {}).begin_operation("ai-recognition")

    with pytest.raises(RecognitionResponseError):
        service.recognize([{"path": str(image)}], diagnostic_operation=operation)

    logged = json.loads((operation.root / "ai-response.json").read_text(encoding="utf-8"))
    assert logged["provider_raw_response"] == raw_response
    assert logged["parse_error"]
    assert "RecognitionResponseError" in logged["traceback"]
    assert "test-key" not in json.dumps(logged)


@pytest.mark.parametrize("overall_form", ["soft_flat", "flexible_chain", "hard_flat", "soft_bulky"])
def test_recognizable_outline_with_missing_weight_gets_complete_low_confidence_candidate(overall_form: str):
    content = {
        "observation": {
            "product_name": "结构化商品", "overall_form": overall_form,
            "length_cm": 20, "width_cm": 10, "height_cm": 4, "weight_g": None,
        },
        "packaging_proposal": {},
    }
    observation, proposal = RecognitionService.parse_payload(
        {"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]}, model="vision-test"
    )
    assert proposal is not None
    assert proposal.normal.is_complete()
    assert proposal.conservative.is_complete()
    assert proposal.normal.confidence == "low"
    assert proposal.normal.length_cm >= observation.length_cm
    assert observation.raw_payload["vision_packaging_completion"] == "generated_from_recognized_outline"
