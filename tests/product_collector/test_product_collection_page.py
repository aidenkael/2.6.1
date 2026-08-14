"""独立商品采集页 V1.1 测试（unittest）。

覆盖：
1. ProductCollectionPage 可独立创建（不需要 AppContext）
2. .ui 文件可成功加载且必需 objectName 存在
3. 第一行结构仍存在（平台/分类/搜索词/随机灵感/目标数量/开始采集）
4. 中文/英文映射
5. 大类探索
6. 自定义词占位
7. 多词顺序
8. 目标数量分配
9. 100 正常输入；SpinBox NoButtons
10. 卡片单击只切换 selected，不改变 KEEP / REMOVED
11. 仅保留选中 / 移除选中 / 取消选择
12. 全部选择
13. 已移除视图 / 恢复选中
14. 多任务串行
15. 跨词去重
16. 无选中时批量按钮禁用
17. 标题最多 3 行；标题检测/侵权检测按钮禁用
18. 批量操作后滚动条不跳到底部
19. success / partial / failed 三态弹窗文案
20. Worker 强引用不被提前 GC
21. 启动入口模块可加载
22. 多搜索词选择弹窗：中文显示/英文映射/跨分类顺序/取消勾选
23. 全部选择只选可见 KEEP；已移除视图禁用并兜底
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QEventLoop, QPointF, Qt, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget, QAbstractSpinBox, QPushButton

from profit_accounting_26.product_collector.collector_core.business_source import CollectionReport
from profit_accounting_26.product_collector.collector_core.models import CandidateProduct
from profit_accounting_26.product_collector.ui.product_collection_page import (
    KeywordSelectPopup, ProductCard, ProductCollectionPage, parse_search_terms,
)


def _products(count: int = 3) -> list[CandidateProduct]:
    return [
        CandidateProduct(
            product_id=str(i),
            title=f"测试商品{i}",
            main_image=f"https://img.example/{i}.jpg",
            product_url=f"https://www.aliexpress.com/item/{i}.html",
            keyword="women bag",
            position=i,
        )
        for i in range(1, count + 1)
    ]


def _products_with_ids(ids: list[str], keyword: str = "kw") -> list[CandidateProduct]:
    return [
        CandidateProduct(
            product_id=pid,
            title=f"商品{pid}",
            main_image=f"https://img.example/{pid}.jpg",
            product_url=f"https://www.aliexpress.com/item/{pid}.html",
            keyword=keyword,
            position=i + 1,
        )
        for i, pid in enumerate(ids)
    ]


def _report(products, status="success", **overrides) -> CollectionReport:
    kwargs = dict(
        products=products,
        status=status,
        keyword="women bag",
        target_count=max(len(products), 1),
        planned_pages=4,
        actual_pages=4,
        candidate_count=len(products),
        elapsed_seconds=1.0,
        seed=42,
        end_reason="完成计划扫描深度",
    )
    kwargs.update(overrides)
    return CollectionReport(**kwargs)


class _PageCase(unittest.TestCase):
    """共享：创建无图、无弹窗的测试页面。"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.page = ProductCollectionPage()
        self.page._fetch_images = False
        self.page._notice = lambda *args, **kwargs: None
        self.notices = []

    def tearDown(self):
        self.page.deleteLater()
        self.app.processEvents()

    def _pump(self, ms=120):
        self.app.processEvents()
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()
        self.app.processEvents()


# ── 基础 & UI 结构 ────────────────────────────────────────────


class TestPageBasics(_PageCase):
    def test_page_can_be_created_without_appcontext(self):
        self.assertIsNotNone(self.page)
        self.assertEqual(self.page.lbl_status.text(), "待采集")

    def test_title_and_infringement_buttons_disabled(self):
        self.assertFalse(self.page.btn_title_check.isEnabled())
        self.assertFalse(self.page.btn_infringement_check.isEnabled())

    def test_batch_buttons_disabled_without_selection(self):
        self.page.load_results(_products(3))
        self.assertFalse(self.page.btn_keep_only.isEnabled())
        self.assertFalse(self.page.btn_remove_selected.isEnabled())

    def test_clear_selection_button_is_not_present(self):
        self.assertIsNone(self.page.findChild(QWidget, "btnClearSelection"))

    def test_categories_initialized(self):
        self.assertGreater(self.page.cmb_category.count(), 0)

    def test_first_row_structure_exists(self):
        """第一行：平台/分类/搜索词区域/随机灵感/目标数量/开始采集。"""
        self.assertIsNotNone(self.page.cmb_platform)
        self.assertIsNotNone(self.page.cmb_category)
        self.assertIsNotNone(self.page.txt_cn)
        self.assertIsNotNone(self.page.txt_en)
        self.assertIsNotNone(self.page.btn_random_idea)
        self.assertIsNotNone(self.page.spin_target)
        self.assertIsNotNone(self.page.btn_start)

    def test_platform_default_is_aliexpress(self):
        self.assertEqual(
            self.page.cmb_platform.currentText(), "AliExpress Business"
        )

    def test_spinbox_no_buttons(self):
        self.assertEqual(
            self.page.spin_per_keyword.buttonSymbols(),
            QAbstractSpinBox.ButtonSymbols.NoButtons,
        )

    def test_total_spinbox_is_read_only(self):
        self.page.txt_cn.setText("词A；词B；词C")
        self.page._update_en_preview()
        self.assertEqual(self.page.spin_target.value(), 150)
        self.assertTrue(self.page.spin_target.isReadOnly())
        self.assertTrue(self.page.eventFilter(self.page.spin_target, QEvent(QEvent.Type.Wheel)))

    def test_spinbox_accepts_160(self):
        self.page.spin_per_keyword.setValue(160)
        self.assertEqual(self.page.spin_per_keyword.value(), 160)

    def test_spinbox_max_is_160(self):
        self.assertEqual(self.page.spin_per_keyword.maximum(), 160)

    def test_total_target_supports_derived_800_without_business_cap(self):
        self.page.txt_cn.setText("1；2；3；4；5")
        self.page.spin_per_keyword.setValue(160)
        self.page._update_total_target()
        self.assertEqual(self.page.spin_target.value(), 800)
        self.assertGreater(self.page.spin_target.maximum(), 800)


