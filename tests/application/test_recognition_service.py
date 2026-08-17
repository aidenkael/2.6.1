import json

import pytest

from profit_accounting_26.application.diagnostic_logger import DiagnosticLogger
from profit_accounting_26.application.recognition_service import RecognitionResponseError, RecognitionService


def _v1_response() -> dict:
    return {
        "choices": [{"message": {"content": json.dumps({
            "product_name": "女士单肩包",
            "observed": {
                "product_price_rmb": None, "page_shipping_rmb": None,
                "bare_dimensions_cm": {"length": None, "width": None, "height": None},
                "bare_weight_g": None,
            },
            "shipment": {"length_cm": 17, "width_cm": 32, "height_cm": 17, "weight_g": 720, "state": "袋装"},
            "note": "",
        }, ensure_ascii=False)}}],
    }


def _recognition_service_for_provider(provider: str):
    class Settings:
        @staticmethod
        def load():
            return {"vision_api_timeout_seconds": 30}

    class Profile:
        api_url = "https://example.invalid"
        model_name = "vision-test"

    Profile.provider = provider

    class Store:
        @staticmethod
        def bound_profile(_purpose):
            return Profile(), "secret"

    return RecognitionService(Settings(), Store())


def test_openai_vision_request_keeps_strict_schema_and_simple_prompt(tmp_path, monkeypatch):
    image = tmp_path / "product.png"
    image.write_bytes(b"image")
    captured = {}
    service = _recognition_service_for_provider("OpenAI")
    monkeypatch.setattr(service, "_request_payload", lambda **kwargs: captured.update(kwargs) or _v1_response())

    observation, proposal = service.recognize([{"path": str(image)}])

    assert observation.product_name == "女士单肩包"
    assert proposal is not None and proposal.normal.weight_g == 720
    assert captured["response_format"]["json_schema"]["strict"] is True
    prompt = captured["content"][0]["text"]
    assert '"bare_dimensions_cm"' not in prompt
    assert "符合给定 JSON Schema" in prompt


@pytest.mark.parametrize("provider", ["DeepSeek", "GLM", "阿里云百炼", "自定义"])
def test_non_openai_vision_request_uses_prompt_contract_without_response_format(tmp_path, monkeypatch, provider):
    image = tmp_path / "product.png"
    image.write_bytes(b"image")
    captured = {}
    service = _recognition_service_for_provider(provider)
    monkeypatch.setattr(service, "_request_payload", lambda **kwargs: captured.update(kwargs) or _v1_response())

    service.recognize(
        [{"path": str(image)}],
        user_context={"product_name": {"value": "用户确认名称", "source": "user_confirmed"}},
    )

    assert captured["response_format"] is None
    prompt = captured["content"][0]["text"]
    for field in ("product_name", "product_price_rmb", "page_shipping_rmb", "bare_dimensions_cm", "bare_weight_g", "shipment", "length_cm", "weight_g", "state", "note"):
        assert field in prompt


def test_recognition_request_sends_confirmed_facts_at_one_level(tmp_path, monkeypatch):
    image = tmp_path / "product.png"
    image.write_bytes(b"image")
    captured = {}
    service = _recognition_service_for_provider("DeepSeek")
    monkeypatch.setattr(service, "_request_payload", lambda **kwargs: captured.update(kwargs) or _v1_response())

    service.recognize(
        [{"path": str(image)}],
        user_context={"confirmed_facts": {"weight_g": {"value": 580, "source": "user_confirmed"}}},
    )

    fact_text = next(item["text"] for item in captured["content"] if item["type"] == "text" and item["text"].startswith("confirmed_facts"))
    assert fact_text.count('"confirmed_facts"') == 0
    assert '"weight_g"' in fact_text


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
    assert "图片" in prompt
    assert "shipment" in prompt


