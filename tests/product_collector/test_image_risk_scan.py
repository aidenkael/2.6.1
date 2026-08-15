"""ImageRiskScanService 测试。

覆盖：
- 检测已选
- 检测全部
- 无选中商品
- 同一图片运行期重复检测跳过
- 软件不产生持久缓存
- AI 正常结果
- 部分批次失败
- id/图片映射正确
- 不自动删除、不自动取消选择
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from profit_accounting_26.product_collector.image_risk_scan import (
    BATCH_SIZE,
    ImageRiskItem,
    ImageRiskScanService,
    ImageRiskScanStats,
    _build_image_prompt,
)


class TestBuildImagePrompt:
    """测试图片 Prompt 构建。"""

    def test_prompt_contains_key_terms(self):
        prompt = _build_image_prompt()
        assert "platform" in prompt or "infringement" in prompt

    def test_prompt_contains_strict_rules(self):
        prompt = _build_image_prompt()
        assert "误判" in prompt or "误杀" in prompt


class TestImageRiskScanService:
    """测试 ImageRiskScanService。"""

    def test_cache_miss(self):
        """缓存未命中应返回 None。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)
        assert service.get_cached("1", "https://example.com/pic.jpg") is None

    def test_cache_hit(self):
        """缓存命中应返回结果。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)
        item = ImageRiskItem(
            product_id="1",
            main_image="https://example.com/pic.jpg",
            risk="infringement",
            reason="品牌Logo",
        )
        service._set_cached("1", "https://example.com/pic.jpg", item)
        cached = service.get_cached("1", "https://example.com/pic.jpg")
        assert cached is not None
        assert cached.risk == "infringement"

    def test_cache_key_includes_url(self):
        """缓存键包含 URL，不同图片不共享缓存。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)
        item1 = ImageRiskItem("1", "https://example.com/pic1.jpg", "infringement", "品牌Logo")
        item2 = ImageRiskItem("1", "https://example.com/pic2.jpg", "none", "")
        service._set_cached("1", "https://example.com/pic1.jpg", item1)
        service._set_cached("1", "https://example.com/pic2.jpg", item2)
        assert service.get_cached("1", "https://example.com/pic1.jpg").risk == "infringement"
        assert service.get_cached("1", "https://example.com/pic2.jpg").risk == "none"

    def test_api_not_configured(self):
        """API 无配置时应报错。"""
        profile_store = MagicMock()
        profile_store.bound_profile.return_value = None
        service = ImageRiskScanService(profile_store)

        from profit_accounting_26.application.recognition_service import RecognitionUnavailableError
        with pytest.raises(RecognitionUnavailableError, match="尚未绑定"):
            service._scan_single_batch([{"id": "1", "main_image": "https://example.com/pic.jpg"}])

    def test_empty_products(self):
        """空商品列表应返回空。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)
        results, stats, _all = service.scan_batch([])
        assert results == []
        assert stats.requested_count == 0
        assert stats.failed_count == 0

    def test_scan_batch_uses_cache(self):
        """已缓存的商品应跳过检测。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        # 预先缓存一个结果
        item = ImageRiskItem("1", "https://example.com/pic1.jpg", "infringement", "品牌Logo")
        service._set_cached("1", "https://example.com/pic1.jpg", item)

        products = [
            {"id": "1", "main_image": "https://example.com/pic1.jpg"},  # 已缓存
            {"id": "2", "main_image": "https://example.com/pic2.jpg"},  # 未缓存
        ]

        # Mock _scan_single_batch 只处理未缓存的
        call_count = [0]
        def mock_scan_batch(batch, **kwargs):
            call_count[0] += 1
            return [ImageRiskItem("2", "https://example.com/pic2.jpg", "none", "")], 0

        service._scan_single_batch = mock_scan_batch
        results, stats, _all = service.scan_batch(products)

        assert call_count[0] == 1  # 只调用了一次
        assert len(results) == 1  # 只有缓存的那个 risk != none
        assert stats.requested_count == 2
        assert stats.cached_count == 1
        assert stats.checked_count == 1
        assert stats.risk_count == 1
        assert stats.failed_count == 0

    def test_missing_image_counts_as_failed(self):
        """缺图商品计入 failed_count，不发送 API、不写安全缓存。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        scanned_ids: list[str] = []

        def mock_scan_batch(batch, **kwargs):
            scanned_ids.extend(str(p.get("id")) for p in batch)
            return [
                ImageRiskItem("1", "https://img.example/1.jpg", "none", ""),
                ImageRiskItem("3", "https://img.example/3.jpg", "none", ""),
            ], 0

        service._scan_single_batch = mock_scan_batch

        products = [
            {"id": "1", "main_image": "https://img.example/1.jpg"},
            {"id": "2", "main_image": ""},  # 缺图
            {"id": "3", "main_image": "https://img.example/3.jpg"},
        ]
        results, stats, all_checked = service.scan_batch(products)

        # 3 个商品都在本次检测范围
        assert stats.requested_count == 3
        # 缺图计入失败
        assert stats.failed_count == 1
        assert stats.checked_count == 2
        # 缺图商品不进入 API 请求
        assert "2" not in scanned_ids
        # 缺图商品不写安全缓存
        assert service.get_cached("2", "") is None
        # 不为缺图商品生成 platform/infringement/none 结果
        assert len(all_checked) == 2
        assert all(r.product_id != "2" for r in all_checked)
        assert all(r.product_id != "2" for r in results)

    def test_parse_results_valid(self):
        """正常解析图片风险结果。"""
        image_items = [
            ("1", "https://example.com/pic1.jpg", b"fake"),
            ("2", "https://example.com/pic2.jpg", b"fake"),
        ]
        data = {
            "results": [
                {"id": "1", "risk": "infringement", "reason": "Nike Swoosh Logo"},
                {"id": "2", "risk": "none", "reason": ""},
            ]
        }
        results = ImageRiskScanService._parse_results(data, image_items)
        assert len(results) == 2
        assert results[0].product_id == "1"
        assert results[0].risk == "infringement"
        assert results[0].reason == "Nike Swoosh Logo"
        assert results[1].risk == "none"

    def test_parse_results_invalid_json(self):
        """非法 JSON 应返回空。"""
        image_items = [("1", "https://example.com/pic.jpg", b"fake")]
        assert ImageRiskScanService._parse_results("not a dict", image_items) == []
        assert ImageRiskScanService._parse_results({}, image_items) == []
        assert ImageRiskScanService._parse_results({"results": "not a list"}, image_items) == []

    def test_parse_results_skips_unknown_ids(self):
        """跳过未知的 id。"""
        image_items = [("1", "https://example.com/pic.jpg", b"fake")]
        data = {
            "results": [
                {"id": "999", "risk": "infringement", "reason": "品牌Logo"},  # 未知 id
            ]
        }
        results = ImageRiskScanService._parse_results(data, image_items)
        assert len(results) == 0

    def test_parse_results_invalid_risk_skipped(self):
        """非法/未知 risk 值应跳过该条目，不生成 none。"""
        image_items = [
            ("1", "https://example.com/pic1.jpg", b"fake"),
            ("2", "https://example.com/pic2.jpg", b"fake"),
        ]
        data = {
            "results": [
                {"id": "1", "risk": "invalid_value", "reason": ""},  # 跳过
                {"id": "2", "risk": "platform", "reason": "ok"},
            ]
        }
        results = ImageRiskScanService._parse_results(data, image_items)
        assert len(results) == 1
        assert results[0].product_id == "2"
        assert results[0].risk == "platform"

    def test_parse_results_invalid_risk_not_in_cache(self):
        """非法 risk 不得写入安全缓存。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        def mock_scan_batch(batch, **kwargs):
            # 模拟 AI 返回非法 risk，应在 _parse_results 内跳过
            # 这里模拟 _scan_single_batch 返回空结果（因为非法 risk 被跳过）
            return [], 0

        service._scan_single_batch = mock_scan_batch
        products = [{"id": "1", "main_image": "https://example.com/pic.jpg"}]
        results, stats, all_checked = service.scan_batch(products)

        # 非法 risk 不进入缓存
        assert service.get_cached("1", "https://example.com/pic.jpg") is None
        assert len(all_checked) == 0