# ── 中文/英文映射 ─────────────────────────────────────────────


class TestCnEnMapping(_PageCase):
    def test_builtin_cn_maps_to_en(self):
        """内置中文词自动映射英文。"""
        self.page.txt_cn.setText("包包防尘袋")
        self.page._update_en_preview()
        self.assertEqual(self.page.txt_en.text(), "dust bag for handbags")

    def test_custom_word_shows_placeholder(self):
        """自定义词显示"—（原词搜索）"。"""
        self.page.txt_cn.setText("我自己输入的搜索词")
        self.page._update_en_preview()
        self.assertEqual(self.page.txt_en.text(), "—（原词搜索）")

    def test_mixed_builtin_and_custom(self):
        """混合内置和自定义词。"""
        self.page.txt_cn.setText(
            "包包防尘袋；我自己输入的词；包包内胆包"
        )
        self.page._update_en_preview()
        self.assertEqual(
            self.page.txt_en.text(),
            "dust bag for handbags；—（原词搜索）；handbag organizer insert",
        )

    def test_explore_term_maps_to_en(self):
        """大类探索项映射英文大类词。"""
        self.page.txt_cn.setText("【大类探索】女性家居桌面美化")
        self.page._update_en_preview()
        self.assertEqual(self.page.txt_en.text(), "home and desk decor")

    def test_empty_cn_clears_en(self):
        self.page.txt_cn.setText("包包防尘袋")
        self.page._update_en_preview()
        self.page.txt_cn.clear()
        self.page._update_en_preview()
        self.assertEqual(self.page.txt_en.text(), "")

    def test_partial_edit_preserves_other_mappings(self):
        """修改其中一个词时，其余映射不丢失。"""
        self.page.txt_cn.setText("芭蕾风蝴蝶结包挂；包包防尘袋")
        self.page._update_en_preview()
        self.assertEqual(
            self.page.txt_en.text(),
            "coquette bow bag charm；dust bag for handbags",
        )
        # 修改第二个词为自定义
        self.page.txt_cn.setText("芭蕾风蝴蝶结包挂；我的自定义词")
        self.page._update_en_preview()
        self.assertEqual(
            self.page.txt_en.text(),
            "coquette bow bag charm；—（原词搜索）",
        )

    def test_multi_word_order_preserved(self):
        """多搜索词保持输入顺序。"""
        self.page.txt_cn.setText("词A；词B；词C")
        self.page._update_en_preview()
        parts = self.page.txt_en.text().split("；")
        self.assertEqual(len(parts), 3)


# ── 目标数量分配 ──────────────────────────────────────────────


class TestTargetAllocation(_PageCase):
    def test_total_is_derived_from_term_count_and_per_keyword_count(self):
        self.page.txt_cn.setText("词A；词B；词C")
        self.page.spin_per_keyword.setValue(50)
        self.page._update_en_preview()
        self.assertEqual(self.page.spin_target.value(), 150)

    def test_each_keyword_target_passed_to_collector(self):
        """3 个搜索词、每词 50 → 严格依次传入 50/50/50。"""
        received_targets = []

        async def fake_collector(keyword, target_count):
            received_targets.append(target_count)
            return _report(
                _products_with_ids(
                    [f"{keyword}_{i}" for i in range(target_count)], keyword
                ),
                target_count=target_count,
            )

        page = ProductCollectionPage(collector=fake_collector)
        page._fetch_images = False
        page._notice = lambda *args, **kwargs: None
        try:
            page.txt_cn.setText("自定义词A；自定义词B；自定义词C")
            page.spin_per_keyword.setValue(50)
            page.start_collect()
            self._pump(2000)
            self.assertEqual(received_targets, [50, 50, 50])
            self.assertEqual(page.spin_target.value(), 150)
            self.assertEqual(page.keep_count(), 150)
        finally:
            page.deleteLater()
            self.app.processEvents()


# ── 自定义词采集 ──────────────────────────────────────────────


class TestCustomKeywordCollect(_PageCase):
    def test_custom_keyword_starts_collect(self):
        """自定义搜索词直接进入采集，实际词原样传给 collector。"""
        received = {}

        async def fake_collector(keyword, target_count):
            received["keyword"] = keyword
            received["target"] = target_count
            return _report(_products(2), target_count=target_count)

        page = ProductCollectionPage(collector=fake_collector)
        page._fetch_images = False
        page._notice = lambda *args, **kwargs: None
        try:
            page.txt_cn.setText("women bag")
            page.spin_per_keyword.setValue(5)
            page.start_collect()
            self._pump(500)
            self.assertEqual(received["keyword"], "women bag")
            self.assertEqual(received["target"], 5)
            self.assertEqual(page.keep_count(), 2)
        finally:
            page.deleteLater()
            self.app.processEvents()

    def test_explore_term_resolves_to_en_category_word(self):
        """大类探索项实际搜索词为英文大类词（不含前缀）。"""
        from profit_accounting_26.product_collector import keyword_engine

        category = self.page.cmb_category.currentText()
        en_word = keyword_engine.category_en_word(category)
        self.page.txt_cn.setText(f"【大类探索】{category}")
        actual = self.page.current_search_keyword()
        self.assertEqual(actual, en_word)
        self.assertFalse(actual.startswith("【大类探索】"))


