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
        """重复 id / 未知 id：只接受本批 expected_ids，同 id 只计一次，unknown 不加入结果。"""
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

            # 只保留属于本批的唯一有效结果：id=1 一次；重复与未知 id 被过滤
            assert len(risks) == 1
            assert risks[0].product_id == "1"
            assert risks[0].risk == "platform"
            content = log_path.read_text(encoding="utf-8")
            # 有效返回 id 唯一集合 = {"1"} -> success=1；expected {"1","2"} -> missing=1
            assert "success=1 missing=1" in content
            # 结构诊断：重复 1 条、未知 1 条
            assert "unknown_id_count=1" in content
            assert "duplicate_id_count=1" in content
        finally:
            for handler in list(prl._logger.handlers):
                prl._logger.removeHandler(handler)
                handler.close()


class TestTitleBatching:
    """A 项：标题 20/批 分批顺序执行、单批失败隔离、取消、on_batch。"""

    @staticmethod
    def _service_with_failures(monkeypatch, fail_batches=(), partial_batch_return=None):
        """构造可注入失败的 service。

        fail_batches: 第几批抛 HTTP 400（如 {3}）。
        partial_batch_return: {批次号: 该批返回的 id 集合}，缺省 id 视为缺失失败。
        返回 (service, batch_sizes, call_count)。
        """
        from urllib.error import HTTPError

        profile_store = MagicMock()
        profile = MagicMock()
        profile.api_url = "https://api.example.com/v1"
        profile.model_name = "test-model"
        profile.provider = "OpenAI"
        profile_store.bound_profile.return_value = (profile, "test-key")

        import profit_accounting_26.product_collector.title_risk_scan as module

        call_count = [0]
        batch_sizes = []

        def fake_urlopen(request, *args, **kwargs):
            call_count[0] += 1
            batch_no = call_count[0]
            body = json.loads(request.data.decode("utf-8"))
            content = body["messages"][0]["content"]
            idx = content.rindex("[")
            items = json.loads(content[idx:])
            batch_sizes.append(len(items))
            if batch_no in fail_batches:
                raise HTTPError("http://x", 400, "Bad Request", None, None)
            if partial_batch_return is not None and batch_no in partial_batch_return:
                keep_ids = partial_batch_return[batch_no]
                items = [it for it in items if it["id"] in keep_ids]
            results = [{"id": it["id"], "risk": "none", "reason": ""} for it in items]
            response_json = json.dumps({
                "choices": [{"message": {"content": json.dumps({"results": results})}}]
            }).encode("utf-8")

            class MockResponse:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def read(self):
                    return response_json

            return MockResponse()

        monkeypatch.setattr(module, "urlopen", fake_urlopen)
        return TitleRiskScanService(profile_store), batch_sizes, call_count

    @pytest.mark.parametrize("count,expected_batches", [
        (0, 0), (1, 1), (19, 1), (20, 1), (21, 2),
        (40, 2), (41, 3), (90, 5), (100, 5),
    ])
    def test_split(self, monkeypatch, count, expected_batches):
        """分批数量符合预期，每批 <= 20，无空批次。"""
        service, batch_sizes, call_count = self._service_with_failures(monkeypatch)
        titles = [{"id": str(i), "title": f"商品{i}"} for i in range(1, count + 1)]
        results = service.scan(titles)
        assert len(batch_sizes) == expected_batches
        assert all(size <= 20 for size in batch_sizes)
        if count == 0:
            # 0 个不发 API
            assert call_count[0] == 0
            assert results == []
        else:
            assert len(results) == count
            assert sum(batch_sizes) == count

    def test_middle_batch_failure_continues(self, monkeypatch):
        """批3 HTTP 400：前后批次结果保留，批4/批5 仍继续。"""
        service, batch_sizes, call_count = self._service_with_failures(monkeypatch, fail_batches={3})
        titles = [{"id": str(i), "title": f"商品{i}"} for i in range(1, 101)]  # 5 批
        risks = service.scan(titles)
        assert call_count[0] == 5
        assert len(batch_sizes) == 5
        assert len(risks) == 80  # 4 批成功
        returned = {r.product_id for r in risks}
        assert "1" in returned and "100" in returned
        # 批3 的 id（41-60）缺失，不强行置 none
        assert not returned & {str(i) for i in range(41, 61)}

    def test_first_batch_failure_continues(self, monkeypatch):
        """批1 失败：后续批次仍继续。"""
        service, _, call_count = self._service_with_failures(monkeypatch, fail_batches={1})
        titles = [{"id": str(i), "title": f"商品{i}"} for i in range(1, 41)]  # 2 批
        risks = service.scan(titles)
        assert call_count[0] == 2
        assert len(risks) == 20
        returned = {r.product_id for r in risks}
        assert not returned & {str(i) for i in range(1, 21)}
        assert "21" in returned

    def test_last_batch_failure_keeps_earlier(self, monkeypatch):
        """最后一批失败：前面批次结果保留。"""
        service, _, call_count = self._service_with_failures(monkeypatch, fail_batches={5})
        titles = [{"id": str(i), "title": f"商品{i}"} for i in range(1, 91)]  # 5 批
        risks = service.scan(titles)
        assert call_count[0] == 5
        assert len(risks) == 80
        returned = {r.product_id for r in risks}
        assert "1" in returned
        assert not returned & {str(i) for i in range(81, 91)}

    def test_all_batches_fail_returns_empty(self, monkeypatch):
        """全部批次失败：返回空列表，不抛错。"""
        service, _, call_count = self._service_with_failures(
            monkeypatch, fail_batches={1, 2, 3, 4, 5})
        titles = [{"id": str(i), "title": f"商品{i}"} for i in range(1, 91)]
        risks = service.scan(titles)
        assert call_count[0] == 5
        assert risks == []

    def test_missing_ids_only_failed(self, monkeypatch):
        """某批返回缺少部分 ID：只把缺失的算失败，已返回的仍应用。"""
        service, _, _ = self._service_with_failures(
            monkeypatch, partial_batch_return={2: {"21", "22", "23", "24", "25"}})
        titles = [{"id": str(i), "title": f"商品{i}"} for i in range(1, 41)]  # 2 批
        risks = service.scan(titles)
        assert len(risks) == 25  # 批1 20 + 批2 5
        returned = {r.product_id for r in risks}
        assert "1" in returned and "21" in returned
        assert "26" not in returned  # 批2 缺失 15 个

    def test_on_batch_callback(self, monkeypatch):
        """on_batch 每批调用一次，携带 (results, failed, batch_index, total_batches, elapsed_ms)。"""
        service, _, _ = self._service_with_failures(monkeypatch)
        titles = [{"id": str(i), "title": f"商品{i}"} for i in range(1, 91)]  # 5 批
        calls = []
        service.scan(titles, on_batch=lambda *a: calls.append(a))
        assert len(calls) == 5
        assert calls[0][2] == 1 and calls[0][3] == 5
        assert calls[-1][2] == 5 and calls[-1][3] == 5
        assert all(c[1] == 0 for c in calls)  # 无失败
        assert all(c[4] >= 0 for c in calls)  # elapsed_ms 非负（mock 极快可能为 0）
        assert all(len(c[0]) == 20 for c in calls[:4])
        assert len(calls[-1][0]) == 10

    def test_cancel_stops_future_batches(self, monkeypatch):
        """cancel 后不再发送后续批次，已完成批次结果保留。"""
        service, _, call_count = self._service_with_failures(monkeypatch)
        titles = [{"id": str(i), "title": f"商品{i}"} for i in range(1, 41)]  # 2 批

        def cancel_check():
            return call_count[0] >= 1  # 第一批执行完后取消

        risks = service.scan(titles, cancel_requested=cancel_check)
        assert call_count[0] == 1
        assert len(risks) == 20
        returned = {r.product_id for r in risks}
        assert "1" in returned and "20" in returned

    def test_cancel_logs_actual_batch_count(self, monkeypatch, tmp_path):
        """取消时专用日志批次数 = 实际执行批次数（不是计划批次数）。"""
        from profit_accounting_26.product_collector import product_risk_log as prl

        for handler in list(prl._logger.handlers):
            prl._logger.removeHandler(handler)
            handler.close()
        log_path = prl.configure(tmp_path)
        try:
            service, _, call_count = self._service_with_failures(monkeypatch)
            titles = [{"id": str(i), "title": f"商品{i}"} for i in range(1, 101)]  # 计划 5 批

            def cancel_after_two():
                return call_count[0] >= 2  # 执行 2 批后取消

            risks = service.scan(titles, cancel_requested=cancel_after_two)
            assert call_count[0] == 2
            content = log_path.read_text(encoding="utf-8")
            assert "批次数=2" in content
            assert "status=取消" in content
            assert "批次3开始" not in content
        finally:
            for handler in list(prl._logger.handlers):
                prl._logger.removeHandler(handler)
                handler.close()