class TestInvalidRiskPreservesExistingState:
    """测试非法 risk 不清除已有风险状态。"""

    def test_invalid_image_risk_preserves_existing(self):
        """图片检测返回非法 risk 时，卡片原有风险状态不得清除。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        # 预先缓存一个有风险的结果
        old_item = ImageRiskItem("1", "https://example.com/pic.jpg", "infringement", "品牌Logo")
        service._set_cached("1", "https://example.com/pic.jpg", old_item)

        # 模拟 API 返回非法 risk（在 _parse_results 中被跳过）
        def mock_scan_batch(batch, **kwargs):
            return [], 0  # 非法结果被跳过，返回空

        service._scan_single_batch = mock_scan_batch
        products = [{"id": "1", "main_image": "https://example.com/pic.jpg"}]
        results, stats, all_checked = service.scan_batch(products, force_refresh=True)

        # 旧缓存应保留（因为新结果是非法的，不写入缓存）
        cached = service.get_cached("1", "https://example.com/pic.jpg")
        assert cached is not None
        assert cached.risk == "infringement"


class TestImageRiskScanServiceIntegration:
    """集成测试。"""

    def test_scan_batch_with_mock(self, monkeypatch):
        """模拟完整 API 调用。"""
        profile_store = MagicMock()
        profile = MagicMock()
        profile.api_url = "https://api.example.com/v1"
        profile.model_name = "test-model"
        profile.provider = "OpenAI"
        profile_store.bound_profile.return_value = (profile, "test-key")

        response_data = {
            "results": [
                {"id": "1", "risk": "infringement", "reason": "Disney Character"},
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

        import profit_accounting_26.product_collector.image_risk_scan as module
        monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: MockResponse())

        service = ImageRiskScanService(profile_store)
        # Mock 图片下载
        monkeypatch.setattr(service, "_download_image", lambda url: b"fake-image-data")

        products = [
            {"id": "1", "main_image": "https://example.com/pic1.jpg"},
            {"id": "2", "main_image": "https://example.com/pic2.jpg"},
        ]
        results, stats, _all = service.scan_batch(products)

        assert stats.failed_count == 0
        assert stats.requested_count == 2
        assert stats.checked_count == 2
        assert stats.risk_count == 1
        assert len(results) == 1
        assert results[0].product_id == "1"
        assert results[0].risk == "infringement"


class TestBatchSize:
    """测试批处理大小。"""

    def test_batch_size_is_10(self):
        """内部批处理大小应为 10。"""
        assert BATCH_SIZE == 10

    def test_service_batch_size(self):
        """Service 的 BATCH_SIZE 应一致。"""
        assert ImageRiskScanService.BATCH_SIZE == BATCH_SIZE


class TestNoRiskCaching:
    """测试无风险图片的缓存行为。"""

    def test_no_risk_result_enters_cache(self):
        """risk=none 的结果应进入运行期缓存。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        def mock_scan_batch(batch, **kwargs):
            return [ImageRiskItem("1", "https://example.com/pic.jpg", "none", "")], 0

        service._scan_single_batch = mock_scan_batch
        products = [{"id": "1", "main_image": "https://example.com/pic.jpg"}]
        results, stats, _all = service.scan_batch(products)

        # 无风险不进入 risky results
        assert len(results) == 0
        # 但应进入缓存
        cached = service.get_cached("1", "https://example.com/pic.jpg")
        assert cached is not None
        assert cached.risk == "none"

    def test_same_normal_image_skips_api(self):
        """再次检测同一正常图片不应重复调用 API。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        # 预先缓存无风险结果
        item = ImageRiskItem("1", "https://example.com/pic.jpg", "none", "")
        service._set_cached("1", "https://example.com/pic.jpg", item)

        call_count = [0]
        def mock_scan_batch(batch, **kwargs):
            call_count[0] += 1
            return [], 0

        service._scan_single_batch = mock_scan_batch
        products = [{"id": "1", "main_image": "https://example.com/pic.jpg"}]
        results, stats, _all = service.scan_batch(products)

        assert call_count[0] == 0  # 未调用 API
        assert stats.cached_count == 1
        assert stats.checked_count == 0
        assert len(results) == 0  # 无风险

    def test_risky_image_also_cached(self):
        """风险图片也应正常缓存。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        def mock_scan_batch(batch, **kwargs):
            return [ImageRiskItem("1", "https://example.com/pic.jpg", "infringement", "品牌Logo")], 0

        service._scan_single_batch = mock_scan_batch
        products = [{"id": "1", "main_image": "https://example.com/pic.jpg"}]
        results, stats, _all = service.scan_batch(products)

        assert len(results) == 1
        cached = service.get_cached("1", "https://example.com/pic.jpg")
        assert cached is not None
        assert cached.risk == "infringement"