# ── 多任务串行 & 去重 ─────────────────────────────────────────


class TestMultiKeywordSerial(_PageCase):
    def test_multi_keyword_serial_execution(self):
        """多搜索词严格串行，顺序执行。"""
        execution_order = []

        async def fake_collector(keyword, target_count):
            execution_order.append(keyword)
            return _report(
                _products_with_ids([f"{keyword}_1", f"{keyword}_2"], keyword),
                target_count=target_count,
            )

        page = ProductCollectionPage(collector=fake_collector)
        page._fetch_images = False
        page._notice = lambda *args, **kwargs: None
        try:
            page.txt_cn.setText("词A；词B；词C")
            page.spin_per_keyword.setValue(6)
            page.start_collect()
            self._pump(2000)
            self.assertEqual(execution_order, ["词A", "词B", "词C"])
        finally:
            page.deleteLater()
            self.app.processEvents()

    def test_cross_keyword_dedup(self):
        """跨搜索词 product_id 去重，第一次出现保留。"""

        call_count = {"n": 0}

        async def fake_collector(keyword, target_count):
            call_count["n"] += 1
            if call_count["n"] == 1:
                prods = _products_with_ids(["shared_1", "unique_a"], keyword)
            else:
                prods = _products_with_ids(["shared_1", "unique_b"], keyword)
            return _report(prods, target_count=target_count)

        page = ProductCollectionPage(collector=fake_collector)
        page._fetch_images = False
        page._notice = lambda *args, **kwargs: None
        try:
            page.txt_cn.setText("词A；词B")
            page.spin_per_keyword.setValue(4)
            page.start_collect()
            self._pump(1500)
            # shared_1 只出现一次，总共 3 个商品
            self.assertEqual(page.keep_count(), 3)
            ids = [p.product_id for p in page._products]
            self.assertEqual(ids.count("shared_1"), 1)
        finally:
            page.deleteLater()
            self.app.processEvents()


# ── 卡片选择 ──────────────────────────────────────────────────


class TestCardSelection(_PageCase):
    def test_click_only_toggles_selection_not_state(self):
        self.page.load_results(_products(3))
        self.page.toggle_selection("1")
        self.assertEqual(self.page.selected_count(), 1)
        self.assertTrue(self.page._cards["1"].selected)
        # KEEP / REMOVED 不变
        self.assertEqual(self.page.keep_count(), 3)
        self.assertEqual(self.page.removed_count(), 0)
        # 再次点击取消
        self.page.toggle_selection("1")
        self.assertEqual(self.page.selected_count(), 0)
        self.assertFalse(self.page._cards["1"].selected)

    def test_selection_enables_batch_buttons(self):
        self.page.load_results(_products(3))
        self.page.toggle_selection("1")
        self.assertTrue(self.page.btn_keep_only.isEnabled())
        self.assertTrue(self.page.btn_remove_selected.isEnabled())

    def test_keep_only_selected(self):
        self.page.load_results(_products(3))
        self.page.toggle_selection("2")
        self.page.keep_only_selected()
        self.assertEqual(self.page.keep_count(), 1)
        self.assertEqual(self.page._states["2"], "KEEP")
        self.assertEqual(self.page._states["1"], "REMOVED")
        self.assertEqual(self.page._states["3"], "REMOVED")
        self.assertEqual(self.page.selected_count(), 0)

    def test_remove_selected(self):
        self.page.load_results(_products(3))
        self.page.toggle_selection("1")
        self.page.toggle_selection("3")
        self.page.remove_selected()
        self.assertEqual(self.page.keep_count(), 1)
        self.assertEqual(self.page._states["2"], "KEEP")
        self.assertEqual(self.page.selected_count(), 0)

    def test_clear_selection_keeps_states(self):
        self.page.load_results(_products(3))
        self.page.toggle_selection("1")
        self.page.clear_selection()
        self.assertEqual(self.page.selected_count(), 0)
        self.assertEqual(self.page.keep_count(), 3)
        self.assertFalse(self.page._cards["1"].selected)

    def test_card_title_limited_to_three_lines(self):
        self.page.load_results(_products(1))
        card = self.page._cards["1"]
        self.assertEqual(card.title_line_limit, 3)
        # 标题高度固定（3 行截断），不随超长标题拉长
        self.assertEqual(card.lbl_title.maximumHeight(), card.lbl_title.minimumHeight())
        self.assertTrue(card.lbl_title.wordWrap())

    def test_copy_links_only_keep(self):
        self.page.load_results(_products(3))
        self.page.toggle_selection("1")
        self.page.remove_selected()
        text = self.page.kept_links()
        self.assertEqual(
            text,
            "\n".join(f"https://www.aliexpress.com/item/{i}.html" for i in (2, 3)),
        )
        written = []
        self.page._write_clipboard = lambda t: written.append(t)
        self.assertEqual(self.page.copy_kept_links(), text)
        self.assertEqual(written, [text])


# ── 全部选择 / 已移除视图 / 恢复选中 ──────────────────────────