class TestQwen37JsonMode:
    """阿里云百炼 qwen3.7-plus 标题检测启用 JSON Mode（其余 provider / 模型不变）。"""

    @staticmethod
    def _request_body(monkeypatch, provider, model_name):
        """构造一次单商品 scan，返回实际发送的请求体。"""
        profile_store = MagicMock()
        profile = MagicMock()
        profile.api_url = "https://api.example.com/v1"
        profile.model_name = model_name
        profile.provider = provider
        profile_store.bound_profile.return_value = (profile, "test-key")

        captured = []

        def fake_urlopen(request, *args, **kwargs):
            captured.append(json.loads(request.data.decode("utf-8")))
            response_json = json.dumps({
                "choices": [{"message": {"content": json.dumps({"results": [
                    {"id": "1", "risk": "none", "reason": ""}]})}}]
            }).encode("utf-8")

            class MockResponse:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def read(self):
                    return response_json

            return MockResponse()

        import profit_accounting_26.product_collector.title_risk_scan as module
        monkeypatch.setattr(module, "urlopen", fake_urlopen)
        service = TitleRiskScanService(profile_store)
        service.scan([{"id": "1", "title": "A"}])
        assert captured
        return captured[0]

    def test_bailian_qwen37_plus_sends_json_object(self, monkeypatch):
        """百炼 + qwen3.7-plus：请求包含 json_object response_format。"""
        body = self._request_body(monkeypatch, "阿里云百炼", "qwen3.7-plus-0119")
        assert body["response_format"] == {"type": "json_object"}

    def test_bailian_other_model_unchanged(self, monkeypatch):
        """百炼 + 非 qwen3.7-plus 模型：不发送 response_format。"""
        body = self._request_body(monkeypatch, "阿里云百炼", "qwen3.5-max")
        assert "response_format" not in body

    def test_openai_behavior_unchanged(self, monkeypatch):
        """OpenAI 原有行为保持不变：仍发送 json_object。"""
        body = self._request_body(monkeypatch, "OpenAI", "gpt-4o-mini")
        assert body["response_format"] == {"type": "json_object"}

    def test_other_provider_unchanged(self, monkeypatch):
        """其它 provider：不发送 response_format。"""
        body = self._request_body(monkeypatch, "DeepSeek", "deepseek-chat")
        assert "response_format" not in body


