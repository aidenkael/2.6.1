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


class TestPromptContractV3:
    """V3 标题 Prompt contract 测试。

    只验证 Prompt contract 与解析器，不做假 AI 准确率测试。
    """

    def test_prompt_version_is_v3(self):
        """标题 PROMPT_VERSION 必须为 v3。"""
        import profit_accounting_26.product_collector.title_risk_scan as module
        assert module.PROMPT_VERSION == "product-collector-title-risk-v3"
        assert TitleRiskScanService.PROMPT_VERSION == "product-collector-title-risk-v3"

    def test_prompt_keeps_full_context_rule(self):
        """标题 Prompt 保留完整上下文判断规则。"""
        prompt = _build_prompt([{"id": "1", "title": "Test"}])
        assert "完整上下文" in prompt
        assert "机械触发" in prompt
        assert "模糊情况返回 none" in prompt

    def test_prompt_halloween_skeleton_not_auto_risk(self):
        """标题 Prompt 明确 Halloween skeleton 不自动风险。"""
        prompt = _build_prompt([{"id": "1", "title": "Test"}])
        assert "Halloween skeleton decoration -> none" in prompt
        assert "Kids storage bag -> none" in prompt

    def test_prompt_88cm_and_model_88_not_auto_risk(self):
        """标题 Prompt 明确 88cm / 型号 88 不自动风险。"""
        prompt = _build_prompt([{"id": "1", "title": "Test"}])
        assert "88cm curtain -> none" in prompt
        assert "model 88 -> none" in prompt

    def test_prompt_contains_new_risk_families(self):
        """标题 Prompt 补入成人 / 政治 / 宗教 / 仇恨 / 暴力语义。"""
        prompt = _build_prompt([{"id": "1", "title": "Test"}])
        assert "成人色情" in prompt
        assert "政治人物" in prompt
        assert "宗教人物" in prompt
        assert "仇恨" in prompt
        assert "暴力" in prompt
        assert "自残" in prompt

    def test_prompt_contains_religious_building(self):
        """标题 Prompt 明确宗教建筑（mosque / church / temple）。"""
        prompt = _build_prompt([{"id": "1", "title": "Test"}])
        assert "明确宗教建筑" in prompt
        assert "mosque" in prompt
        assert "church" in prompt
        assert "temple" in prompt
        assert "普通建筑不能靠猜测判断宗教" in prompt
        assert "Cross、Star 等单独词语不自动判宗教" in prompt
        assert "证据不足 -> none" in prompt

    def test_prompt_collect_exclusion_uses_platform_and_prefix(self):
        """用户采集排除项仍输出 platform，reason 标记采集规则排除。"""
        prompt = _build_prompt([{"id": "1", "title": "Test"}])
        assert "用户内部采集排除项（platform" in prompt
        assert "采集规则排除｜" in prompt

    def test_prompt_contains_reason_prefixes(self):
        """reason 三种前缀存在。"""
        prompt = _build_prompt([{"id": "1", "title": "Test"}])
        assert "SHEIN规则风险｜" in prompt
        assert "采集规则排除｜" in prompt
        assert "侵权风险｜" in prompt

    def test_prompt_risk_enum_still_three(self):
        """标题风险枚举仍只有 none/platform/infringement，无第四档。"""
        prompt = _build_prompt([{"id": "1", "title": "Test"}])
        assert "none | platform | infringement" in prompt
        lowered = prompt.lower()
        assert "review" not in lowered
        assert "confidence" not in lowered


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

    def test_scan_logs_success_missing_by_unique_expected_ids(self, monkeypatch, tmp_path):
        """任务 5：重复 id / 未知 id 时 success/missing 按实际送检 id 集合统计。"""
        from profit_accounting_26.product_collector import product_risk_log as prl

        for handler in list(prl._logger.handlers):
            prl._logger.removeHandler(handler)
            handler.close()
        log_path = prl.configure(tmp_path)
        try:
            profile_store = MagicMock()
            profile = MagicMock()
            profile.api_url = "https://api.example.com/v1"
            profile.model_name = "test-model"
            profile.provider = "OpenAI"
            profile_store.bound_profile.return_value = (profile, "test-key")

            # AI 返回：id=1 重复两次 + id=999（未知 id）
            response_data = {
                "results": [
                    {"id": "1", "risk": "platform", "reason": "带电"},
                    {"id": "1", "risk": "infringement", "reason": "重复 id"},
                    {"id": "999", "risk": "platform", "reason": "未知 id"},
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
            titles = [{"id": "1", "title": "A"}, {"id": "2", "title": "B"}]
            risks = service.scan(titles)

            # 业务结果不变：仍返回解析出的有效条目
            assert len(risks) == 3
            content = log_path.read_text(encoding="utf-8")
            # 有效返回 id 唯一集合 = {"1"} -> success=1；expected {"1","2"} -> missing=1
            assert "success=1 missing=1" in content
        finally:
            for handler in list(prl._logger.handlers):
                prl._logger.removeHandler(handler)
                handler.close()