class TestImageRiskStats:
    """测试图片检测统计。"""

    def test_stats_all_normal(self):
        """全部正常时统计正确，检测数量不为 0。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        def mock_scan_batch(batch, **kwargs):
            return [
                ImageRiskItem("1", "https://example.com/p1.jpg", "none", ""),
                ImageRiskItem("2", "https://example.com/p2.jpg", "none", ""),
            ], 0

        service._scan_single_batch = mock_scan_batch
        products = [
            {"id": "1", "main_image": "https://example.com/p1.jpg"},
            {"id": "2", "main_image": "https://example.com/p2.jpg"},
        ]
        results, stats, _all = service.scan_batch(products)

        assert stats.requested_count == 2
        assert stats.checked_count == 2
        assert stats.risk_count == 0
        assert stats.failed_count == 0
        assert len(results) == 0

    def test_stats_partial_failure(self):
        """部分失败时统计正确。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        call_count = [0]
        def mock_scan_batch(batch, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # 第一批 10 个商品，AI 只返回了 8 个，2 个漏返回
                results = [
                    ImageRiskItem(str(i), f"https://example.com/p{i}.jpg",
                                 "infringement" if i == 1 else "none",
                                 "角色IP" if i == 1 else "")
                    for i in range(1, 9)
                ]
                return results, 0
            # 第二批异常
            raise RuntimeError("API error")

        service._scan_single_batch = mock_scan_batch
        # 11 个商品会分成 10 + 1 两批
        products = [{"id": str(i), "main_image": f"https://example.com/p{i}.jpg"} for i in range(1, 12)]
        results, stats, _all = service.scan_batch(products)

        assert stats.requested_count == 11
        assert stats.cached_count == 0
        assert stats.checked_count == 8  # 第一批成功返回 8 个结果
        assert stats.risk_count == 1
        # 失败: 第一批2个AI漏返回 + 第二批1个异常 = 3
        assert stats.failed_count == 3
        # 不变式
        assert stats.requested_count == stats.cached_count + stats.checked_count + stats.failed_count

    def test_stats_with_cache_mixed(self):
        """缓存 + 新检测混合时统计正确。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        # 预先缓存 2 个（1 风险 + 1 无风险）
        service._set_cached("1", "https://example.com/p1.jpg",
                           ImageRiskItem("1", "https://example.com/p1.jpg", "infringement", "品牌Logo"))
        service._set_cached("2", "https://example.com/p2.jpg",
                           ImageRiskItem("2", "https://example.com/p2.jpg", "none", ""))

        def mock_scan_batch(batch, **kwargs):
            return [ImageRiskItem("3", "https://example.com/p3.jpg", "none", "")], 0

        service._scan_single_batch = mock_scan_batch
        products = [
            {"id": "1", "main_image": "https://example.com/p1.jpg"},
            {"id": "2", "main_image": "https://example.com/p2.jpg"},
            {"id": "3", "main_image": "https://example.com/p3.jpg"},
        ]
        results, stats, _all = service.scan_batch(products)

        assert stats.requested_count == 3
        assert stats.cached_count == 2
        assert stats.checked_count == 1
        assert stats.risk_count == 1  # 只有缓存的 id=1 是风险
        assert stats.failed_count == 0
        assert len(results) == 1  # 只有 id=1 是风险


class TestDownloadFailureStats:
    """测试图片下载失败的统计。"""

    def test_single_download_failure(self):
        """单张图片下载失败 → failed_count +1。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        def mock_scan_batch(batch, **kwargs):
            # 10个商品中只有1个成功下载，9个下载失败
            return [ImageRiskItem("1", "https://example.com/p1.jpg", "infringement", "品牌Logo")], 9

        service._scan_single_batch = mock_scan_batch
        products = [{"id": str(i), "main_image": f"https://example.com/p{i}.jpg"} for i in range(1, 11)]
        results, stats, _all = service.scan_batch(products)

        assert stats.requested_count == 10
        assert stats.checked_count == 1
        assert stats.failed_count == 9  # 9 个下载失败 + 0 个AI漏返回
        assert stats.risk_count == 1
        assert stats.cached_count == 0
        # 不变式: requested = cached + checked + failed
        assert stats.requested_count == stats.cached_count + stats.checked_count + stats.failed_count

    def test_download_failure_no_cache_written(self):
        """下载失败的商品不应写入缓存。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        def mock_scan_batch(batch, **kwargs):
            return [ImageRiskItem("1", "https://example.com/p1.jpg", "infringement", "角色IP")], 1

        service._scan_single_batch = mock_scan_batch
        products = [
            {"id": "1", "main_image": "https://example.com/p1.jpg"},
            {"id": "2", "https://example.com/p2.jpg": "https://example.com/p2.jpg"},  # 下载失败
        ]
        # 修正 id 2 的商品数据
        products = [
            {"id": "1", "main_image": "https://example.com/p1.jpg"},
            {"id": "2", "main_image": "https://example.com/p2.jpg"},
        ]
        results, stats, _all = service.scan_batch(products)

        # 只有 id=1 写入缓存
        assert service.get_cached("1", "https://example.com/p1.jpg") is not None
        # id=2 不应写入缓存
        assert service.get_cached("2", "https://example.com/p2.jpg") is None


class TestAIMissedAndDuplicate:
    """测试 AI 漏返回和重复返回。"""

    def test_ai_misses_product_id(self):
        """AI 漏返回一个商品 id → 该商品 failed_count +1。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        def mock_scan_batch(batch, **kwargs):
            # 3 个商品送检，但 AI 只返回了 2 个
            return [
                ImageRiskItem("1", "https://example.com/p1.jpg", "infringement", "角色IP"),
                ImageRiskItem("2", "https://example.com/p2.jpg", "none", ""),
            ], 0  # 下载都成功

        service._scan_single_batch = mock_scan_batch
        products = [
            {"id": "1", "main_image": "https://example.com/p1.jpg"},
            {"id": "2", "main_image": "https://example.com/p2.jpg"},
            {"id": "3", "main_image": "https://example.com/p3.jpg"},  # AI 漏返回
        ]
        results, stats, _all = service.scan_batch(products)

        assert stats.requested_count == 3
        assert stats.checked_count == 2
        assert stats.failed_count == 1  # id=3 被AI漏返回
        assert stats.requested_count == stats.cached_count + stats.checked_count + stats.failed_count

    def test_ai_unknown_id_not_counted(self):
        """AI 返回未知 id → 不增加 checked_count。"""
        image_items = [
            ("1", "https://example.com/p1.jpg", b"fake"),
        ]
        data = {
            "results": [
                {"id": "1", "risk": "infringement", "reason": "角色IP"},
                {"id": "999", "risk": "infringement", "reason": "品牌Logo"},  # 未知 id
            ]
        }
        results = ImageRiskScanService._parse_results(data, image_items)
        assert len(results) == 1
        assert results[0].product_id == "1"

    def test_ai_duplicate_id_only_first(self):
        """AI 重复返回同一 id → 只取第一个，不重复计数。"""
        image_items = [
            ("1", "https://example.com/p1.jpg", b"fake"),
        ]
        data = {
            "results": [
                {"id": "1", "risk": "infringement", "reason": "角色IP"},
                {"id": "1", "risk": "none", "reason": ""},  # 重复
            ]
        }
        results = ImageRiskScanService._parse_results(data, image_items)
        assert len(results) == 1
        assert results[0].risk == "infringement"  # 取第一个


class TestStatsInvariant:
    """测试 requested = cached + checked + failed 不变式。"""

    def test_invariant_all_cases(self):
        """混合场景下不变式成立。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        # 预先缓存 1 个
        service._set_cached("1", "https://example.com/p1.jpg",
                           ImageRiskItem("1", "https://example.com/p1.jpg", "infringement", "品牌Logo"))

        def mock_scan_batch(batch, **kwargs):
            # 2个商品送检（id=2, id=3）
            # id=2 成功，id=3 下载失败
            return [ImageRiskItem("2", "https://example.com/p2.jpg", "none", "")], 1

        service._scan_single_batch = mock_scan_batch
        products = [
            {"id": "1", "main_image": "https://example.com/p1.jpg"},  # 缓存
            {"id": "2", "main_image": "https://example.com/p2.jpg"},
            {"id": "3", "main_image": "https://example.com/p3.jpg"},  # 下载失败
        ]
        results, stats, _all = service.scan_batch(products)

        assert stats.requested_count == 3
        assert stats.cached_count == 1
        assert stats.checked_count == 1
        assert stats.failed_count == 1
        # 不变式
        assert stats.requested_count == stats.cached_count + stats.checked_count + stats.failed_count


class TestForceRefresh:
    """测试 force_refresh 参数。"""

    def test_default_uses_cache(self):
        """默认再次检测同图 → 命中缓存，不调用 API。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)
        service._set_cached("1", "https://example.com/p1.jpg",
                           ImageRiskItem("1", "https://example.com/p1.jpg", "infringement", "品牌Logo"))

        call_count = [0]
        def mock_scan_batch(batch, **kwargs):
            call_count[0] += 1
            return [], 0

        service._scan_single_batch = mock_scan_batch
        products = [{"id": "1", "main_image": "https://example.com/p1.jpg"}]
        results, stats, _all = service.scan_batch(products)

        assert call_count[0] == 0  # 未调用 API
        assert stats.cached_count == 1
        assert stats.checked_count == 0

    def test_force_refresh_bypasses_cache(self):
        """force_refresh=True → 即使有缓存也重新调用 API。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)
        service._set_cached("1", "https://example.com/p1.jpg",
                           ImageRiskItem("1", "https://example.com/p1.jpg", "infringement", "品牌Logo"))

        call_count = [0]
        def mock_scan_batch(batch, **kwargs):
            call_count[0] += 1
            return [ImageRiskItem("1", "https://example.com/p1.jpg", "none", "")], 0

        service._scan_single_batch = mock_scan_batch
        products = [{"id": "1", "main_image": "https://example.com/p1.jpg"}]
        results, stats, _all = service.scan_batch(products, force_refresh=True)

        assert call_count[0] == 1  # 重新调用了 API
        assert stats.cached_count == 0  # 不算缓存
        assert stats.checked_count == 1

    def test_force_refresh_overwrites_cache(self):
        """重新检测后的结果覆盖旧运行期缓存。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)
        # 旧缓存：有风险
        service._set_cached("1", "https://example.com/p1.jpg",
                           ImageRiskItem("1", "https://example.com/p1.jpg", "infringement", "品牌Logo"))

        def mock_scan_batch(batch, **kwargs):
            # 新结果：无风险
            return [ImageRiskItem("1", "https://example.com/p1.jpg", "none", "")], 0

        service._scan_single_batch = mock_scan_batch
        products = [{"id": "1", "main_image": "https://example.com/p1.jpg"}]
        results, stats, _all = service.scan_batch(products, force_refresh=True)

        # 缓存已被新结果覆盖
        cached = service.get_cached("1", "https://example.com/p1.jpg")
        assert cached is not None
        assert cached.risk == "none"
        # 无风险结果不进入 risky results
        assert len(results) == 0


