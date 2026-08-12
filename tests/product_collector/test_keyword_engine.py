"""最小关键词引擎测试。

覆盖：
1. 分类可加载
2. 每个分类第一项为【大类探索】<英文大类词>
3. 搜索词解析：自定义词原样返回，大类探索解析为英文大类词
4. 随机灵感返回合法分类 + 搜索词
5. 中文→英文映射（resolve_cn_keyword）
6. 批量解析（resolve_keywords_batch）
7. 大类探索映射
8. 自定义词占位
"""

import unittest

from profit_accounting_26.product_collector import keyword_engine


class TestCategories(unittest.TestCase):
    def test_categories_not_empty(self):
        categories = keyword_engine.list_categories()
        self.assertGreater(len(categories), 0)
        self.assertTrue(all(c.strip() for c in categories))

    def test_every_category_has_en_word_and_items(self):
        for category in keyword_engine.list_categories():
            self.assertTrue(keyword_engine.category_en_word(category), category)
            terms = keyword_engine.category_terms(category)
            self.assertGreater(len(terms), 1, category)


class TestCategoryTerms(unittest.TestCase):
    def test_first_item_is_category_exploration(self):
        for category in keyword_engine.list_categories():
            terms = keyword_engine.category_terms(category)
            display, actual = terms[0]
            en = keyword_engine.category_en_word(category)
            self.assertEqual(display, f"【大类探索】{en}")
            self.assertEqual(actual, en)

    def test_specific_terms_follow_first_item(self):
        category = keyword_engine.list_categories()[0]
        terms = keyword_engine.category_terms(category)
        for display, actual in terms[1:]:
            self.assertFalse(display.startswith("【大类探索】"))
            self.assertEqual(display, actual)
            self.assertTrue(display.strip())


class TestResolveKeyword(unittest.TestCase):
    def test_custom_keyword_returned_as_is(self):
        self.assertEqual(keyword_engine.resolve_search_keyword("women bag"), "women bag")

    def test_custom_keyword_stripped(self):
        self.assertEqual(keyword_engine.resolve_search_keyword("  led strip "), "led strip")

    def test_explore_prefix_resolved_to_en_word(self):
        self.assertEqual(
            keyword_engine.resolve_search_keyword("【大类探索】home and desk decor"),
            "home and desk decor",
        )


class TestRandomIdea(unittest.TestCase):
    def test_returns_valid_category_and_term(self):
        categories = set(keyword_engine.list_categories())
        for seed in range(20):
            import random

            category, term = keyword_engine.random_idea(random.Random(seed))
            self.assertIn(category, categories)
            displays = [d for d, _a in keyword_engine.category_terms(category)]
            self.assertIn(term, displays)
            self.assertFalse(term.startswith("【大类探索】"))


class TestResolveCnKeyword(unittest.TestCase):
    def test_builtin_cn_maps_to_en(self):
        _display, actual = keyword_engine.resolve_cn_keyword("包包防尘袋")
        self.assertEqual(actual, "dust bag for handbags")

    def test_custom_word_returned_as_is(self):
        _display, actual = keyword_engine.resolve_cn_keyword("我自己输入的搜索词")
        self.assertEqual(actual, "我自己输入的搜索词")

    def test_explore_cn_maps_to_en_category(self):
        _display, actual = keyword_engine.resolve_cn_keyword(
            "【大类探索】女性家居桌面美化"
        )
        self.assertEqual(actual, "home and desk decor")

    def test_empty_returns_empty(self):
        self.assertEqual(keyword_engine.resolve_cn_keyword(""), ("", ""))
        self.assertEqual(keyword_engine.resolve_cn_keyword(None), ("", ""))

    def test_strips_whitespace(self):
        _display, actual = keyword_engine.resolve_cn_keyword("  包包防尘袋  ")
        self.assertEqual(actual, "dust bag for handbags")


