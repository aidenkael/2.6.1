"""BusinessSource 极简单元测试

只覆盖真正有价值的点：
1. JSONP 解析
2. 商品提取
3. 标准链接生成
4. 缺字段跳过
5. position 连续
6. product_id 去重
7. 盲盒式扫描深度区间（固定 seed）
8. 候选池抽样：恰好 N / partial / 去重
"""

import json
import random
import unittest

from profit_accounting_26.product_collector.collector_core.business_source import (
    add_products_to_results,
    determine_status,
    extract_products_from_response,
    finalize_sample,
    parse_jsonp,
    planned_pages_for,
    standardize_url,
    STATUS_FAILED,
    STATUS_PARTIAL,
    STATUS_SUCCESS,
)
from profit_accounting_26.product_collector.collector_core.models import CandidateProduct


class TestParseJsonp(unittest.TestCase):
    def test_standard_jsonp(self):
        text = 'mtopjsonp4({"api":"test","data":{"value":1}})'
        result = parse_jsonp(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["api"], "test")
        self.assertEqual(result["data"]["value"], 1)

    def test_with_leading_whitespace(self):
        text = '  mtopjsonp1({"ok":true})'
        result = parse_jsonp(text)
        self.assertIsNotNone(result)
        self.assertTrue(result["ok"])

    def test_pure_json_fallback(self):
        text = '{"api":"test","data":{}}'
        result = parse_jsonp(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["api"], "test")

    def test_empty_string(self):
        self.assertIsNone(parse_jsonp(""))

    def test_none_like_empty(self):
        self.assertIsNone(parse_jsonp(""))

    def test_invalid_content(self):
        self.assertIsNone(parse_jsonp("not json at all"))


class TestExtractProducts(unittest.TestCase):
    def test_normal_path(self):
        parsed = {"data": {"data": [{"itemId": "123", "title": "t"}]}}
        items = extract_products_from_response(parsed)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["itemId"], "123")

    def test_missing_data_key(self):
        parsed = {"data": {}}
        items = extract_products_from_response(parsed)
        self.assertEqual(items, [])

    def test_empty_structure(self):
        self.assertEqual(extract_products_from_response({}), [])


class TestStandardizeUrl(unittest.TestCase):
    def test_basic(self):
        url = standardize_url("1005010786180634")
        self.assertEqual(url, "https://www.aliexpress.com/item/1005010786180634.html")

    def test_no_tracking_params(self):
        url = standardize_url("123456")
        self.assertNotIn("skuId", url)
        self.assertNotIn("spm", url)
        self.assertNotIn("pdp_ext_f", url)


class TestIsValid(unittest.TestCase):
    def _make_item(self, **overrides):
        base = {
            "itemId": "123",
            "title": "Test Product",
            "itemMainPic": "https://example.com/pic.jpg",
            "detailUrl": "https://www.aliexpress.com/item/123.html",
        }
        base.update(overrides)
        return base

    def test_valid_item(self):
        results = []
        seen = set()
        added, skipped = add_products_to_results([self._make_item()], "test", results, seen)
        self.assertEqual(added, 1)
        self.assertEqual(skipped, 0)

    def test_missing_title(self):
        results = []
        seen = set()
        item = self._make_item(title="")
        added, skipped = add_products_to_results([item], "test", results, seen)
        self.assertEqual(added, 0)
        self.assertEqual(skipped, 1)

    def test_missing_image(self):
        results = []
        seen = set()
        item = self._make_item(itemMainPic="")
        added, skipped = add_products_to_results([item], "test", results, seen)
        self.assertEqual(added, 0)
        self.assertEqual(skipped, 1)

    def test_missing_url(self):
        results = []
        seen = set()
        item = self._make_item(detailUrl="", itemUrl="")
        added, skipped = add_products_to_results([item], "test", results, seen)
        self.assertEqual(added, 0)
        self.assertEqual(skipped, 1)

    def test_missing_product_id(self):
        results = []
        seen = set()
        item = self._make_item(itemId="")
        added, skipped = add_products_to_results([item], "test", results, seen)
        self.assertEqual(added, 0)
        self.assertEqual(skipped, 1)


class TestDedupAndPosition(unittest.TestCase):
    def _make_item(self, pid, title="Test"):
        return {
            "itemId": pid,
            "title": title,
            "itemMainPic": "https://example.com/pic.jpg",
            "detailUrl": f"https://www.aliexpress.com/item/{pid}.html",
        }

    def test_dedup_by_product_id(self):
        results = []
        seen = set()
        items = [self._make_item("111"), self._make_item("111"), self._make_item("222")]
        add_products_to_results(items, "test", results, seen)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].product_id, "111")
        self.assertEqual(results[1].product_id, "222")

    def test_position_continuous(self):
        results = []
        seen = set()
        items = [self._make_item(f"id_{i}") for i in range(5)]
        add_products_to_results(items, "kw", results, seen)
        positions = [p.position for p in results]
        self.assertEqual(positions, [1, 2, 3, 4, 5])

    def test_position_continuous_across_batches(self):
        results = []
        seen = set()
        batch1 = [self._make_item(f"a_{i}") for i in range(3)]
        batch2 = [self._make_item(f"b_{i}") for i in range(2)]
        add_products_to_results(batch1, "kw", results, seen)
        add_products_to_results(batch2, "kw", results, seen)
        positions = [p.position for p in results]
        self.assertEqual(positions, [1, 2, 3, 4, 5])

    def test_keyword_preserved(self):
        results = []
        seen = set()
        items = [self._make_item("x1")]
        add_products_to_results(items, "women bag", results, seen)
        self.assertEqual(results[0].keyword, "women bag")

    def test_url_standardized(self):
        results = []
        seen = set()
        items = [self._make_item("1005010786180634")]
        add_products_to_results(items, "test", results, seen)
        self.assertEqual(
            results[0].product_url,
            "https://www.aliexpress.com/item/1005010786180634.html",
        )