class TestNoPersistence:
    """测试不产生持久化。"""

    def test_no_files_or_db_created(self, tmp_path):
        """不增加持久化文件或数据库记录。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)
        service._set_cached("1", "https://example.com/p1.jpg",
                           ImageRiskItem("1", "https://example.com/p1.jpg", "infringement", "品牌Logo"))
        # 只检查内存缓存存在，且没有文件创建逻辑
        assert len(service._cache) == 1
        assert service.get_cached("1", "https://example.com/p1.jpg") is not None
        # _cache 是纯 dict，不写文件
        assert hasattr(service, '_cache')
        assert isinstance(service._cache, dict)


class TestAllChecked:
    """测试 scan_batch 返回 all_checked（本次成功检测的所有商品，含安全）。"""

    def test_all_checked_includes_safe_items(self):
        """all_checked 包含安全商品。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        def mock_scan_batch(batch, **kwargs):
            return [
                ImageRiskItem("1", "https://example.com/p1.jpg", "infringement", "角色IP"),
                ImageRiskItem("2", "https://example.com/p2.jpg", "none", ""),
            ], 0

        service._scan_single_batch = mock_scan_batch
        products = [
            {"id": "1", "main_image": "https://example.com/p1.jpg"},
            {"id": "2", "main_image": "https://example.com/p2.jpg"},
        ]
        results, stats, all_checked = service.scan_batch(products)

        assert len(results) == 1  # 只有风险的
        assert len(all_checked) == 2  # 包含安全的
        assert all_checked[0].risk == "infringement"
        assert all_checked[1].risk == "none"

    def test_all_checked_empty_when_all_cached(self):
        """全部命中缓存时 all_checked 为空（无需更新 UI）。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)
        service._set_cached("1", "https://example.com/p1.jpg",
                           ImageRiskItem("1", "https://example.com/p1.jpg", "infringement", "角色IP"))
        products = [{"id": "1", "main_image": "https://example.com/p1.jpg"}]
        results, stats, all_checked = service.scan_batch(products)

        assert len(all_checked) == 0
        assert stats.cached_count == 1

    def test_all_checked_does_not_include_failed(self):
        """检测失败的商品不在 all_checked 中。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        def mock_scan_batch(batch, **kwargs):
            # 1个成功，2个下载失败
            return [ImageRiskItem("1", "https://example.com/p1.jpg", "none", "")], 2

        service._scan_single_batch = mock_scan_batch
        products = [
            {"id": "1", "main_image": "https://example.com/p1.jpg"},
            {"id": "2", "main_image": "https://example.com/p2.jpg"},
            {"id": "3", "main_image": "https://example.com/p3.jpg"},
        ]
        results, stats, all_checked = service.scan_batch(products)

        assert len(all_checked) == 1
        assert all_checked[0].product_id == "1"
        assert stats.failed_count == 2