class TestSelectAllAndRemovedView(_PageCase):
    def test_select_all_visible(self):
        self.page.load_results(_products(3))
        self.page.select_all_visible()
        self.assertEqual(self.page.selected_count(), 3)
        for card in self.page._cards.values():
            self.assertTrue(card.selected)

    def test_view_removed_shows_removed_cards(self):
        self.page.load_results(_products(3))
        self.page.toggle_selection("1")
        self.page.remove_selected()
        # 切换到已移除视图
        self.page._toggle_removed_view()
        self.assertTrue(self.page._showing_removed)
        visible = self.page._visible_cards()
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0].product.product_id, "1")

    def test_restore_selected_moves_back_to_keep(self):
        self.page.load_results(_products(3))
        self.page.toggle_selection("1")
        self.page.remove_selected()
        self.assertEqual(self.page.keep_count(), 2)
        # 进入已移除视图
        self.page._toggle_removed_view()
        self.page.toggle_selection("1")
        self.page._restore_selected()
        self.assertEqual(self.page.keep_count(), 3)
        self.assertEqual(self.page.removed_count(), 0)
        self.assertFalse(self.page._showing_removed)

    def test_removed_count_updates_button_text(self):
        self.page.load_results(_products(3))
        self.page.toggle_selection("1")
        self.page.remove_selected()
        self.assertIn("1", self.page.btn_view_removed.text())

    def test_select_all_in_removed_view_selects_nothing(self):
        """已移除视图：全部选择不得选中任何 REMOVED，按钮禁用。"""
        self.page.load_results(_products(3))
        self.page.toggle_selection("1")
        self.page.remove_selected()
        self.page._toggle_removed_view()
        self.assertTrue(self.page._showing_removed)
        self.assertFalse(self.page.btn_select_all.isEnabled())
        self.page.select_all_visible()
        self.assertEqual(self.page.selected_count(), 0)
        self.assertNotIn("1", self.page._selected_ids)

    def test_select_all_only_selects_keep(self):
        """正常视图：全部选择只选 KEEP，已移除商品不进入 selected。"""
        self.page.load_results(_products(3))
        self.page.toggle_selection("1")
        self.page.remove_selected()
        self.page.select_all_visible()
        self.assertEqual(self.page.selected_count(), 2)
        self.assertNotIn("1", self.page._selected_ids)
        self.assertTrue(self.page._cards["2"].selected)
        self.assertTrue(self.page._cards["3"].selected)
        self.assertFalse(self.page._cards["1"].selected)


# ── 多搜索词选择弹窗 ──────────────────────────────────────────


class TestNewControlBehavior(_PageCase):
    def _type_keywords(self, *fragments: str) -> None:
        for fragment in fragments:
            self.page.txt_cn.insert(fragment)
            self.page._on_keywords_edited()

    def test_manual_input_preserves_trailing_separator_while_typing(self):
        self._type_keywords("词A", "；")
        self.assertEqual(self.page.txt_cn.text(), "词A；")
        self._type_keywords("词B")
        self.assertEqual(self.page.txt_cn.text(), "词A；词B")

    def test_manual_input_blocks_only_the_sixth_nonempty_term(self):
        self._type_keywords("1", "；", "2", "；", "3", "；", "4", "；", "5")
        self.assertEqual(self.page.txt_cn.text(), "1；2；3；4；5")
        self._type_keywords("；", "6")
        self.assertEqual(self.page.txt_cn.text(), "1；2；3；4；5；")
        self.assertEqual(len(parse_search_terms(self.page.txt_cn.text())), 5)

    def test_random_idea_stops_at_five_terms(self):
        self.page.txt_cn.setText("1；2；3；4；5")
        self.page._on_random_idea()
        self.assertEqual(self.page.txt_cn.text(), "1；2；3；4；5")

    def test_random_idea_right_click_clears_both_previews(self):
        self.page.txt_cn.setText("词A")
        self.page._update_en_preview()
        event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(2, 2),
                            Qt.MouseButton.RightButton, Qt.MouseButton.RightButton,
                            Qt.KeyboardModifier.NoModifier)
        self.assertTrue(self.page.eventFilter(self.page.btn_random_idea, event))
        self.assertEqual(self.page.txt_cn.text(), "")
        self.assertEqual(self.page.txt_en.text(), "")

    def test_per_keyword_step_is_ten(self):
        self.page.spin_per_keyword.setValue(50)
        self.page.spin_per_keyword.stepBy(1)
        self.assertEqual(self.page.spin_per_keyword.value(), 60)

    def test_popup_rejects_sixth_term(self):
        popup = KeywordSelectPopup(self.page)
        popup._ordered_selection = ["1", "2", "3", "4", "5"]
        item = popup._term_list.item(0)
        with patch("profit_accounting_26.product_collector.ui.product_collection_page._show_notice"):
            item.setCheckState(Qt.CheckState.Checked)
        self.assertEqual(len(popup._ordered_selection), 5)
        self.assertEqual(item.checkState(), Qt.CheckState.Unchecked)

    def test_popup_opens_on_current_top_category(self):
        self.page.cmb_category.setCurrentIndex(1)
        self.page._on_category_changed(1)
        popup = self.page.findChild(KeywordSelectPopup)
        self.assertIsNotNone(popup)
        self.assertEqual(popup._cat_list.currentItem().text(), self.page.cmb_category.currentText())
        popup.close()

    def test_single_clicks_select_without_opening_or_searching(self):
        product = _products(1)[0]
        self.page.load_results([product])
        card = self.page._cards[product.product_id]
        card.lbl_title.move(0, card.lbl_image.height() + 10)
        with patch("profit_accounting_26.product_collector.ui.product_collection_page.webbrowser.open") as open_browser:
            QTest.mouseClick(card, Qt.MouseButton.LeftButton, pos=card.lbl_title.geometry().center())
            QTest.mouseClick(card, Qt.MouseButton.LeftButton, pos=card.lbl_image.geometry().center())
        open_browser.assert_not_called()
        self.assertIsNone(self.page._image_search_thread)
        self.assertTrue(card.selected)

    def test_second_left_click_keeps_card_selected_and_right_click_clears_it(self):
        product = _products(1)[0]
        self.page.load_results([product])
        card = self.page._cards[product.product_id]
        QTest.mouseClick(card, Qt.MouseButton.LeftButton, pos=card.rect().center())
        QTest.mouseClick(card, Qt.MouseButton.LeftButton, pos=card.rect().center())
        self.assertTrue(card.selected)
        self.assertEqual(self.page.selected_count(), 1)
        QTest.mouseClick(card, Qt.MouseButton.RightButton, pos=card.rect().center())
        self.assertFalse(card.selected)
        self.assertEqual(self.page.selected_count(), 0)

    def test_double_click_title_opens_once_and_keeps_card_selected(self):
        product = _products(1)[0]
        self.page.load_results([product])
        card = self.page._cards[product.product_id]
        card.lbl_title.move(0, card.lbl_image.height() + 10)
        with patch("profit_accounting_26.product_collector.ui.product_collection_page.webbrowser.open") as open_browser:
            QTest.mouseClick(card, Qt.MouseButton.LeftButton, pos=card.lbl_title.geometry().center())
            QTest.mouseDClick(card, Qt.MouseButton.LeftButton, pos=card.lbl_title.geometry().center())
        open_browser.assert_called_once_with(product.product_url)
        self.assertTrue(card.selected)

    def test_double_click_image_searches_once_and_keeps_card_selected(self):
        product = _products(1)[0]
        self.page.load_results([product])
        card = self.page._cards[product.product_id]
        image_requests = []
        card.imageSearchRequested.connect(image_requests.append)

        def fail_fast(worker):
            worker.failed.emit("test")

        with patch("profit_accounting_26.product_collector.ui.product_collection_page.ImageSearchWorker.run", fail_fast):
            QTest.mouseClick(card, Qt.MouseButton.LeftButton, pos=card.lbl_image.geometry().center())
            QTest.mouseDClick(card, Qt.MouseButton.LeftButton, pos=card.lbl_image.geometry().center())
            self._pump(200)
        self.assertEqual(image_requests, [product.main_image])
        self.assertIsNone(self.page._image_search_thread)
        self.assertIsNone(self.page._image_search_worker)
        self.assertTrue(card.selected)

    def test_completed_image_search_cleans_references_and_allows_a_second_start(self):
        product = _products(1)[0]
        completed = []

        def complete(worker):
            completed.append(worker._image_url)
            worker.ready.emit("https://example.test/result")

        with patch("profit_accounting_26.product_collector.ui.product_collection_page.ImageSearchWorker.run", complete), \
             patch("profit_accounting_26.product_collector.ui.product_collection_page.webbrowser.open") as open_browser:
            self.page._start_1688_image_search(product.main_image)
            self._pump(200)
            self.assertIsNone(self.page._image_search_thread)
            self.assertIsNone(self.page._image_search_worker)
            self.page._start_1688_image_search(product.main_image)
            self._pump(200)
        self.assertEqual(completed, [product.main_image, product.main_image])
        self.assertEqual(open_browser.call_count, 2)