class TestPlannedPages(unittest.TestCase):
    """盲盒式扫描深度：固定 seed 后落在规定区间。"""

    DEPTH_RANGES = [
        (1, 4, 8),
        (10, 4, 8),
        (11, 6, 10),
        (30, 6, 10),
        (31, 8, 12),
        (60, 8, 12),
        (61, 10, 14),
        (80, 10, 14),
        (81, 12, 16),
        (100, 12, 16),
        (101, 14, 18),
        (120, 14, 18),
        (121, 16, 18),
        (160, 16, 18),
    ]

    def test_depth_in_range_for_fixed_seed(self):
        for target, lo, hi in self.DEPTH_RANGES:
            for seed in (1, 42, 2026):
                rng = random.Random(seed)
                depth = planned_pages_for(target, rng)
                self.assertGreaterEqual(depth, lo, f"N={target} seed={seed}")
                self.assertLessEqual(depth, hi, f"N={target} seed={seed}")

    def test_depth_covers_full_range_with_many_seeds(self):
        """多 seed 下区间两端都能取到，且不超过 18 页。"""
        for target, lo, hi in self.DEPTH_RANGES:
            depths = {
                planned_pages_for(target, random.Random(seed)) for seed in range(200)
            }
            self.assertEqual(min(depths), lo, f"N={target}")
            self.assertEqual(max(depths), hi, f"N={target}")
            self.assertLessEqual(max(depths), 18)

    def test_same_seed_same_depth(self):
        a = planned_pages_for(100, random.Random(7))
        b = planned_pages_for(100, random.Random(7))
        self.assertEqual(a, b)


class TestFinalizeSample(unittest.TestCase):
    def _pool(self, count: int) -> list[CandidateProduct]:
        return [
            CandidateProduct(
                product_id=str(i),
                title=f"t{i}",
                main_image="",
                product_url=f"https://www.aliexpress.com/item/{i}.html",
                keyword="kw",
                position=i,
            )
            for i in range(1, count + 1)
        ]

    def test_pool_larger_than_target_returns_exactly_n(self):
        samples, partial = finalize_sample(self._pool(120), 100, random.Random(42))
        self.assertEqual(len(samples), 100)
        self.assertFalse(partial)
        self.assertEqual(len({p.product_id for p in samples}), 100)

    def test_pool_smaller_than_target_is_partial(self):
        samples, partial = finalize_sample(self._pool(30), 100, random.Random(42))
        self.assertEqual(len(samples), 30)
        self.assertTrue(partial)

    def test_empty_pool_is_partial(self):
        samples, partial = finalize_sample([], 10, random.Random(1))
        self.assertEqual(samples, [])
        self.assertTrue(partial)

    def test_result_is_shuffled_and_deterministic_with_seed(self):
        pool = self._pool(50)
        s1, _ = finalize_sample(pool, 20, random.Random(99))
        s2, _ = finalize_sample(pool, 20, random.Random(99))
        self.assertEqual([p.product_id for p in s1], [p.product_id for p in s2])
        # 抽样结果不是简单的前 N 个（shuffle 生效）
        head = [str(i) for i in range(1, 21)]
        self.assertNotEqual([p.product_id for p in s1], head)


class TestDetermineStatus(unittest.TestCase):
    """状态判定逻辑：完成深度 + 商品数量 → success / partial / failed。"""

    def test_full_depth_and_enough_products_is_success(self):
        self.assertEqual(
            determine_status(False, 200, 10, 10, 100, 100),
            STATUS_SUCCESS,
        )

    def test_full_depth_and_extra_products_is_success(self):
        """候选池大于目标、深度完成 → success。"""
        self.assertEqual(
            determine_status(False, 250, 10, 10, 100, 100),
            STATUS_SUCCESS,
        )

    def test_incomplete_depth_but_enough_products_is_partial(self):
        """深度未完成但商品够 → partial（核心修正点）。"""
        self.assertEqual(
            determine_status(False, 200, 3, 10, 100, 100),
            STATUS_PARTIAL,
        )

    def test_full_depth_but_not_enough_products_is_partial(self):
        """深度完成但商品不足 → partial。"""
        self.assertEqual(
            determine_status(False, 50, 10, 10, 50, 100),
            STATUS_PARTIAL,
        )

    def test_incomplete_depth_and_not_enough_is_partial(self):
        self.assertEqual(
            determine_status(False, 30, 2, 10, 20, 100),
            STATUS_PARTIAL,
        )

    def test_empty_pool_is_failed(self):
        self.assertEqual(
            determine_status(False, 0, 0, 10, 0, 100),
            STATUS_FAILED,
        )

    def test_forced_failed_is_failed(self):
        self.assertEqual(
            determine_status(True, 100, 5, 10, 50, 100),
            STATUS_FAILED,
        )

    def test_forced_failed_even_with_products_is_failed(self):
        """异常强制失败，即使有商品也返回 failed。"""
        self.assertEqual(
            determine_status(True, 200, 10, 10, 100, 100),
            STATUS_FAILED,
        )

    def test_some_products_no_depth_is_partial(self):
        """有商品但 0 页完成（理论上首页响应后即中断）→ partial。"""
        self.assertEqual(
            determine_status(False, 10, 0, 5, 10, 100),
            STATUS_PARTIAL,
        )


if __name__ == "__main__":
    unittest.main()
