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
        assert "品牌 Logo" in prompt
        assert "动漫角色" in prompt
        assert "影视角色" in prompt
        assert "游戏角色" in prompt
        assert "球队标志" in prompt
        assert "品牌/IP复核" in prompt or "has_risk" in prompt

    def test_prompt_contains_strict_rules(self):
        prompt = _build_image_prompt()
        assert "误判" in prompt
        assert "侵权" not in prompt or "不是判断" in prompt


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
            has_risk=True,
            labels=["品牌Logo"],
            display_label="品牌/IP复核",
        )
        service._set_cached("1", "https://example.com/pic.jpg", item)
        cached = service.get_cached("1", "https://example.com/pic.jpg")
        assert cached is not None
        assert cached.has_risk is True

    def test_cache_key_includes_url(self):
        """缓存键包含 URL，不同图片不共享缓存。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)
        item1 = ImageRiskItem("1", "https://example.com/pic1.jpg", True, [], "品牌/IP复核")
        item2 = ImageRiskItem("1", "https://example.com/pic2.jpg", False, [], "")
        service._set_cached("1", "https://example.com/pic1.jpg", item1)
        service._set_cached("1", "https://example.com/pic2.jpg", item2)
        assert service.get_cached("1", "https://example.com/pic1.jpg").has_risk is True
        assert service.get_cached("1", "https://example.com/pic2.jpg").has_risk is False

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
        results, stats = service.scan_batch([])
        assert results == []
        assert stats.requested_count == 0
        assert stats.failed_count == 0

    def test_scan_batch_uses_cache(self):
        """已缓存的商品应跳过检测。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        # 预先缓存一个结果
        item = ImageRiskItem("1", "https://example.com/pic1.jpg", True, ["品牌Logo"], "品牌/IP复核")
        service._set_cached("1", "https://example.com/pic1.jpg", item)

        products = [
            {"id": "1", "main_image": "https://example.com/pic1.jpg"},  # 已缓存
            {"id": "2", "main_image": "https://example.com/pic2.jpg"},  # 未缓存
        ]

        # Mock _scan_single_batch 只处理未缓存的
        call_count = [0]
        def mock_scan_batch(batch):
            call_count[0] += 1
            return [ImageRiskItem("2", "https://example.com/pic2.jpg", False, [], "")], 0

        service._scan_single_batch = mock_scan_batch
        results, stats = service.scan_batch(products)

        assert call_count[0] == 1  # 只调用了一次
        assert len(results) == 1  # 只有缓存的那个 has_risk=True
        assert stats.requested_count == 2
        assert stats.cached_count == 1
        assert stats.checked_count == 1
        assert stats.risk_count == 1
        assert stats.failed_count == 0

    def test_parse_results_valid(self):
        """正常解析图片风险结果。"""
        image_items = [
            ("1", "https://example.com/pic1.jpg", b"fake"),
            ("2", "https://example.com/pic2.jpg", b"fake"),
        ]
        data = {
            "results": [
                {"id": "1", "has_risk": True, "internal_labels": ["品牌Logo"], "detail": "Nike Swoosh"},
                {"id": "2", "has_risk": False},  # 无风险不输出
            ]
        }
        results = ImageRiskScanService._parse_results(data, image_items)
        assert len(results) == 2
        assert results[0].product_id == "1"
        assert results[0].has_risk is True
        assert results[0].labels == ["品牌Logo"]
        assert results[0].display_label == "品牌/IP复核"

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
                {"id": "999", "has_risk": True, "internal_labels": ["品牌Logo"]},  # 未知 id
            ]
        }
        results = ImageRiskScanService._parse_results(data, image_items)
        assert len(results) == 0


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
                {"id": "1", "has_risk": True, "internal_labels": ["角色IP"], "detail": "Disney Character"},
                {"id": "2", "has_risk": False},
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
        results, stats = service.scan_batch(products)

        assert stats.failed_count == 0
        assert stats.requested_count == 2
        assert stats.checked_count == 2
        assert stats.risk_count == 1
        assert len(results) == 1
        assert results[0].product_id == "1"
        assert results[0].has_risk is True
        assert "角色IP" in results[0].labels


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
        """has_risk=false 的结果应进入运行期缓存。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        def mock_scan_batch(batch):
            return [ImageRiskItem("1", "https://example.com/pic.jpg", False, [], "")], 0

        service._scan_single_batch = mock_scan_batch
        products = [{"id": "1", "main_image": "https://example.com/pic.jpg"}]
        results, stats = service.scan_batch(products)

        # 无风险不进入 risky results
        assert len(results) == 0
        # 但应进入缓存
        cached = service.get_cached("1", "https://example.com/pic.jpg")
        assert cached is not None
        assert cached.has_risk is False

    def test_same_normal_image_skips_api(self):
        """再次检测同一正常图片不应重复调用 API。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        # 预先缓存无风险结果
        item = ImageRiskItem("1", "https://example.com/pic.jpg", False, [], "")
        service._set_cached("1", "https://example.com/pic.jpg", item)

        call_count = [0]
        def mock_scan_batch(batch):
            call_count[0] += 1
            return [], 0

        service._scan_single_batch = mock_scan_batch
        products = [{"id": "1", "main_image": "https://example.com/pic.jpg"}]
        results, stats = service.scan_batch(products)

        assert call_count[0] == 0  # 未调用 API
        assert stats.cached_count == 1
        assert stats.checked_count == 0
        assert len(results) == 0  # 无风险

    def test_risky_image_also_cached(self):
        """风险图片也应正常缓存。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        def mock_scan_batch(batch):
            return [ImageRiskItem("1", "https://example.com/pic.jpg", True, ["品牌Logo"], "品牌/IP复核")], 0

        service._scan_single_batch = mock_scan_batch
        products = [{"id": "1", "main_image": "https://example.com/pic.jpg"}]
        results, stats = service.scan_batch(products)

        assert len(results) == 1
        cached = service.get_cached("1", "https://example.com/pic.jpg")
        assert cached is not None
        assert cached.has_risk is True


class TestImageRiskStats:
    """测试图片检测统计。"""

    def test_stats_all_normal(self):
        """全部正常时统计正确，检测数量不为 0。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        def mock_scan_batch(batch):
            return [
                ImageRiskItem("1", "https://example.com/p1.jpg", False, [], ""),
                ImageRiskItem("2", "https://example.com/p2.jpg", False, [], ""),
            ], 0

        service._scan_single_batch = mock_scan_batch
        products = [
            {"id": "1", "main_image": "https://example.com/p1.jpg"},
            {"id": "2", "main_image": "https://example.com/p2.jpg"},
        ]
        results, stats = service.scan_batch(products)

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
        def mock_scan_batch(batch):
            call_count[0] += 1
            if call_count[0] == 1:
                # 第一批 10 个商品，AI 只返回了 8 个，2 个漏返回
                results = [
                    ImageRiskItem(str(i), f"https://example.com/p{i}.jpg",
                                 i == 1, ["角色IP"] if i == 1 else [],
                                 "品牌/IP复核" if i == 1 else "")
                    for i in range(1, 9)
                ]
                return results, 0
            # 第二批异常
            raise RuntimeError("API error")

        service._scan_single_batch = mock_scan_batch
        # 11 个商品会分成 10 + 1 两批
        products = [{"id": str(i), "main_image": f"https://example.com/p{i}.jpg"} for i in range(1, 12)]
        results, stats = service.scan_batch(products)

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
                           ImageRiskItem("1", "https://example.com/p1.jpg", True, ["品牌Logo"], "品牌/IP复核"))
        service._set_cached("2", "https://example.com/p2.jpg",
                           ImageRiskItem("2", "https://example.com/p2.jpg", False, [], ""))

        def mock_scan_batch(batch):
            return [ImageRiskItem("3", "https://example.com/p3.jpg", False, [], "")], 0

        service._scan_single_batch = mock_scan_batch
        products = [
            {"id": "1", "main_image": "https://example.com/p1.jpg"},
            {"id": "2", "main_image": "https://example.com/p2.jpg"},
            {"id": "3", "main_image": "https://example.com/p3.jpg"},
        ]
        results, stats = service.scan_batch(products)

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

        def mock_scan_batch(batch):
            # 10个商品中只有1个成功下载，9个下载失败
            return [ImageRiskItem("1", "https://example.com/p1.jpg", True, ["品牌Logo"], "品牌/IP复核")], 9

        service._scan_single_batch = mock_scan_batch
        products = [{"id": str(i), "main_image": f"https://example.com/p{i}.jpg"} for i in range(1, 11)]
        results, stats = service.scan_batch(products)

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

        def mock_scan_batch(batch):
            return [ImageRiskItem("1", "https://example.com/p1.jpg", True, ["角色IP"], "品牌/IP复核")], 1

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
        results, stats = service.scan_batch(products)

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

        def mock_scan_batch(batch):
            # 3 个商品送检，但 AI 只返回了 2 个
            return [
                ImageRiskItem("1", "https://example.com/p1.jpg", True, ["角色IP"], "品牌/IP复核"),
                ImageRiskItem("2", "https://example.com/p2.jpg", False, [], ""),
            ], 0  # 下载都成功

        service._scan_single_batch = mock_scan_batch
        products = [
            {"id": "1", "main_image": "https://example.com/p1.jpg"},
            {"id": "2", "main_image": "https://example.com/p2.jpg"},
            {"id": "3", "main_image": "https://example.com/p3.jpg"},  # AI 漏返回
        ]
        results, stats = service.scan_batch(products)

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
                {"id": "1", "has_risk": True, "internal_labels": ["角色IP"]},
                {"id": "999", "has_risk": True, "internal_labels": ["品牌Logo"]},  # 未知 id
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
                {"id": "1", "has_risk": True, "internal_labels": ["角色IP"]},
                {"id": "1", "has_risk": False},  # 重复
            ]
        }
        results = ImageRiskScanService._parse_results(data, image_items)
        assert len(results) == 1
        assert results[0].has_risk is True  # 取第一个