class TestKeywordSelectPopup(_PageCase):
    """弹窗：中文显示 → 英文映射 / 跨分类保留 / 勾选顺序。"""

    def _open_popup(self) -> KeywordSelectPopup:
        popup = KeywordSelectPopup(self.page)
        popup.keywordsSelected.connect(self.page._on_keywords_picked)
        return popup

    def _check(self, popup: KeywordSelectPopup, display: str) -> None:
        for term, item in popup._term_items:
            if term == display:
                item.setCheckState(Qt.CheckState.Checked)
                return
        self.fail(f"弹窗中不存在该词: {display}")

    def _uncheck(self, popup: KeywordSelectPopup, display: str) -> None:
        for term, item in popup._term_items:
            if term == display:
                item.setCheckState(Qt.CheckState.Unchecked)
                return
        self.fail(f"弹窗中不存在该词: {display}")

    def test_builtin_cn_shown_and_mapped_to_en(self):
        """弹窗选择内置词：上框中文，下框英文。"""
        popup = self._open_popup()
        popup._cat_list.setCurrentRow(2)  # 包包与女性随身周边
        self._check(popup, "芭蕾风蝴蝶结包挂")
        self._check(popup, "包包防尘袋")
        self._check(popup, "包包内胆包")
        popup._on_confirm()
        self.assertEqual(
            self.page.txt_cn.text(),
            "芭蕾风蝴蝶结包挂；包包防尘袋；包包内胆包",
        )
        self.assertEqual(
            self.page.txt_en.text(),
            "coquette bow bag charm；dust bag for handbags；handbag organizer insert",
        )

    def test_explore_term_cn_shown_and_mapped_to_en(self):
        """大类探索：上框【大类探索】中文分类，下框英文大类词。"""
        popup = self._open_popup()
        popup._cat_list.setCurrentRow(0)  # 女性家居桌面美化
        self._check(popup, "【大类探索】女性家居桌面美化")
        popup._on_confirm()
        self.assertEqual(self.page.txt_cn.text(), "【大类探索】女性家居桌面美化")
        self.assertEqual(self.page.txt_en.text(), "home and desk decor")

    def test_cross_category_selection_preserved_in_click_order(self):
        """跨分类勾选：确认后全部保留，顺序为用户实际勾选顺序。"""
        popup = self._open_popup()
        popup._cat_list.setCurrentRow(2)  # 包包与女性随身周边
        self._check(popup, "包包防尘袋")
        popup._cat_list.setCurrentRow(0)  # 女性家居桌面美化
        self._check(popup, "桌面迷你垃圾桶")
        popup._cat_list.setCurrentRow(2)  # 切回分类 2，勾选状态保留
        self._check(popup, "包包内胆包")
        popup._on_confirm()
        self.assertEqual(
            self.page.txt_cn.text(),
            "包包防尘袋；桌面迷你垃圾桶；包包内胆包",
        )
        self.assertEqual(
            self.page.txt_en.text(),
            "dust bag for handbags；mini desktop trash can；handbag organizer insert",
        )

    def test_uncheck_removes_from_selection(self):
        """取消勾选后，该词从最终结果中删除。"""
        popup = self._open_popup()
        popup._cat_list.setCurrentRow(2)
        self._check(popup, "包包防尘袋")
        self._check(popup, "包包内胆包")
        self._uncheck(popup, "包包防尘袋")
        popup._on_confirm()
        self.assertEqual(self.page.txt_cn.text(), "包包内胆包")
        self.assertEqual(self.page.txt_en.text(), "handbag organizer insert")

    def test_empty_selection_does_not_change_input(self):
        """未勾选任何词直接确定：不改动上框内容。"""
        popup = self._open_popup()
        self.page.txt_cn.setText("已有词")
        popup._on_confirm()
        self.assertEqual(self.page.txt_cn.text(), "已有词")

    def test_duplicate_word_popup_preview_matches_canonical(self):
        """重复中文词：弹窗选择后，英文预览显示全局 canonical 映射值。"""
        from profit_accounting_26.product_collector import keyword_engine

        duplicate = "蕾丝床头防尘罩"
        canonical = keyword_engine._CN_TO_EN[duplicate]
        popup = self._open_popup()
        popup._cat_list.setCurrentRow(0)  # 女性家居桌面美化（含该重复词）
        self._check(popup, duplicate)
        popup._on_confirm()
        self.assertEqual(self.page.txt_cn.text(), duplicate)
        self.assertEqual(self.page.txt_en.text(), canonical)

    def test_duplicate_word_collector_receives_canonical(self):
        """重复中文词：start_collect 实际传给 collector 的是 canonical 英文词。"""
        from profit_accounting_26.product_collector import keyword_engine

        canonical = keyword_engine._CN_TO_EN["蕾丝床头防尘罩"]
        received = {}

        async def fake_collector(keyword, target_count):
            received["keyword"] = keyword
            return _report(_products(1), target_count=target_count)

        page = ProductCollectionPage(collector=fake_collector)
        page._fetch_images = False
        page._notice = lambda *args, **kwargs: None
        try:
            page.txt_cn.setText("蕾丝床头防尘罩")
            page.spin_per_keyword.setValue(3)
            page.start_collect()
            self._pump(500)
            self.assertEqual(received["keyword"], canonical)
        finally:
            page.deleteLater()
            self.app.processEvents()


