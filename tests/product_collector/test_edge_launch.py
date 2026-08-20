"""Edge 浏览器启动层 targeted tests（任务书十七~二十五节）。

本轮只修改浏览器启动层（pw.chromium.launch → channel="msedge"），
绝对不修改采集业务逻辑（搜索 URL / API marker / JSONP 解析 / 随机页数 /
planned_pages_for / random.sample / seed / 翻页 / 滚动 / 超时 / 候选池 /
去重 / final_sample / success/partial/failed 判定）。

覆盖：
- 源码使用 channel="msedge"，不写死路径/版本号；
- 不使用 launch_persistent_context / connect_over_cdp / 用户 User Data；
- Edge 缺失（launch 抛异常）→ graceful failed：
  status=failed、end_reason=“未检测到 Microsoft Edge，无法启动商品采集。”、
  正常写日志、不崩溃（UU护航 不受影响）；
- CollectionReport 语义不变（success/partial/failed 判定仍走原逻辑）。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from profit_accounting_26.product_collector.collector_core import business_source as bs


def _source_text() -> str:
    return Path(bs.__file__).read_text(encoding="utf-8")


class TestEdgeLaunchSource:
    def test_launch_uses_msedge_channel(self):
        """启动层使用系统 Edge Stable（channel='msedge'），不写死路径/版本。"""
        text = _source_text()
        assert 'channel="msedge"' in text, "浏览器启动必须使用 channel=msedge"
        assert "pw.chromium.launch(headless=True)" not in text, (
            "不得回退为裸 Chromium 启动"
        )

    def test_no_persistent_context_no_cdp_no_user_data(self):
        """禁止 persistent context / connect_over_cdp / 用户 User Data。"""
        text = _source_text()
        for forbidden in (
            "launch_persistent_context",
            "connect_over_cdp",
            "user_data_dir",
            "userDataDir",
            "Default",
            "Profile 1",
        ):
            assert forbidden not in text, f"源码不得出现 {forbidden}"

    def test_no_hardcoded_edge_path_or_version(self):
        """不写死本机 Edge 路径 / 版本号，不搜索全磁盘、不下载浏览器。"""
        text = _source_text()
        for forbidden in (
            r"msedge.exe",
            r"C:\\Program Files (x86)\\Microsoft\\Edge",
            "channel_version",
        ):
            assert forbidden not in text, f"源码不得出现 {forbidden}"


class _FakePW:
    """模拟 playwright：chromium.launch 抛“可执行文件不存在”（Edge 未安装）。"""

    class chromium:
        @staticmethod
        async def launch(**kwargs):
            raise Exception("Executable doesn't exist at .../msedge")

    def __init__(self, calls: list) -> None:
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class TestEdgeMissingGracefulFailed:
    def test_edge_missing_returns_failed_with_clear_reason(self, monkeypatch, tmp_path):
        """Edge 缺失：status=failed、明确错误信息、不崩溃、正常日志。"""
        calls: list[dict] = []

        class FakeAsyncPlaywright:
            async def __aenter__(self):
                return _FakePW(calls)

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(bs, "async_playwright", lambda: FakeAsyncPlaywright())
        report = asyncio.run(
            bs.collect_with_report("phone case", target_count=10, seed=42, log_dir=tmp_path)
        )
        assert report.status == bs.STATUS_FAILED
        assert report.end_reason == "未检测到 Microsoft Edge，无法启动商品采集。"
        assert report.products == []
        assert report.planned_pages > 0
        # 正常写入日志
        logs = list(tmp_path.glob("collect_*.log"))
        assert logs, "Edge 缺失也必须写入正常日志"
        content = logs[0].read_text(encoding="utf-8")
        assert "status: failed" in content
        assert "未检测到 Microsoft Edge" in content

    def test_collection_report_semantics_unchanged(self):
        """success/partial/failed 判定语义不因 Edge 改动而变化。"""
        assert bs.STATUS_SUCCESS == "success"
        assert bs.STATUS_PARTIAL == "partial"
        assert bs.STATUS_FAILED == "failed"
        # 0 候选 → failed（与既有语义一致，不因 Edge 改动）
        assert bs.determine_status(False, 0, 0, 10, 0, 100) == bs.STATUS_FAILED
        assert bs.determine_status(False, 200, 10, 10, 100, 100) == bs.STATUS_SUCCESS

    def test_launch_call_uses_channel_msedge(self, monkeypatch, tmp_path):
        """chromium.launch 必须传 channel='msedge'（启动层唯一改动点）。"""
        captured: dict = {}

        class FakeLaunchChromium:
            @staticmethod
            async def launch(**kwargs):
                captured.update(kwargs)
                raise Exception("no browser")

        class FakeLaunchPW:
            class chromium:
                launch = FakeLaunchChromium.launch

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(bs, "async_playwright", lambda: FakeLaunchPW())
        asyncio.run(
            bs.collect_with_report("phone case", target_count=5, seed=42, log_dir=tmp_path)
        )
        assert captured.get("channel") == "msedge"
        assert captured.get("headless") is True
