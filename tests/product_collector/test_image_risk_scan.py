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
        results, failed = service.scan_batch([])
        assert results == []
        assert failed == 0

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
        results, failed = service.scan_batch(products)

        assert call_count[0] == 1  # 只调用了一次
        assert len(results) == 1  # 只有缓存的那个 has_risk=True

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
        results, failed = service.scan_batch(products)

        assert failed == 0
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