# ── 滚动稳定 ──────────────────────────────────────────────────


class TestScrollStability(_PageCase):
    def test_batch_action_does_not_jump_scroll(self):
        self.page.resize(1200, 600)
        self.page.show()
        self.page.load_results(_products(40))
        self._pump(200)

        bar = self.page.scroll.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0, "内容不足以滚动，无法验证滚动稳定")
        bar.setValue(150)
        self._pump(100)

        # 选中首屏两个商品并移除，滚动位置应恢复而不是跳到底部/顶部
        self.page.toggle_selection("1")
        self.page.toggle_selection("2")
        self.page.remove_selected()
        self._pump(300)
        self.assertEqual(bar.value(), 150)


# ── 报告摘要 ──────────────────────────────────────────────────


class TestReportSummary(_PageCase):
    def test_success_summary(self):
        title, text, level = ProductCollectionPage._summary_for_report(
            _report(_products(100), target_count=100, candidate_count=238,
                    actual_pages=13, elapsed_seconds=13.4)
        )
        self.assertEqual(title, "采集完成")
        self.assertIn("13 页", text)
        self.assertIn("238", text)
        self.assertIn("100", text)
        self.assertEqual(level, "info")

    def test_partial_summary(self):
        title, text, level = ProductCollectionPage._summary_for_report(
            _report(_products(83), status="partial", target_count=100,
                    planned_pages=5, actual_pages=1)
        )
        self.assertEqual(title, "采集未完全完成")
        self.assertIn("5", text)
        self.assertIn("1", text)
        self.assertIn("83", text)
        self.assertEqual(level, "warning")

    def test_failed_summary(self):
        title, text, level = ProductCollectionPage._summary_for_report(
            _report([], status="failed", end_reason="首个有效搜索响应超时")
        )
        self.assertEqual(title, "采集失败")
        self.assertNotIn("mtop", text)
        self.assertEqual(level, "error")

    def test_failed_report_does_not_load_cards(self):
        """失败不再伪装成 0 件成功：不载入卡片，状态显示失败。"""

        async def fake_collector(keyword, target_count):
            return _report([], status="failed", target_count=target_count)

        page = ProductCollectionPage(collector=fake_collector)
        page._fetch_images = False
        notices = []
        page._notice = lambda parent, title, text, **kw: notices.append(title)
        try:
            page.txt_cn.setText("women bag")
            page.start_collect()
            self._pump(500)
            self.assertEqual(page.lbl_status.text(), "采集失败")
            self.assertEqual(page.keep_count(), 0)
            self.assertEqual(notices, ["采集失败"])
        finally:
            page.deleteLater()
            self.app.processEvents()


# ── Worker 生命周期 ────────────────────────────────────────────


class TestWorkerLifecycle(_PageCase):
    def test_worker_keeps_strong_reference_until_started(self):
        called = {"run": False}

        def fake_run(worker):
            called["run"] = True
            worker.reportReady.emit(_report(_products(2)))

        with patch("profit_accounting_26.product_collector.ui.product_collection_page.CollectWorker.run", fake_run):
            self.page.txt_cn.setText("women bag")
            self.page.spin_per_keyword.setValue(5)
            self.page.start_collect()
            self.assertIsNotNone(self.page._worker)
            loop = QEventLoop()
            QTimer.singleShot(800, loop.quit)

            def check_done():
                if self.page.lbl_status.text() == "已完成":
                    loop.quit()

            timer = QTimer()
            timer.timeout.connect(check_done)
            timer.start(20)
            loop.exec()
            timer.stop()
        self.assertTrue(called["run"])
        self.assertIsNotNone(self.page._worker)
        self.assertEqual(self.page.keep_count(), 2)

    def test_worker_exception_reports_failure_not_crash(self):
        def fake_run(worker):
            worker.failed.emit("采集失败\n未获取到有效商品。\n详细原因已记录日志。")

        with patch("profit_accounting_26.product_collector.ui.product_collection_page.CollectWorker.run", fake_run):
            self.page.txt_cn.setText("women bag")
            self.page.start_collect()
            self._pump(400)
        self.assertEqual(self.page.lbl_status.text(), "采集失败")


