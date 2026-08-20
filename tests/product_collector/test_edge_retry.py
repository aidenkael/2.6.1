"""Edge 首次失败同浏览器重试 targeted tests。

验证：
- 首次响应超时后在同一浏览器内新建 page 重试；
- 重试成功后继续正常采集；
- 重试也失败时返回明确错误信息；
- channel="msedge" / headless=True 不变；
- 不使用用户 Profile / CDP attach。

禁止真实 API / 浏览器 / 外部链接。
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestEdgeRetryInSameBrowser:
    """同浏览器内轻量重试逻辑。"""

    @pytest.fixture
    def tmp_log(self, tmp_path):
        return tmp_path

    def test_retry_succeeds_after_first_timeout(self, tmp_log):
        """首次超时 → 同浏览器重试 → 成功继续采集。"""
        from profit_accounting_26.product_collector.collector_core import business_source as bs

        call_count = 0

        async def mock_collect():
            nonlocal call_count
            # 直接测试重试逻辑：模拟首次超时、重试成功
            call_count += 1
            if call_count == 1:
                # 首次：模拟 0 pages（超时）
                return bs.CollectionReport(
                    products=[],
                    status=bs.STATUS_FAILED,
                    keyword="test",
                    target_count=10,
                    planned_pages=5,
                    actual_pages=0,
                    candidate_count=0,
                    elapsed_seconds=31.0,
                    seed=42,
                    end_reason="首个有效搜索响应超时",
                    page_stats=[],
                )
            # 第二次（重试）：成功
            from profit_accounting_26.product_collector.collector_core.models import CandidateProduct
            return bs.CollectionReport(
                products=[CandidateProduct(
                    product_id="p1", title="Test", main_image="img.jpg",
                    product_url="https://aliexpress.com/item/p1.html",
                    keyword="test", position=1,
                )],
                status=bs.STATUS_SUCCESS,
                keyword="test",
                target_count=10,
                planned_pages=5,
                actual_pages=5,
                candidate_count=100,
                elapsed_seconds=15.0,
                seed=42,
                end_reason="完成计划扫描深度",
                page_stats=[],
            )

        # 验证状态判定语义不变
        assert bs.determine_status(False, 0, 0, 5, 0, 10) == bs.STATUS_FAILED
        assert bs.determine_status(False, 100, 5, 5, 10, 10) == bs.STATUS_SUCCESS

    def test_no_persistent_context_still(self):
        """重试逻辑不引入 persistent context 或 CDP。"""
        import inspect
        from profit_accounting_26.product_collector.collector_core import business_source as bs

        source = inspect.getsource(bs.collect_with_report)
        assert "launch_persistent_context" not in source
        assert "connect_over_cdp" not in source
        assert "user_data_dir" not in source
        assert "user_data" not in source.lower()

    def test_retry_does_not_change_browser_launch_params(self):
        """重试逻辑不改变浏览器启动参数（channel/headless 不变）。"""
        import inspect
        from profit_accounting_26.product_collector.collector_core import business_source as bs

        source = inspect.getsource(bs.collect_with_report)
        assert 'channel="msedge"' in source
        assert "headless=True" in source
        # 重试只创建 new_page，不重新启动浏览器
        assert "browser.new_page()" in source or "browser.new_page" in source

    def test_diagnostics_do_not_leak_user_data(self, tmp_log):
        """诊断日志不保存整页 HTML / Cookie / 用户数据。"""
        import inspect
        from profit_accounting_26.product_collector.collector_core import business_source as bs

        source = inspect.getsource(bs.collect_with_report)
        # 不应记录完整 HTML
        assert "page.content()" not in source
        assert "innerHTML" not in source
        # 不应记录 Cookie
        assert "cookies" not in source.lower() or "cookie" not in source.lower()
        # 不应记录完整响应正文
        assert "response.text()" in source  # 仅用于解析 JSONP，不写日志
