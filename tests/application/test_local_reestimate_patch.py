import json

import pytest

from profit_accounting_26.application.local_reestimate_service import LocalReestimateService
from profit_accounting_26.application.recognition_service import RecognitionUnavailableError


def _context():
    return {
        "product_name": "女士单肩包",
        "confirmed_facts": {
            "bare_dimensions_cm": {"length": 45, "width": 30, "height": 15},
            "bare_weight_g": 580,
        },
        "current_shipment": {
            "length_cm": 49, "width_cm": 34, "height_cm": 19, "weight_g": 820,
        },
        "user_correction": "这个包可以压扁，肩带可以拆下来。",
    }


def test_context_contains_only_v1_inputs_and_excludes_runtime_forbidden_data():
    prompt = LocalReestimateService._context(
        **_context(),
        images=["secret-image"],
        cal_summary=["CAL-001"],
        actual_first_mile_fee_rmb=26,
        actual_forwarder="深圳货代",
        observation_patch={"compressibility": "good"},
    )
    for expected in ("女士单肩包", "45", "580", "820", "肩带可以拆下来"):
        assert expected in prompt
    for forbidden_value in ("secret-image", "CAL-001", "深圳货代", "compressibility"):
        assert forbidden_value not in prompt
    assert "normal" not in prompt and "conservative" not in prompt
    for field in ("shipment", "length_cm", "width_cm", "height_cm", "weight_g", "state", "note"):
        assert field in prompt


def test_openai_reestimate_keeps_strict_schema_and_simple_prompt(monkeypatch):
    class Profile:
        api_url = "https://example.invalid"
        model_name = "text-model"
        provider = "OpenAI"

    class Store:
        @staticmethod
        def bound_profile(_purpose):
            return Profile(), "secret"

    response_payload = {
        "shipment": {"length_cm": 46, "width_cm": 31, "height_cm": 8, "weight_g": 760, "state": "袋装"},
        "note": "",
    }

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read():
            return json.dumps({"choices": [{"message": {"content": json.dumps(response_payload, ensure_ascii=False)}}]}, ensure_ascii=False).encode("utf-8")

    captured = {}
    monkeypatch.setattr(
        "profit_accounting_26.application.local_reestimate_service.urlopen",
        lambda request, timeout: captured.update(body=json.loads(request.data.decode("utf-8")), timeout=timeout) or Response(),
    )

    LocalReestimateService(Store()).reestimate(**_context())

    assert captured["body"]["response_format"]["json_schema"]["strict"] is True
    prompt = captured["body"]["messages"][0]["content"]
    assert '"shipment"' not in prompt.split("输入：", 1)[0]
    assert "符合给定 JSON Schema" in prompt


def test_empty_user_correction_is_rejected_before_any_api_call():
    class Store:
        @staticmethod
        def bound_profile(_purpose):
            raise AssertionError("API must not be called")

    context = _context()
    context["user_correction"] = "  "
    with pytest.raises(RecognitionUnavailableError, match="请先填写用户修正原因"):
        LocalReestimateService(Store()).reestimate(**context)


def test_corrected_reestimate_returns_one_shipment_candidate(monkeypatch):
    class Profile:
        api_url = "https://example.invalid"
        model_name = "text-model"
        provider = "自定义"

    class Store:
        @staticmethod
        def bound_profile(_purpose):
            return Profile(), "secret"

    response_payload = {
        "shipment": {
            "length_cm": 46, "width_cm": 31, "height_cm": 8,
            "weight_g": 760, "state": "压扁并整理肩带后紧凑发货",
        },
        "note": "",
    }

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read():
            data = {"choices": [{"message": {"content": json.dumps(response_payload, ensure_ascii=False)}}]}
            return json.dumps(data, ensure_ascii=False).encode("utf-8")

    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("profit_accounting_26.application.local_reestimate_service.urlopen", fake_urlopen)
    result = LocalReestimateService(Store()).reestimate(**_context())

    assert result.shipment is not None
    assert result.shipment.weight_g == 760
    assert result.packaging_proposal is not None
    assert result.packaging_proposal.normal.to_dict() == result.packaging_proposal.conservative.to_dict() | {"label": "AI估算"}
    sent_text = captured["body"]["messages"][0]["content"]
    assert "user_correction" in sent_text
    assert "image_url" not in sent_text
    assert "actual_first_mile" not in sent_text
    assert "CAL-001" not in sent_text
    assert '"shipment"' in sent_text
    assert "response_format" not in captured["body"]


def test_corrected_reestimate_timeout_reports_current_result_preserved(monkeypatch):
    class Profile:
        api_url = "https://example.invalid"
        model_name = "text-model"
        provider = "自定义"

    class Store:
        @staticmethod
        def bound_profile(_purpose):
            return Profile(), "secret"

    monkeypatch.setattr(
        "profit_accounting_26.application.local_reestimate_service.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()),
    )
    with pytest.raises(RecognitionUnavailableError, match="当前结果未改变"):
        LocalReestimateService(Store()).reestimate(**_context())