def test_v13_prompt_keeps_schema_and_adds_shipment_quantity_guidance():
    prompt = RecognitionService._prompt(1, include_json_shape=False)

    assert RecognitionService.PROMPT_VERSION == "2.6.1-visual-v1.9"
    assert set(RecognitionService.RESPONSE_SCHEMA["properties"]) == {
        "product_name", "observed", "bare_estimate", "shipment", "structure", "quantity", "field_evidence", "note"
    }
    assert "purchase_quantity" in prompt
    assert "quantity" in prompt
    assert "null" in prompt
    assert "L/W/H" in prompt
    assert "purchase_quantity" in prompt


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


def test_adjustable_or_component_dimensions_stay_as_evidence_not_outer_dimensions():
    content = {
        "observation": {
            "product_name": "flexible item", "length_cm": 55, "width_cm": 70, "height_cm": 2.5,
            "weight_g": 110, "dimension_scope": "unknown",
        },
        "field_evidence": {"dimensions": {"raw_text": "45-65*65-75*2.5cm", "meaning": ""}},
        "packaging_proposal": None,
    }
    observation, _ = RecognitionService.parse_payload(
        {"choices": [{"message": {"content": json.dumps(content)}}]}, model="vision-test"
    )
    assert (observation.length_cm, observation.width_cm, observation.height_cm) == (None, None, None)
    assert observation.raw_payload["field_evidence"]["dimensions"]["raw_text"] == "45-65*65-75*2.5cm"
    assert observation.raw_payload["dimension_semantic_issue"] == "dimension_evidence_not_outer_dimensions"


def test_explicit_single_item_three_dimensions_remain_available():
    content = {
        "observation": {
            "product_name": "structured item", "length_cm": 17, "width_cm": 8.8, "height_cm": 4.7,
            "dimension_scope": "product_size",
        },
        "field_evidence": {"dimensions": {"raw_text": "17×8.8×4.7cm", "meaning": "single item outer dimensions"}},
        "packaging_proposal": None,
    }
    observation, _ = RecognitionService.parse_payload(
        {"choices": [{"message": {"content": json.dumps(content)}}]}, model="vision-test"
    )
    assert (observation.length_cm, observation.width_cm, observation.height_cm) == (17, 8.8, 4.7)


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


def test_v1_observed_facts_and_shipment_are_independent():
    payload = {
        "product_name": "女士单肩包",
        "observed": {
            "product_price_rmb": None,
            "page_shipping_rmb": 0,
            "bare_dimensions_cm": {"length": 45, "width": None, "height": 15},
            "bare_weight_g": 580,
        },
        "shipment": {
            "length_cm": 46, "width_cm": 31, "height_cm": 8,
            "weight_g": 760, "state": "压扁并整理肩带后紧凑发货",
        },
        "note": "",
    }
    observation, proposal = RecognitionService.parse_payload(
        {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]},
        model="vision-v1",
    )

    assert observation.product_cost_rmb is None  # 看不到价格时不补造
    assert observation.domestic_shipping_rmb == 0
    assert (observation.length_cm, observation.width_cm, observation.height_cm) == (45, None, 15)
    assert observation.weight_g == 580
    assert proposal is not None
    assert proposal.normal.weight_g == 760
    assert proposal.normal.packaging_method == "压扁并整理肩带后紧凑发货"
    assert proposal.normal.to_dict() != observation.to_dict()
    assert proposal.applied_profile_ids == []
    assert proposal.proposal_source == "vision_ai_v1"


def test_v1_nonpositive_shipment_values_fail_basic_validation_without_cal_fallback():
    payload = {
        "product_name": "金属发夹",
        "observed": {
            "product_price_rmb": None, "page_shipping_rmb": None,
            "bare_dimensions_cm": {"length": None, "width": None, "height": None},
            "bare_weight_g": None,
        },
        "shipment": {"length_cm": -1, "width_cm": 5, "height_cm": 2, "weight_g": 0, "state": "袋装"},
        "note": "",
    }
    _, proposal = RecognitionService.parse_payload(
        {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]},
        model="vision-v1",
    )
    assert proposal is not None
    assert proposal.normal.length_cm is None
    assert proposal.normal.weight_g is None
    assert not proposal.normal.is_complete()
    issues = proposal.candidate_records["runtime_v1_validation"]["parse_issues"]
    assert issues["shipment.length_cm"]["reason"] == "nonpositive_shipment_value"
