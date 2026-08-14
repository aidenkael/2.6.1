"""TitleRiskScanService 测试。

覆盖：
- 英文标题批量输入
- 新 3 档风险解析（none/platform/infringement）
- 旧"禁止"/"人工复核"不再作为有效输出
- Kids Towel 不误杀
- USB Rechargeable Fan 命中
- API 无配置
- 非法 JSON
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

    def test_prompt_contains_new_risk_levels(self):
        prompt = _build_prompt([{"id": "1", "title": "Test"}])
        assert "platform" in prompt
        assert "infringement" in prompt
        assert "none" in prompt

    def test_prompt_contains_kids_rule(self):
        prompt = _build_prompt([{"id": "1", "title": "Test"}])
        assert "Kids" in prompt
        assert "none" in prompt


class TestTitleRiskScanService:
    """测试 TitleRiskScanService。"""

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
            "results": [
                {"id": "1", "risk": "platform", "reason": "USB充电风扇"},
                {"id": "2", "risk": "none", "reason": ""},
                {"id": "3", "risk": "infringement", "reason": "Nike品牌商标"},
            ]
        }
        risks = TitleRiskScanService._parse_risks(data)
        assert len(risks) == 3
        assert risks[0].product_id == "1"
        assert risks[0].risk == "platform"
        assert risks[1].risk == "none"
        assert risks[2].risk == "infringement"
        assert risks[2].reason == "Nike品牌商标"

    def test_parse_risks_unknown_risk_skipped(self):
        """未知/非法风险值应跳过该条目，不生成 none。"""
        data = {
            "results": [
                {"id": "1", "risk": "unknown_value", "reason": ""},  # 跳过
                {"id": "2", "risk": "platform", "reason": "ok"},
            ]
        }
        risks = TitleRiskScanService._parse_risks(data)
        assert len(risks) == 1
        assert risks[0].product_id == "2"
        assert risks[0].risk == "platform"

    def test_parse_risks_old_format_returns_empty(self):
        """旧"禁止"/"人工复核"格式不再作为有效输出。"""
        data = {
            "risks": [
                {"id": "1", "result": "人工复核", "labels": ["带电"]},
                {"id": "2", "result": "禁止", "labels": ["食品"]},
            ]
        }
        risks = TitleRiskScanService._parse_risks(data)
        assert risks == []

    def test_parse_risks_invalid_json(self):
        """非法 JSON 应返回空。"""
        assert TitleRiskScanService._parse_risks("not a dict") == []
        assert TitleRiskScanService._parse_risks({}) == []
        assert TitleRiskScanService._parse_risks({"results": "not a list"}) == []

    def test_parse_risks_skips_invalid_items(self):
        """跳过无效项。"""
        data = {
            "results": [
                {"id": "", "risk": "platform", "reason": ""},  # 空 id
                {"id": "2", "risk": "platform", "reason": "ok"},  # 有效
                None,  # 非 dict
            ]
        }
        risks = TitleRiskScanService._parse_risks(data)
        assert len(risks) == 1
        assert risks[0].product_id == "2"


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
            "results": [
                {"id": "1", "risk": "platform", "reason": "USB充电风扇，平台禁售"},
                {"id": "2", "risk": "none", "reason": ""},
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

        assert len(risks) == 2
        assert risks[0].product_id == "1"
        assert risks[0].risk == "platform"
        assert risks[1].product_id == "2"
        assert risks[1].risk == "none"