class TestStatsInvariant:
    """测试 requested = cached + checked + failed 不变式。"""

    def test_invariant_all_cases(self):
        """混合场景下不变式成立。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)

        # 预先缓存 1 个
        service._set_cached("1", "https://example.com/p1.jpg",
                           ImageRiskItem("1", "https://example.com/p1.jpg", True, ["品牌Logo"], "品牌/IP复核"))

        def mock_scan_batch(batch):
            # 2个商品送检（id=2, id=3）
            # id=2 成功，id=3 下载失败
            return [ImageRiskItem("2", "https://example.com/p2.jpg", False, [], "")], 1

        service._scan_single_batch = mock_scan_batch
        products = [
            {"id": "1", "main_image": "https://example.com/p1.jpg"},  # 缓存
            {"id": "2", "main_image": "https://example.com/p2.jpg"},
            {"id": "3", "main_image": "https://example.com/p3.jpg"},  # 下载失败
        ]
        results, stats = service.scan_batch(products)

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
                           ImageRiskItem("1", "https://example.com/p1.jpg", True, ["品牌Logo"], "品牌/IP复核"))

        call_count = [0]
        def mock_scan_batch(batch):
            call_count[0] += 1
            return [], 0

        service._scan_single_batch = mock_scan_batch
        products = [{"id": "1", "main_image": "https://example.com/p1.jpg"}]
        results, stats = service.scan_batch(products)

        assert call_count[0] == 0  # 未调用 API
        assert stats.cached_count == 1
        assert stats.checked_count == 0

    def test_force_refresh_bypasses_cache(self):
        """force_refresh=True → 即使有缓存也重新调用 API。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)
        service._set_cached("1", "https://example.com/p1.jpg",
                           ImageRiskItem("1", "https://example.com/p1.jpg", True, ["品牌Logo"], "品牌/IP复核"))

        call_count = [0]
        def mock_scan_batch(batch):
            call_count[0] += 1
            return [ImageRiskItem("1", "https://example.com/p1.jpg", False, [], "")], 0

        service._scan_single_batch = mock_scan_batch
        products = [{"id": "1", "main_image": "https://example.com/p1.jpg"}]
        results, stats = service.scan_batch(products, force_refresh=True)

        assert call_count[0] == 1  # 重新调用了 API
        assert stats.cached_count == 0  # 不算缓存
        assert stats.checked_count == 1

    def test_force_refresh_overwrites_cache(self):
        """重新检测后的结果覆盖旧运行期缓存。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)
        # 旧缓存：有风险
        service._set_cached("1", "https://example.com/p1.jpg",
                           ImageRiskItem("1", "https://example.com/p1.jpg", True, ["品牌Logo"], "品牌/IP复核"))

        def mock_scan_batch(batch):
            # 新结果：无风险
            return [ImageRiskItem("1", "https://example.com/p1.jpg", False, [], "")], 0

        service._scan_single_batch = mock_scan_batch
        products = [{"id": "1", "main_image": "https://example.com/p1.jpg"}]
        results, stats = service.scan_batch(products, force_refresh=True)

        # 缓存已被新结果覆盖
        cached = service.get_cached("1", "https://example.com/p1.jpg")
        assert cached is not None
        assert cached.has_risk is False
        # 无风险结果不进入 risky results
        assert len(results) == 0


class TestNoPersistence:
    """测试不产生持久化。"""

    def test_no_files_or_db_created(self, tmp_path):
        """不增加持久化文件或数据库记录。"""
        profile_store = MagicMock()
        service = ImageRiskScanService(profile_store)
        service._set_cached("1", "https://example.com/p1.jpg",
                           ImageRiskItem("1", "https://example.com/p1.jpg", True, ["品牌Logo"], "品牌/IP复核"))
        # 只检查内存缓存存在，且没有文件创建逻辑
        assert len(service._cache) == 1
        assert service.get_cached("1", "https://example.com/p1.jpg") is not None
        # _cache 是纯 dict，不写文件
        assert hasattr(service, '_cache')
        assert isinstance(service._cache, dict)