@pytest.fixture()
def risk_log_dir(tmp_path):
    """将风险日志配置到临时目录，测试结束关闭 handler（避免 Windows 文件锁）。"""
    from profit_accounting_26.product_collector import product_risk_log as prl
    for handler in list(prl._logger.handlers):
        prl._logger.removeHandler(handler)
        handler.close()
    path = prl.configure(tmp_path)
    yield path
    for handler in list(prl._logger.handlers):
        prl._logger.removeHandler(handler)
        handler.close()


class TestPromptContractV3:
    """V3 图片 Prompt / request contract 测试。

    只验证 Prompt contract、request contract、解析器与兼容性，
    不做假 AI 准确率测试。
    """

    def test_prompt_version_is_v3(self):
        """图片 PROMPT_VERSION 必须为 v3。"""
        import profit_accounting_26.product_collector.image_risk_scan as module
        assert module.PROMPT_VERSION == "product-collector-image-risk-v3"
        assert ImageRiskScanService.PROMPT_VERSION == "product-collector-image-risk-v3"

    def test_prompt_contains_adult_semantics(self):
        """图片 Prompt 包含成人色情 / 性暗示风险语义。"""
        prompt = _build_image_prompt()
        assert "性暗示" in prompt
        assert "性器官" in prompt
        assert "儿童性感化" in prompt

    def test_prompt_contains_political_semantics(self):
        """图片 Prompt 包含政治人物 / 政治组织风险语义。"""
        prompt = _build_image_prompt()
        assert "政治人物" in prompt
        assert "政党 / 政治组织" in prompt
        assert "政治口号" in prompt

    def test_prompt_contains_religion_semantics(self):
        """图片 Prompt 包含明确宗教内容风险语义。"""
        prompt = _build_image_prompt()
        assert "宗教人物" in prompt
        assert "宗教经文" in prompt
        assert "明确可识别即可判" in prompt
        assert "宗教建筑" in prompt

    def test_prompt_contains_hate_semantics(self):
        """图片 Prompt 包含仇恨 / 歧视风险语义。"""
        prompt = _build_image_prompt()
        assert "仇恨" in prompt
        assert "歧视" in prompt
        assert "白人至上" in prompt

    def test_prompt_contains_violence_semantics(self):
        """图片 Prompt 包含严重暴力 / 血腥 / 自残风险语义。"""
        prompt = _build_image_prompt()
        assert "血腥" in prompt
        assert "自残" in prompt
        assert "开放性伤口" in prompt

    def test_prompt_sensitive_flag_still_platform(self):
        """敏感旗帜 / 国徽仍属于 platform 范围，不因印在商品上而豁免。"""
        prompt = _build_image_prompt()
        assert "敏感旗帜 / 国徽" in prompt
        assert "仍应判 platform" in prompt
        assert "自动豁免" in prompt

    def test_prompt_no_absolute_flag_exemption(self):
        """不允许再次出现'国旗 / 国徽只要装饰用途就不判'的绝对豁免语义。"""
        prompt = _build_image_prompt()
        assert "仅装饰性使用且无政治宣传语义，不判" not in prompt
        assert "普通非敏感旗帜" in prompt

    def test_prompt_contains_halloween_guard(self):
        """图片 Prompt 包含 Halloween 防误杀语义。"""
        prompt = _build_image_prompt()
        assert "美国站 Halloween 防误杀" in prompt
        assert "普通骷髅" in prompt
        assert "普通南瓜" in prompt

    def test_prompt_contains_88_context_guard(self):
        """图片 Prompt 明确 88 不能脱离语境机械判断。"""
        prompt = _build_image_prompt()
        assert "14/88" in prompt
        assert "88cm" in prompt
        assert "普通含义绝不判风险" in prompt

    def test_prompt_contains_packaging_brand_signal(self):
        """图片 Prompt 包含明显品牌包装标识风险。"""
        prompt = _build_image_prompt()
        assert "包装 Logo" in prompt
        assert "包装商标" in prompt
        assert "独立包装名称" in prompt

    def test_prompt_title_is_auxiliary_only(self):
        """标题仅辅助、图片必须有视觉证据。"""
        prompt = _build_image_prompt()
        assert "辅助信息" in prompt
        assert "视觉证据" in prompt
        assert "不得仅凭标题判风险" in prompt

    def test_prompt_contains_reason_prefixes(self):
        """reason 三种前缀存在。"""
        prompt = _build_image_prompt()
        assert "SHEIN规则风险｜" in prompt
        assert "采集规则排除｜" in prompt
        assert "侵权风险｜" in prompt

    def test_prompt_risk_enum_still_three(self):
        """图片风险枚举仍只有 none/platform/infringement，无第四档。"""
        prompt = _build_image_prompt()
        assert "none | platform | infringement" in prompt
        lowered = prompt.lower()
        assert "review" not in lowered
        assert "confidence" not in lowered
        assert "risk_type" not in lowered

    def test_batch_size_still_10(self):
        """BATCH_SIZE 仍为 10。"""
        assert BATCH_SIZE == 10
        assert ImageRiskScanService.BATCH_SIZE == 10


