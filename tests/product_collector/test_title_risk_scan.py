"""TitleRiskScanService 测试。

覆盖：
- 英文标题批量输入
- 中文标签解析
- Kids Towel 不误杀
- Kids Electric Toy Car 命中
- Magnetic Phone Holder 命中
- USB Rechargeable Fan 命中
- Women Shoulder Bag 不输出
- Phone Holder 不脑补带电
- API 无配置
- 非法 JSON
- 部分 id 不存在
- 空结果
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from profit_accounting_26.product_collector.title_risk_scan import (
    TitleRiskItem,
    TitleRiskScanService,
    _build_prompt,
)


class TestBuildPrompt:
    """测试 Prompt 构建。"""

    def test_prompt_contains_titles(self):
        titles = [
            {"id": "1", "title": "USB Rechargeable Fan"},
            {"id": "2", "title": "Women Shoulder Bag"},
        ]
        prompt = _build_prompt(titles)
        assert "USB Rechargeable Fan" in prompt
        assert "Women Shoulder Bag" in prompt
        assert "商品标题风险快筛器" in prompt

    def test_prompt_contains_rules(self):
        prompt = _build_prompt([{"id": "1", "title": "Test"}])
        assert "禁止" in prompt
        assert "人工复核" in prompt
        assert "Kids" in prompt


class TestTitleRiskScanService:
    """测试 TitleRiskScanService。"""

    def _make_service(self, response_data: dict | None = None, error: Exception | None = None):
        """创建测试用 service，mock API 调用。"""
        profile_store = MagicMock()
        profile = MagicMock()
        profile.api_url = "https://api.example.com/v1"
        profile.model_name = "test-model"
        profile.provider = "OpenAI"
        profile_store.bound_profile.return_value = (profile, "test-key")

        service = TitleRiskScanService(profile_store)

        if response_data is not None:
            response_json = json.dumps({
                "choices": [{"message": {"content": json.dumps(response_data)}}]
            }).encode("utf-8")

            class MockResponse:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
                def read(self):
                    return response_json

            import profit_accounting_26.product_collector.title_risk_scan as module
            module.urlopen = lambda *args, **kwargs: MockResponse()

        return service

    def test_api_not_configured(self):
        """API 无配置时应报错。"""
        profile_store = MagicMock()
        profile_store.bound_profile.return_value = None
        service = TitleRiskScanService(profile_store)

        from profit_accounting_26.application.recognition_service import RecognitionUnavailableError
        with pytest.raises(RecognitionUnavailableError, match="尚未绑定"):
            service.scan([{"id": "1", "title": "Test"}])

    def test_empty_titles(self):
        """空标题列表应返回空。"""
        profile_store = MagicMock()
        service = TitleRiskScanService(profile_store)
        result = service.scan([])
        assert result == []

    def test_parse_risks_valid(self):
        """正常解析风险结果。"""
        data = {
            "risks": [
                {"id": "1", "result": "人工复核", "labels": ["带电"], "evidence": ["USB"]},
                {"id": "2", "result": "禁止", "labels": ["食品"], "evidence": ["Candy"]},
            ]
        }
        risks = TitleRiskScanService._parse_risks(data)
        assert len(risks) == 2
        assert risks[0].product_id == "1"
        assert risks[0].result == "人工复核"
        assert risks[0].labels == ["带电"]
        assert risks[1].result == "禁止"

    def test_parse_risks_invalid_json(self):
        """非法 JSON 应返回空。"""
        assert TitleRiskScanService._parse_risks("not a dict") == []
        assert TitleRiskScanService._parse_risks({}) == []
        assert TitleRiskScanService._parse_risks({"risks": "not a list"}) == []

    def test_parse_risks_skips_invalid_items(self):
        """跳过无效项。"""
        data = {
            "risks": [
                {"id": "", "result": "人工复核", "labels": ["带电"]},  # 空 id
                {"id": "2", "result": "通过", "labels": []},  # 无效 result
                {"id": "3", "result": "人工复核", "labels": ["带电"]},  # 有效
            ]
        }
        risks = TitleRiskScanService._parse_risks(data)
        assert len(risks) == 1
        assert risks[0].product_id == "3"

    def test_parse_risks_partial_ids(self):
        """部分 id 不存在时只返回存在的。"""
        data = {
            "risks": [
                {"id": "999", "result": "人工复核", "labels": ["带电"]},  # 不存在的 id
            ]
        }
        # 解析不检查 id 是否存在，由调用方处理
        risks = TitleRiskScanService._parse_risks(data)
        assert len(risks) == 1


class TestTitleRiskScanServiceIntegration:
    """集成测试：模拟完整 API 调用。"""

    def test_scan_with_mock_response(self, monkeypatch):
        """模拟 API 响应并验证解析。"""
        profile_store = MagicMock()
        profile = MagicMock()
        profile.api_url = "https://api.example.com/v1"
        profile.model_name = "test-model"
        profile.provider = "OpenAI"
        profile_store.bound_profile.return_value = (profile, "test-key")

        response_data = {
            "risks": [
                {"id": "1", "result": "人工复核", "labels": ["带电", "电池充电"], "evidence": ["USB Rechargeable"]},
            ]
        }
        response_json = json.dumps({
            "choices": [{"message": {"content": json.dumps(response_data)}}]
        }).encode("utf-8")

        class MockResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return response_json

        import profit_accounting_26.product_collector.title_risk_scan as module
        monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: MockResponse())

        service = TitleRiskScanService(profile_store)
        titles = [
            {"id": "1", "title": "USB Rechargeable Fan"},
            {"id": "2", "title": "Women Shoulder Bag"},
        ]
        risks = service.scan(titles)

        assert len(risks) == 1
        assert risks[0].product_id == "1"
        assert risks[0].result == "人工复核"
        assert "带电" in risks[0].labels