class TestResolveKeywordsBatch(unittest.TestCase):
    def test_single_builtin(self):
        result = keyword_engine.resolve_keywords_batch("包包防尘袋")
        self.assertEqual(len(result), 1)
        show, actual = result[0]
        self.assertEqual(show, "dust bag for handbags")
        self.assertEqual(actual, "dust bag for handbags")

    def test_single_custom(self):
        result = keyword_engine.resolve_keywords_batch("我自己输入的搜索词")
        self.assertEqual(len(result), 1)
        show, actual = result[0]
        self.assertEqual(show, "—（原词搜索）")
        self.assertEqual(actual, "我自己输入的搜索词")

    def test_mixed_builtin_and_custom(self):
        text = "包包防尘袋；我自己输入的词；包包内胆包"
        result = keyword_engine.resolve_keywords_batch(text)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], ("dust bag for handbags", "dust bag for handbags"))
        self.assertEqual(result[1], ("—（原词搜索）", "我自己输入的词"))
        self.assertEqual(result[2], ("handbag organizer insert", "handbag organizer insert"))

    def test_explore_term(self):
        text = "【大类探索】女性家居桌面美化"
        result = keyword_engine.resolve_keywords_batch(text)
        self.assertEqual(len(result), 1)
        show, actual = result[0]
        self.assertEqual(show, "home and desk decor")
        self.assertEqual(actual, "home and desk decor")

    def test_empty_input(self):
        self.assertEqual(keyword_engine.resolve_keywords_batch(""), [])
        self.assertEqual(keyword_engine.resolve_keywords_batch(None), [])
        self.assertEqual(keyword_engine.resolve_keywords_batch("  "), [])

    def test_semicolon_separated_preserves_order(self):
        text = "词A；词B；词C"
        result = keyword_engine.resolve_keywords_batch(text)
        actuals = [actual for _show, actual in result]
        self.assertEqual(actuals, ["词A", "词B", "词C"])

    def test_multiple_builtin_mapping(self):
        text = "芭蕾风蝴蝶结包挂；包包防尘袋"
        result = keyword_engine.resolve_keywords_batch(text)
        shows = [show for show, _actual in result]
        self.assertEqual(
            shows,
            ["coquette bow bag charm", "dust bag for handbags"],
        )


class TestCategoryCnTerms(unittest.TestCase):
    """新 UI 弹窗专用中文显示接口。"""

    def test_first_item_is_cn_category_exploration(self):
        for category in keyword_engine.list_categories():
            terms = keyword_engine.category_cn_terms(category)
            display, actual = terms[0]
            self.assertEqual(display, f"【大类探索】{category}")
            self.assertEqual(actual, keyword_engine.category_en_word(category))

    def test_terms_are_cn_display_with_en_actual(self):
        """显示为中文原词，实际值为全局 canonical 英文搜索词。"""
        for category in keyword_engine.list_categories():
            terms = keyword_engine.category_cn_terms(category)
            for display, actual in terms[1:]:
                self.assertFalse(display.startswith("【大类探索】"))
                self.assertTrue(actual)
                # 中文显示词必须是词库内置词，不能回退为原词搜索
                self.assertIn(display, keyword_engine._CN_TO_EN)
                # canonical 统一：弹窗词条实际值 == 全局解析值
                _show, resolved = keyword_engine.resolve_cn_keyword(display)
                self.assertEqual(actual, resolved)
                self.assertEqual(actual, keyword_engine._CN_TO_EN[display])

    def test_duplicate_cn_word_uses_canonical_mapping(self):
        """同一中文词在多分类英文不同时，统一使用全局 canonical 映射。

        词库中真实存在的重复词：蕾丝床头防尘罩
        （女性家居桌面美化 / 大学宿舍公寓装饰，英文值不同）。
        """
        duplicate = "蕾丝床头防尘罩"
        distinct_ens = {
            en
            for d in keyword_engine.DIRECTIONS
            for cn, en in d["items"]
            if cn == duplicate
        }
        self.assertGreater(
            len(distinct_ens), 1,
            "需要词库中真实存在、跨分类英文不同的重复中文词",
        )
        canonical = keyword_engine._CN_TO_EN[duplicate]
        # 从任意包含该词的分类取得的词条，actual 必须等于 canonical
        seen = False
        for category in keyword_engine.list_categories():
            for display, actual in keyword_engine.category_cn_terms(category):
                if display == duplicate:
                    seen = True
                    self.assertEqual(actual, canonical)
        self.assertTrue(seen, f"词库中未找到重复中文词: {duplicate}")
        # 全局解析与弹窗词条一致
        _show, resolved = keyword_engine.resolve_cn_keyword(duplicate)
        self.assertEqual(resolved, canonical)

    def test_old_category_terms_unchanged(self):
        """旧 category_terms() 语义不变（英文显示，第一项为英文大类探索）。"""
        for category in keyword_engine.list_categories():
            terms = keyword_engine.category_terms(category)
            en = keyword_engine.category_en_word(category)
            self.assertEqual(terms[0], (f"【大类探索】{en}", en))


if __name__ == "__main__":
    unittest.main()