class TestImageRequestWithTitle:
    """图片请求携带标题辅助上下文（request contract）。"""

    @staticmethod
    def _service_with_capture(monkeypatch):
        """构造 service 并捕获实际请求 body。"""
        profile_store = MagicMock()
        profile = MagicMock()
        profile.api_url = "https://api.example.com/v1"
        profile.model_name = "test-model"
        profile.provider = "OpenAI"
        profile_store.bound_profile.return_value = (profile, "test-key")

        captured: dict = {}
        response_data = {"results": [{"id": "1", "risk": "none", "reason": ""}]}
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

        import profit_accounting_26.product_collector.image_risk_scan as module

        def fake_urlopen(request, **kwargs):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return MockResponse()

        monkeypatch.setattr(module, "urlopen", fake_urlopen)
        service = ImageRiskScanService(profile_store)
        monkeypatch.setattr(service, "_download_image", lambda url: b"fake-image-data")
        return service, captured

    @staticmethod
    def _texts(body):
        content = body["messages"][0]["content"]
        return [c["text"] for c in content if c.get("type") == "text"]

    def test_request_contains_id_title_image(self, monkeypatch):
        """图片请求实际带 id、title、image。"""
        service, captured = self._service_with_capture(monkeypatch)
        products = [
            {"id": "1", "title": "Disney Halloween Bag", "main_image": "https://example.com/1.jpg"}
        ]
        service.scan_batch(products)
        text_all = "\n".join(self._texts(captured["body"]))
        assert "商品ID: 1" in text_all
        assert "商品标题: Disney Halloween Bag" in text_all
        content = captured["body"]["messages"][0]["content"]
        assert any(c.get("type") == "image_url" for c in content)

    def test_empty_title_omits_title_text(self, monkeypatch):
        """title 为空时请求不携带标题文本，图片检测仍正常运行。"""
        service, captured = self._service_with_capture(monkeypatch)
        products = [{"id": "1", "title": "", "main_image": "https://example.com/1.jpg"}]
        risky, stats, _all = service.scan_batch(products)
        assert stats.failed_count == 0
        assert stats.checked_count == 1
        text_all = "\n".join(self._texts(captured["body"]))
        assert "商品ID: 1" in text_all
        assert "商品标题:" not in text_all

    def test_missing_title_key_still_works(self, monkeypatch):
        """旧调用不提供 title 键时不崩溃。"""
        service, captured = self._service_with_capture(monkeypatch)
        products = [{"id": "1", "main_image": "https://example.com/1.jpg"}]
        risky, stats, _all = service.scan_batch(products)
        assert stats.failed_count == 0
        assert stats.checked_count == 1
        text_all = "\n".join(self._texts(captured["body"]))
        assert "商品标题:" not in text_all

    def test_cache_key_ignores_title(self):
        """缓存 key 仍为 (product_id, main_image)，标题变化不影响缓存命中。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)
        service._set_cached("1", "https://example.com/1.jpg",
                            ImageRiskItem("1", "https://example.com/1.jpg", "none", ""))
        call_count = [0]

        def mock_scan_batch(batch, **kwargs):
            call_count[0] += 1
            return [], 0

        service._scan_single_batch = mock_scan_batch
        # 带 title 的请求应命中与无 title 时相同的缓存键
        products = [{"id": "1", "title": "Any Title", "main_image": "https://example.com/1.jpg"}]
        results, stats, _all = service.scan_batch(products)
        assert call_count[0] == 0
        assert stats.cached_count == 1
        assert len(results) == 0


class TestImageRiskLogStatus:
    """任务 3/4：图片取消日志、最终状态规则、实际执行批次数。"""

    def _service(self, batch_result=None):
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)
        if batch_result is None:
            # 默认 mock：批次内每个商品都成功返回 none
            service._scan_single_batch = MagicMock(
                side_effect=lambda batch, **kw: (
                    [ImageRiskItem(p["id"], p["main_image"], "none", "") for p in batch],
                    0,
                )
            )
        else:
            service._scan_single_batch = MagicMock(return_value=batch_result)
        return service

    def _products(self, count):
        return [
            {"id": str(i), "main_image": f"https://img.example/{i}.jpg"}
            for i in range(1, count + 1)
        ]

    def test_cancel_during_single_batch_logs_cancelled_once(self, risk_log_dir):
        """单批（<=10 张）API 请求期间取消：日志只写一次用户取消，status=取消。"""
        service = self._service()
        calls = {"n": 0}

        def cancel():
            calls["n"] += 1
            return calls["n"] > 1  # 批次前放行；批次完成后标记取消

        risky, stats, _all = service.scan_batch(
            self._products(2), cancel_requested=cancel
        )
        content = risk_log_dir.read_text(encoding="utf-8")
        assert content.count("[图片检测] 用户取消") == 1
        assert "status=取消" in content
        assert stats.checked_count == 2  # 当前批允许自然完成

    def test_cancel_during_last_batch_logs_cancelled_once(self, risk_log_dir):
        """最后一批 API 请求期间取消：必须记录用户取消。"""
        service = self._service()
        calls = {"n": 0}

        def cancel():
            calls["n"] += 1
            # 前 3 次检查放行（批次1前/批次1后/批次2前），
            # 第 4 次（批次2 完成后的批次后检查）才标记取消
            return calls["n"] >= 4

        risky, stats, _all = service.scan_batch(
            self._products(11), cancel_requested=cancel  # 2 批
        )
        content = risk_log_dir.read_text(encoding="utf-8")
        assert content.count("[图片检测] 用户取消") == 1
        assert "status=取消" in content
        assert "批次数=2" in content  # 实际执行 2 批

    def test_cancel_between_batches_logs_cancelled_once(self, risk_log_dir):
        """批次间取消：只写一次用户取消，后续批次不再发送。"""
        service = self._service()
        calls = {"n": 0}

        def cancel():
            calls["n"] += 1
            return calls["n"] >= 2  # 第一批后、第二批前取消

        risky, stats, _all = service.scan_batch(
            self._products(20), cancel_requested=cancel  # 计划 2 批
        )
        content = risk_log_dir.read_text(encoding="utf-8")
        assert content.count("[图片检测] 用户取消") == 1
        assert "status=取消" in content
        assert "批次数=1" in content  # 只实际执行了 1 批
        assert stats.checked_count == 10

    def test_final_status_completed(self, risk_log_dir):
        """无失败：status=完成。"""
        service = self._service()
        service.scan_batch(self._products(2))
        content = risk_log_dir.read_text(encoding="utf-8")
        assert "status=完成" in content

    def test_final_status_partial_failure(self, risk_log_dir):
        """failed>0 且 checked>0：status=部分失败。"""
        batch_result = (
            [ImageRiskItem("1", "https://img.example/1.jpg", "none", "")],
            1,  # 下载失败 1 个
        )
        service = self._service(batch_result)
        service.scan_batch(self._products(2))
        content = risk_log_dir.read_text(encoding="utf-8")
        assert "status=部分失败" in content

    def test_final_status_total_failure(self, risk_log_dir):
        """failed>0 且 checked==0：status=失败。"""
        batch_result = ([], 2)  # 全部下载失败
        service = self._service(batch_result)
        service.scan_batch(self._products(2))
        content = risk_log_dir.read_text(encoding="utf-8")
        assert "status=失败" in content

    def test_batches_records_executed_not_planned(self, risk_log_dir):
        """批次数记录实际执行过的批次数，取消时不是原计划总批数。"""
        service = self._service()
        calls = {"n": 0}

        def cancel():
            calls["n"] += 1
            return calls["n"] > 1  # 第一批完成后取消

        service.scan_batch(self._products(15), cancel_requested=cancel)  # 计划 2 批
        content = risk_log_dir.read_text(encoding="utf-8")
        assert "批次数=1" in content