class TestReturnStructureDiagnostics:
    """返回结构诊断与有效结果统计（本批归属 / 去重 / unknown 过滤）。"""

    @staticmethod
    def _run_scan(monkeypatch, tmp_path, response_results, total=20):
        """执行一次单批 scan，返回 (risks, log_text, on_batch_calls)。"""
        import profit_accounting_26.product_collector.title_risk_scan as module
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

            response_json = json.dumps({
                "choices": [{
                    "message": {"content": json.dumps({"results": response_results})},
                    "finish_reason": "stop",
                }]
            }).encode("utf-8")

            class MockResponse:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def read(self):
                    return response_json

            monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: MockResponse())
            service = TitleRiskScanService(profile_store)
            calls = []
            titles = [{"id": str(i), "title": f"商品{i}"} for i in range(1, total + 1)]
            risks = service.scan(titles, on_batch=lambda *a: calls.append(a))
            log_text = log_path.read_text(encoding="utf-8")
            return risks, log_text, calls
        finally:
            for handler in list(prl._logger.handlers):
                prl._logger.removeHandler(handler)
                handler.close()

    def test_diagnostics_logged_for_normal_batch(self, monkeypatch, tmp_path):
        """全部正常：诊断记录完整字段，全部计数为 0。"""
        results = [{"id": str(i), "risk": "none", "reason": ""} for i in range(1, 21)]
        risks, log_text, calls = self._run_scan(monkeypatch, tmp_path, results)
        assert len(risks) == 20
        assert calls[0][1] == 0
        assert (
            "批次1诊断 finish_reason=stop" in log_text
            and "results_is_list=True raw_results_count=20 valid_count=20" in log_text
            and "missing_id_count=0 invalid_risk_count=0 unknown_id_count=0 duplicate_id_count=0"
            in log_text
        )

    def test_diagnostics_when_results_not_list(self, monkeypatch, tmp_path):
        """results 缺失 / 非 list：记录 results_is_list=False，全部算缺失。"""
        risks, log_text, calls = self._run_scan(monkeypatch, tmp_path, {"id": "1"})
        assert risks == []
        assert calls[0][1] == 20  # 本批 20 个全部缺失
        assert (
            "results_is_list=False raw_results_count=0 valid_count=0" in log_text
            and "missing_id_count=20" in log_text
        )

    def test_unknown_id_excluded_and_counted(self, monkeypatch, tmp_path):
        """19 valid + 1 unknown -> success=19 failed=1，unknown 不加入结果。"""
        results = [{"id": str(i), "risk": "none", "reason": ""} for i in range(1, 20)]
        results.append({"id": "999", "risk": "platform", "reason": "未知 id"})
        risks, log_text, calls = self._run_scan(monkeypatch, tmp_path, results)
        returned_ids = {r.product_id for r in risks}
        assert len(risks) == 19
        assert "999" not in returned_ids
        assert len(calls[0][0]) == 19
        assert calls[0][1] == 1  # failed=1
        assert len(calls[0][0]) + calls[0][1] == 20
        assert "success=19 failed=1" in log_text  # title_batch_finished
        assert "unknown_id_count=1" in log_text
        assert "checked=19 failed=1" in log_text

    def test_invalid_risk_not_counted_as_success(self, monkeypatch, tmp_path):
        """非法 risk 不计成功，计入失败。"""
        results = [{"id": str(i), "risk": "none", "reason": ""} for i in range(2, 21)]
        results.append({"id": "1", "risk": "banned", "reason": "非法值"})
        risks, log_text, calls = self._run_scan(monkeypatch, tmp_path, results)
        assert len(risks) == 19
        assert calls[0][1] == 1
        assert "invalid_risk_count=1" in log_text
        assert "success=19 failed=1" in log_text

    def test_duplicate_id_counted_once(self, monkeypatch, tmp_path):
        """同一 id 返回两次只计一次，重复条目计入诊断。"""
        results = [{"id": str(i), "risk": "none", "reason": ""} for i in range(2, 20)]
        results.append({"id": "1", "risk": "platform", "reason": "首次"})
        results.append({"id": "1", "risk": "infringement", "reason": "重复"})
        risks, log_text, calls = self._run_scan(monkeypatch, tmp_path, results)
        # 返回 1..19（缺 20）：id=1 只计一次 -> 19 有效、1 缺失、1 重复
        assert len(risks) == 19
        assert calls[0][1] == 1
        assert "duplicate_id_count=1" in log_text
        assert "missing_id_count=1" in log_text
        assert "success=19 failed=1" in log_text

    def test_success_plus_failed_within_batch_size(self, monkeypatch, tmp_path):
        """混合场景：success + failed 不超过本批商品数。"""
        results = [{"id": str(i), "risk": "none", "reason": ""} for i in range(2, 20)]
        results.append({"id": "1", "risk": "none", "reason": ""})
        results.append({"id": "1", "risk": "none", "reason": "重复"})
        results.append({"id": "999", "risk": "none", "reason": "未知"})
        results.append({"id": "20", "risk": "banned", "reason": "非法"})
        risks, log_text, calls = self._run_scan(monkeypatch, tmp_path, results)
        success = len(calls[0][0])
        failed = calls[0][1]
        assert success + failed <= 20
        # valid = 1..19（id=1 只计一次），缺 id=20 -> missing=1
        assert success == 19
        assert failed == 1
        assert "invalid_risk_count=1" in log_text
        assert "duplicate_id_count=1" in log_text
        assert "unknown_id_count=1" in log_text

    def test_total_checked_plus_failed_within_total(self, monkeypatch, tmp_path):
        """多批混合：整体 checked + failed 不超过本次总商品数。"""
        import profit_accounting_26.product_collector.title_risk_scan as module
        from profit_accounting_26.product_collector import product_risk_log as prl
        from urllib.error import HTTPError

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

            call_count = [0]

            def fake_urlopen(request, *args, **kwargs):
                call_count[0] += 1
                batch_no = call_count[0]
                body = json.loads(request.data.decode("utf-8"))
                content = body["messages"][0]["content"]
                idx = content.rindex("[")
                items = json.loads(content[idx:])
                if batch_no == 3:
                    raise HTTPError("http://x", 400, "Bad Request", None, None)
                results = [{"id": it["id"], "risk": "none", "reason": ""} for it in items]
                if batch_no == 2:
                    # 19 valid + 1 unknown
                    results = results[:-1] + [{"id": "999", "risk": "none", "reason": ""}]
                response_json = json.dumps({
                    "choices": [{"message": {"content": json.dumps({"results": results})}}]
                }).encode("utf-8")

                class MockResponse:
                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        return False

                    def read(self):
                        return response_json

                return MockResponse()

            monkeypatch.setattr(module, "urlopen", fake_urlopen)
            service = TitleRiskScanService(profile_store)
            titles = [{"id": str(i), "title": f"商品{i}"} for i in range(1, 61)]  # 3 批
            risks = service.scan(titles)
            # 批1: 20 valid；批2: 19 valid + 1 unknown；批3: HTTP 400 -> 20 failed
            assert len(risks) == 39
            content = log_path.read_text(encoding="utf-8")
            assert "checked=39 failed=21" in content
        finally:
            for handler in list(prl._logger.handlers):
                prl._logger.removeHandler(handler)
                handler.close()
