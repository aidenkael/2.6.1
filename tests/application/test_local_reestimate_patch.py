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


# ------------------------------------------------------------------ 阶段 3 冲突优先级


def test_prompt_version_is_v1_2():
    assert LocalReestimateService.PROMPT_VERSION == "2.6.1-reestimate-v1.2"


def test_conflicting_summary_and_correction_both_sent_with_correction_priority():
    """A：摘要仍是 A，用户修正说其实是 B：两者都进 Prompt，且修正优先。"""
    prompt = LocalReestimateService._context(
        product_name="A；硬质；不可压缩",
        confirmed_facts={},
        current_shipment={"length_cm": 30, "width_cm": 20, "height_cm": 10, "weight_g": 400},
        user_correction="其实是B，可以压缩袋装",
    )
    # 两者都存在
    assert "A；硬质；不可压缩" in prompt
    assert "其实是B，可以压缩袋装" in prompt
    # Prompt 明确用户修正优先、不得因摘要旧内容忽略修正
    assert "以用户修正为准" in prompt
    assert "不得因为摘要仍是旧内容而忽略用户修正" in prompt
    # 轻量合同保持：只输出一个 shipment，不算费用/利润
    assert "只输出一个最终 shipment" in prompt
    assert "物流费用" in prompt and "利润" in prompt


def test_consistent_summary_and_correction_both_sent():
    """B：摘要与修正都写 B：作为一致证据正常发送。"""
    prompt = LocalReestimateService._context(
        product_name="B；软质；可压缩",
        confirmed_facts={},
        current_shipment={},
        user_correction="这个其实是B，可以压缩",
    )
    assert "B；软质；可压缩" in prompt
    assert "这个其实是B，可以压缩" in prompt


def test_confirmed_bare_facts_are_highest_hard_facts():
    """C：确认裸尺寸/裸重存在时，Prompt 明确结构化确认事实优先。"""
    prompt = LocalReestimateService._context(
        product_name="睡帽；软布结构；可压缩",
        confirmed_facts={"length_cm": 30, "width_cm": 25, "height_cm": 4, "weight_g": 90},
        current_shipment={},
        user_correction="压扁发货",
    )
    assert "30" in prompt and "90" in prompt
    assert "最高优先级的硬事实" in prompt
    assert "1. 用户明确确认的结构化裸尺寸/裸重" in prompt


def test_current_shipment_still_sent():
    """D：current_shipment 继续正常发送。"""
    prompt = LocalReestimateService._context(
        product_name="睡帽",
        confirmed_facts={},
        current_shipment={"length_cm": 26, "width_cm": 20, "height_cm": 6, "weight_g": 150},
        user_correction="压缩发货",
    )
    assert "current_shipment" in prompt
    assert "26" in prompt and "150" in prompt


def test_reestimate_never_rewrites_summary_contract():
    """服务合同：重估只返回一个 shipment，不得携带改写摘要/自动覆盖字段。"""
    assert LocalReestimateService.RESPONSE_SCHEMA["required"] == ["shipment", "note"]
    assert set(LocalReestimateService.RESPONSE_SCHEMA["properties"]) == {"shipment", "note"}
    prompt = LocalReestimateService._context(
        product_name="A；硬质", confirmed_facts={}, current_shipment={},
        user_correction="其实是B",
    )
    assert "不要改写或返回新的商品摘要" in prompt