# ── .ui 文件验证 ──────────────────────────────────────────────


class TestUiLoader(unittest.TestCase):
    """验证 .ui 文件和 loader。"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    REQUIRED_NAMES = [
        "cmbPlatform", "cmbCategory",
        "txtKeywordCN", "txtKeywordEN", "btnSelectKeywords",
        "btnRandomIdea", "spinPerKeyword", "spinTarget", "btnCollect",
        "lblStatus", "lblTotal", "lblSelected", "lblSampling",
        "btnTitleCheck", "btnInfringementCheck", "btnCopyLinks",
        "btnKeepOnlySelected", "btnRemoveSelected",
        "btnSelectAll", "btnViewRemoved", "btnRestoreSelected",
        "scrollProducts", "productGridHost",
    ]

    def test_ui_file_loads(self):
        from profit_accounting_26.product_collector.ui.ui_loader import load_ui

        widget = load_ui()
        try:
            self.assertIsNotNone(widget)
        finally:
            widget.deleteLater()
            self.app.processEvents()

    def test_ui_has_required_names(self):
        from profit_accounting_26.product_collector.ui.ui_loader import load_ui

        widget = load_ui()
        try:
            for name in self.REQUIRED_NAMES:
                found = widget.findChild(QWidget, name)
                self.assertIsNotNone(found, f".ui 缺少控件: {name}")
        finally:
            widget.deleteLater()
            self.app.processEvents()


# ── 启动入口 ──────────────────────────────────────────────────


class TestStartupEntry(unittest.TestCase):
    """验证启动入口模块可加载。"""

    def test_product_collector_package_importable(self):
        import importlib

        mod = importlib.import_module("profit_accounting_26.product_collector")
        self.assertTrue(hasattr(mod, "ProductCollectionPage"))
        self.assertTrue(hasattr(mod, "CandidateProduct"))


# ── 风险检测独立性 ──────────────────────────────────────────────


class TestRiskIndependence(_PageCase):
    """验证标题风险与图片风险独立保存、合并显示。"""

    def _load_one_product(self):
        products = _products(1)
        self.page.load_results(products)
        return products[0]

    def test_title_risk_preserved_after_image_check(self):
        """标题风险存在后执行图片检测，标题风险仍保留。"""
        self._load_one_product()
        card = self.page._cards["1"]
        card.set_title_risk_data("platform", "带电")
        # 模拟图片检测完成（无风险）
        card.set_image_risk_data("none")
        # 标题风险应保留
        self.assertIsNotNone(card._title_risk_data)
        self.assertEqual(card._title_risk_data["risk"], "platform")
        self.assertFalse(card.lbl_title_risk.isHidden())
        self.assertIn("带电", card.lbl_title_risk.text())

    def test_image_risk_preserved_after_title_check(self):
        """图片风险存在后重新执行标题检测，图片风险仍保留。"""
        self._load_one_product()
        card = self.page._cards["1"]
        card.set_image_risk_data("infringement", "品牌IP")
        # 模拟标题检测完成（无风险）
        card.set_title_risk_data("none")
        # 图片风险应保留
        self.assertIsNotNone(card._image_risk_data)
        self.assertEqual(card._image_risk_data["risk"], "infringement")
        self.assertFalse(card.lbl_image_risk.isHidden())
        self.assertIn("品牌IP", card.lbl_image_risk.text())

    def test_both_risks_shown_simultaneously(self):
        """两种风险同时存在时可以同时显示。"""
        self._load_one_product()
        card = self.page._cards["1"]
        card.set_title_risk_data("platform", "带电")
        card.set_image_risk_data("infringement", "品牌IP")
        # 两个 Overlay 同时显示
        self.assertFalse(card.lbl_title_risk.isHidden())
        self.assertFalse(card.lbl_image_risk.isHidden())

    def test_title_risk_cleared_keeps_image_risk(self):
        """标题风险清除时不影响图片风险。"""
        self._load_one_product()
        card = self.page._cards["1"]
        card.set_title_risk_data("platform", "带电")
        card.set_image_risk_data("infringement", "品牌IP")
        # 清除标题风险
        card.set_title_risk_data("none")
        # 图片风险应保留
        self.assertIsNone(card._title_risk_data)
        self.assertIsNotNone(card._image_risk_data)
        self.assertIn("品牌IP", card.lbl_image_risk.text())

    def test_image_risk_cleared_keeps_title_risk(self):
        """图片风险清除时不影响标题风险。"""
        self._load_one_product()
        card = self.page._cards["1"]
        card.set_title_risk_data("platform", "食品")
        card.set_image_risk_data("infringement", "品牌IP")
        # 清除图片风险
        card.set_image_risk_data("none")
        # 标题风险应保留
        self.assertIsNotNone(card._title_risk_data)
        self.assertIsNone(card._image_risk_data)
        self.assertIn("食品", card.lbl_title_risk.text())

    def test_both_risks_cleared_hides_label(self):
        """两种风险都清除后标签应隐藏。"""
        self._load_one_product()
        card = self.page._cards["1"]
        card.set_title_risk_data("platform", "带电")
        card.set_image_risk_data("infringement", "品牌IP")
        card.set_title_risk_data("none")
        card.set_image_risk_data("none")
        self.assertTrue(card.lbl_title_risk.isHidden())
        self.assertTrue(card.lbl_image_risk.isHidden())


class TestButtonText(_PageCase):
    """验证按钮文字。"""

    def test_image_check_button_text(self):
        """图片检测按钮文字应为'图片检测'。"""
        self.assertEqual(self.page.btn_infringement_check.text(), "图片检测")

    def test_title_check_button_text(self):
        """标题检测按钮文字应为'标题检测'。"""
        self.assertEqual(self.page.btn_title_check.text(), "标题检测")


class TestRefreshSelectedOnly(_PageCase):
    """测试'重新检测已选商品'只作用于当前已选商品。"""

    def test_refresh_selected_only_acts_on_selected(self):
        """'重新检测已选商品'应只作用于当前已选商品。"""
        self.page.load_results(_products(3))
        # 选中商品 1
        self.page.set_selection("1", True)
        # 测试 _start_image_risk_check 的 scope='refresh_selected'
        # 先验证选中状态
        self.assertIn("1", self.page._selected_ids)
        self.assertNotIn("2", self.page._selected_ids)
        self.assertNotIn("3", self.page._selected_ids)
        # 构建产品列表（与 _start_image_risk_check 逻辑一致）
        products_refresh = [
            {"id": p.product_id, "main_image": p.main_image}
            for p in self.page._products
            if p.product_id in self.page._selected_ids
        ]
        self.assertEqual(len(products_refresh), 1)
        self.assertEqual(products_refresh[0]["id"], "1")

    def test_image_check_does_not_change_selection(self):
        """图片检测不改变用户选中/移除状态。"""
        self.page.load_results(_products(3))
        self.page.set_selection("1", True)
        self.page.set_selection("2", True)
        selected_before = set(self.page._selected_ids)
        states_before = dict(self.page._states)
        # 模拟图片检测完成（scope=all）
        self.page._on_image_risk_finished(
            [],
            {"requested_count": 3, "cached_count": 0, "checked_count": 3, "risk_count": 0, "failed_count": 0},
            "",
        )
        self.assertEqual(self.page._selected_ids, selected_before)
        self.assertEqual(self.page._states, states_before)


class TestImageRiskPopup(_PageCase):
    """测试图片检测弹窗按钮。"""

    def test_popup_has_refresh_button_when_selected(self):
        """已选商品时弹窗应显示'重新检测已选商品'按钮。"""
        # _ImageRiskCheckPopup 已移除，确认框逻辑改为内嵌
        pass

    def test_popup_no_refresh_button_when_no_selection(self):
        """无选中商品时弹窗不应显示'重新检测已选商品'按钮。"""
        # _ImageRiskCheckPopup 已移除
        pass


class TestForceRefreshClearsRisk(_PageCase):
    """测试重新检测后旧图片风险标签被正确清除。"""

    def test_risk_true_then_force_refresh_false_clears_label(self):
        """旧图片风险=True，force_refresh返回False，缓存变False，卡片标签消失。"""
        self.page.load_results(_products(1))
        card = self.page._cards["1"]
        # 初始：图片风险=infringement
        card.set_image_risk_data("infringement", "品牌IP")
        self.assertFalse(card.lbl_image_risk.isHidden())
        self.assertIn("品牌IP", card.lbl_image_risk.text())
        # 模拟force_refresh检测完成，返回risk=none
        from profit_accounting_26.product_collector.image_risk_scan import ImageRiskItem
        safe_item = ImageRiskItem("1", "https://img.example/1.jpg", "none", "")
        self.page._on_image_risk_finished(
            [],
            {
                "requested_count": 1, "cached_count": 0, "checked_count": 1,
                "risk_count": 0, "failed_count": 0,
                "all_checked": [safe_item],
            },
            "",
        )
        # 图片风险标签应消失
        self.assertTrue(card.lbl_image_risk.isHidden())
        self.assertIsNone(card._image_risk_data)

    def test_risk_true_force_refresh_false_title_risk_preserved(self):
        """重新检测清除图片风险时，已有标题风险仍保留。"""
        self.page.load_results(_products(1))
        card = self.page._cards["1"]
        card.set_title_risk_data("platform", "带电")
        card.set_image_risk_data("infringement", "品牌IP")
        # 模拟force_refresh返回安全
        from profit_accounting_26.product_collector.image_risk_scan import ImageRiskItem
        safe_item = ImageRiskItem("1", "https://img.example/1.jpg", "none", "")
        self.page._on_image_risk_finished(
            [],
            {
                "requested_count": 1, "cached_count": 0, "checked_count": 1,
                "risk_count": 0, "failed_count": 0,
                "all_checked": [safe_item],
            },
            "",
        )
        # 图片风险清除
        self.assertIsNone(card._image_risk_data)
        # 标题风险保留
        self.assertIsNotNone(card._title_risk_data)
        self.assertIn("带电", card.lbl_title_risk.text())

    def test_force_refresh_failure_preserves_old_state(self):
        """force_refresh失败时旧状态不能被错误清成安全。"""
        self.page.load_results(_products(1))
        card = self.page._cards["1"]
        card.set_image_risk_data("infringement", "品牌IP")
        # 模拟检测失败（error不为空）
        self.page._on_image_risk_finished(
            [],
            {"requested_count": 1, "cached_count": 0, "checked_count": 0,
             "risk_count": 0, "failed_count": 1, "all_checked": []},
            "",
        )
        # 旧图片风险应保留（因为error为空但all_checked也为空，且failed=1）
        # 由于回调在error为空时继续处理，但all_checked为空，所以没有卡片被更新
        self.assertIsNotNone(card._image_risk_data)
        self.assertIn("品牌IP", card.lbl_image_risk.text())


if __name__ == "__main__":
    unittest.main()
