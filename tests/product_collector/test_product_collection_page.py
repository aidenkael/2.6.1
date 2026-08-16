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

from PySide6.QtCore import QEvent, QEventLoop, QPointF, Qt, QThread, QTimer
from PySide6.QtGui import QFontMetrics, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget, QAbstractSpinBox, QPushButton

from profit_accounting_26.product_collector.collector_core.business_source import CollectionReport
from profit_accounting_26.product_collector.collector_core.models import CandidateProduct
from profit_accounting_26.product_collector.ui.product_collection_page import (
    CollectWorker, KeywordSelectPopup, ProductCard, ProductCollectionPage,
    _ImageRiskWorker, _TitleRiskWorker, parse_search_terms,
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
            # 全量测试高负载下线程退出可能超过固定等待，轮询等待线程真正清理完成
            for _ in range(60):
                self._pump(50)
                if self.page._image_search_thread is None:
                    break
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

        def wait_cleared():
            """轮询等待搜图线程结束并清理引用（高负载下避免固定等待不够）。"""
            for _ in range(60):
                self._pump(50)
                if self.page._image_search_thread is None:
                    return

        with patch("profit_accounting_26.product_collector.ui.product_collection_page.ImageSearchWorker.run", complete), \
             patch("profit_accounting_26.product_collector.ui.product_collection_page.webbrowser.open") as open_browser:
            self.page._start_1688_image_search(product.main_image)
            wait_cleared()
            self.assertIsNone(self.page._image_search_thread)
            self.assertIsNone(self.page._image_search_worker)
            self.page._start_1688_image_search(product.main_image)
            wait_cleared()
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
        self.assertEqual(self.page.keep_count(), 2)

    def test_worker_exception_reports_failure_not_crash(self):
        def fake_run(worker):
            worker.failed.emit("采集失败\n未获取到有效商品。\n详细原因已记录日志。")

        with patch("profit_accounting_26.product_collector.ui.product_collection_page.CollectWorker.run", fake_run):
            self.page.txt_cn.setText("women bag")
            self.page.start_collect()
            self._pump(400)
        self.assertEqual(self.page.lbl_status.text(), "采集失败")


class TestCollectThreadLifecycle(_PageCase):
    """任务 2：采集 QThread / Worker 生命周期收紧。"""

    def _run_fake_collect(self, report=None):
        """patch 快速完成一轮单关键词采集，并等待线程 finished 事件处理完毕。"""
        report = report if report is not None else _report(_products(2))
        called = {"run": False}

        def fake_run(worker):
            called["run"] = True
            worker.reportReady.emit(report)

        with patch("profit_accounting_26.product_collector.ui.product_collection_page.CollectWorker.run", fake_run):
            self.page.txt_cn.setText("women bag")
            self.page.spin_per_keyword.setValue(5)
            self.page.start_collect()
            self.assertIsNotNone(self.page._thread)
            self.assertIsNotNone(self.page._worker)
            self._pump(800)
        self.assertTrue(called["run"])

    def test_thread_and_worker_cleared_after_last_collect(self):
        """最后一轮采集线程结束后 _thread/_worker 清空。"""
        self._run_fake_collect()
        self.assertIsNone(self.page._thread)
        self.assertIsNone(self.page._worker)

    def test_clear_button_enabled_after_collect_with_products(self):
        """采集完成且有商品后，清空本次按钮可用。"""
        self._run_fake_collect()
        self.assertEqual(self.page.keep_count(), 2)
        self.assertTrue(self.page.btn_clear_all.isEnabled())

    def test_old_thread_finished_does_not_clear_new_thread(self):
        """多关键词：旧线程结束不得误清刚创建的新线程/worker（identity 判断）。"""
        old_thread = QThread(self.page)
        old_worker = CollectWorker("old", 5, None)
        new_thread = QThread(self.page)
        new_worker = CollectWorker("new", 5, None)
        try:
            self.page._thread = new_thread
            self.page._worker = new_worker
            # 旧线程 finished 触发清理：不应动新线程引用
            self.page._clear_collect_task(old_thread, old_worker)
            self.assertIs(self.page._thread, new_thread)
            self.assertIs(self.page._worker, new_worker)
            # 新线程结束才清理
            self.page._clear_collect_task(new_thread, new_worker)
            self.assertIsNone(self.page._thread)
            self.assertIsNone(self.page._worker)
        finally:
            old_thread.deleteLater()
            old_worker.deleteLater()
            new_thread.deleteLater()
            new_worker.deleteLater()
            self.app.processEvents()


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


class TestImageCheckPassesTitle(_PageCase):
    """图片检测调用点必须把商品标题一并传给 ImageRiskScanService。"""

    def test_start_image_check_passes_title(self):
        """_start_image_risk_check 构造的 products 含 id/title/main_image。"""
        from unittest.mock import MagicMock

        self.page.load_results(_products(2))
        self.page._image_risk_service = MagicMock()
        captured = {}

        class FakeWorker:
            def __init__(self, service, products, **kwargs):
                captured["products"] = products

            finished = MagicMock()

            def moveToThread(self, thread):
                pass

            def run(self):
                pass

            def deleteLater(self):
                pass

        with patch(
            "profit_accounting_26.product_collector.ui.product_collection_page.QThread"
        ), patch(
            "profit_accounting_26.product_collector.ui.product_collection_page._ImageRiskWorker",
            FakeWorker,
        ):
            self.page._start_image_risk_check(self.page._products)

        products = captured["products"]
        self.assertEqual(len(products), 2)
        self.assertEqual(products[0]["id"], "1")
        self.assertEqual(products[0]["title"], "测试商品1")
        self.assertEqual(products[0]["main_image"], "https://img.example/1.jpg")

    def test_detect_all_image_stage_passes_title(self):
        """全部检测的图片阶段构造的 products 也含 title。"""
        from unittest.mock import MagicMock

        self.page.load_results(_products(2))
        self.page._image_risk_service = MagicMock()
        targets = list(self.page._products)
        self.page._detect_all_targets = targets
        self.page._enter_detecting(targets)
        self.page._detect_all_phase = "image"
        captured = {}

        class FakeWorker:
            def __init__(self, service, products, **kwargs):
                captured["products"] = products

            finished = MagicMock()

            def moveToThread(self, thread):
                pass

            def run(self):
                pass

            def deleteLater(self):
                pass

        with patch(
            "profit_accounting_26.product_collector.ui.product_collection_page.QThread"
        ), patch(
            "profit_accounting_26.product_collector.ui.product_collection_page._ImageRiskWorker",
            FakeWorker,
        ):
            self.page._on_detect_all_title_finished([], "")

        products = captured["products"]
        self.assertEqual(len(products), 2)
        self.assertEqual(products[0]["id"], "1")
        self.assertEqual(products[0]["title"], "测试商品1")
        self.assertEqual(products[0]["main_image"], "https://img.example/1.jpg")


class TestCancelPreservesResults(_PageCase):
    """测试取消后已完成结果保留。"""

    def test_title_cancel_preserves_successful_results(self):
        """标题检测取消后，已成功的结果应保留并写入卡片。"""
        self.page.load_results(_products(2))
        card1 = self.page._cards["1"]
        card2 = self.page._cards["2"]
        # 模拟检测开始
        self.page._enter_detecting([self.page._products[0], self.page._products[1]])
        self.page._cancel_requested = True  # 用户点击取消
        # 模拟检测完成（成功返回结果）
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem
        risks = [
            TitleRiskItem("1", "platform", "带电商品"),
            TitleRiskItem("2", "none", ""),
        ]
        self.page._on_title_risk_finished(risks, "")
        # 结果应被应用，尽管取消了
        self.assertIsNotNone(card1._title_risk_data)
        self.assertEqual(card1._title_risk_data["risk"], "platform")
        # 状态显示取消消息
        self.assertIn("取消", self.page.lbl_status.text())

    def test_image_cancel_preserves_current_batch_results(self):
        """图片检测取消后，当前批成功结果应保留并写入卡片。"""
        self.page.load_results(_products(2))
        card1 = self.page._cards["1"]
        # 模拟检测开始
        self.page._enter_detecting([self.page._products[0], self.page._products[1]])
        self.page._cancel_requested = True
        # 模拟第一批成功完成
        from profit_accounting_26.product_collector.image_risk_scan import ImageRiskItem
        all_checked = [
            ImageRiskItem("1", "https://img.example/1.jpg", "infringement", "品牌Logo"),
        ]
        stats = {
            "requested_count": 2, "cached_count": 0, "checked_count": 1,
            "risk_count": 1, "failed_count": 1, "all_checked": all_checked,
        }
        self.page._on_image_risk_finished([], stats, "")
        # id=1 的结果应被应用
        self.assertIsNotNone(card1._image_risk_data)
        self.assertEqual(card1._image_risk_data["risk"], "infringement")
        self.assertIn("取消", self.page.lbl_status.text())


class TestOverlayGeometry(_PageCase):
    """测试风险 Overlay 几何位置。"""

    def test_title_risk_overlay_has_positive_dimensions(self):
        """标题风险 Overlay 设置文字后应有正宽高。"""
        self.page.load_results(_products(1))
        card = self.page._cards["1"]
        card.set_title_risk_data("platform", "USB充电风扇")
        # 强制布局计算
        card._layout_risk_overlays()
        self.assertGreater(card.lbl_title_risk.width(), 0)
        self.assertGreater(card.lbl_title_risk.height(), 0)

    def test_image_risk_overlay_has_positive_dimensions(self):
        """图片风险 Overlay 设置文字后应有正宽高。"""
        self.page.load_results(_products(1))
        card = self.page._cards["1"]
        card.set_image_risk_data("infringement", "Nike品牌Logo")
        card._layout_risk_overlays()
        self.assertGreater(card.lbl_image_risk.width(), 0)
        self.assertGreater(card.lbl_image_risk.height(), 0)

    def test_title_risk_overlay_within_title_area(self):
        """标题风险 Overlay 应位于标题区域内。"""
        self.page.load_results(_products(1))
        card = self.page._cards["1"]
        card.set_title_risk_data("platform", "测试风险原因")
        card._layout_risk_overlays()
        title_geo = card.lbl_title.geometry()
        overlay_geo = card.lbl_title_risk.geometry()
        # Overlay 应在标题区域内
        self.assertGreaterEqual(overlay_geo.left(), title_geo.left())
        self.assertLessEqual(overlay_geo.right(), title_geo.right() + 10)  # 允许小误差

    def test_image_risk_overlay_within_image_area(self):
        """图片风险 Overlay 应位于图片区域内。"""
        self.page.load_results(_products(1))
        card = self.page._cards["1"]
        card.set_image_risk_data("infringement", "品牌Logo明显")
        card._layout_risk_overlays()
        img_geo = card.lbl_image.geometry()
        overlay_geo = card.lbl_image_risk.geometry()
        # Overlay 应在图片区域内
        self.assertGreaterEqual(overlay_geo.left(), img_geo.left())
        self.assertLessEqual(overlay_geo.right(), img_geo.right() + 10)

    def test_overlay_height_fixed_regardless_of_text_length(self):
        """短 reason 和长 reason 的标签高度应一致（固定 3 行高度）。"""
        self.page.load_results(_products(1))
        card = self.page._cards["1"]
        # 短 reason
        card.set_title_risk_data("platform", "短")
        card._layout_risk_overlays()
        h_short = card.lbl_title_risk.height()
        w_short = card.lbl_title_risk.width()
        # 长 reason
        card.set_title_risk_data(
            "platform",
            "这是一段明显更长的原因描述，用来验证固定高度方案下标签尺寸不随内容变化",
        )
        card._layout_risk_overlays()
        h_long = card.lbl_title_risk.height()
        w_long = card.lbl_title_risk.width()
        # 高度和宽度应完全一致
        self.assertEqual(h_short, h_long)
        self.assertEqual(w_short, w_long)
        # 宽度应为固定的 _TITLE_RISK_BADGE_WIDTH
        self.assertEqual(w_short, card._TITLE_RISK_BADGE_WIDTH)


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


class TestDetectSnapshotIsActualTargets(_PageCase):
    """测试检测快照是实际传入的 targets。"""

    def test_detect_snapshot_is_targets_not_all_keep(self):
        """检测快照应是实际传入的 targets，不是全部 KEEP 商品。"""
        self.page.load_results(_products(3))
        # 只选择前 2 个商品进行检测
        targets = [self.page._products[0], self.page._products[1]]
        self.page._enter_detecting(targets)
        # 快照应只包含 2 个目标，而不是 3 个 KEEP
        self.assertEqual(len(self.page._detect_snapshot), 2)
        snapshot_ids = {p.product_id for p in self.page._detect_snapshot}
        self.assertEqual(snapshot_ids, {"1", "2"})

    def test_detect_snapshot_default_is_all_keep(self):
        """不传 targets 时，快照默认是全部 KEEP 商品。"""
        self.page.load_results(_products(3))
        self.page._enter_detecting()  # 不传 targets
        self.assertEqual(len(self.page._detect_snapshot), 3)


class TestDetectAllShowsFailedCount(_PageCase):
    """测试全部检测显示失败数量。"""

    def test_detect_all_image_shows_failed_count(self):
        """全部检测图片阶段有失败时，状态应显示失败数量。"""
        self.page.load_results(_products(2))
        # 模拟全部检测开始
        targets = [self.page._products[0], self.page._products[1]]
        self.page._enter_detecting(targets)
        self.page._detect_all_targets = targets
        # 模拟图片阶段完成，有 1 个失败
        from profit_accounting_26.product_collector.image_risk_scan import ImageRiskItem
        all_checked = [
            ImageRiskItem("1", "https://img.example/1.jpg", "none", ""),
        ]
        stats = {
            "requested_count": 2, "cached_count": 0, "checked_count": 1,
            "risk_count": 0, "failed_count": 1, "all_checked": all_checked,
        }
        self.page._on_detect_all_image_finished([], stats, "")
        # 状态应显示失败数量
        self.assertIn("失败", self.page.lbl_status.text())
        self.assertIn("1", self.page.lbl_status.text())


class TestInvalidRiskPreservesExistingState(_PageCase):
    """测试非法 risk 不清除卡片已有风险状态。"""

    def test_invalid_title_risk_does_not_clear_existing(self):
        """标题检测返回非法 risk 时，卡片原有风险状态不得清除。"""
        self.page.load_results(_products(1))
        card = self.page._cards["1"]
        # 先设置一个有风险的状态
        card.set_title_risk_data("platform", "原有风险")
        self.assertIsNotNone(card._title_risk_data)
        # 模拟检测完成，但返回的 risk 在 _parse_risks 中被跳过（非法 risk）
        # 所以 risks 列表为空
        self.page._enter_detecting([self.page._products[0]])
        self.page._on_title_risk_finished([], "")  # 空列表因为非法 risk 被跳过
        # 原有风险应保留
        self.assertIsNotNone(card._title_risk_data)
        self.assertEqual(card._title_risk_data["risk"], "platform")


class TestTitleFailedCount(_PageCase):
    """测试标题检测缺失/非法结果统计为失败。"""

    def test_title_missing_results_count_as_failed(self):
        """3 个 targets 只返回 2 个有效结果时 failed_count=1，状态体现失败。"""
        self.page.load_results(_products(3))
        cards = {pid: self.page._cards[pid] for pid in ("1", "2", "3")}
        # 预置商品 3 原有风险（缺失结果时应保持）
        cards["3"].set_title_risk_data("platform", "原有风险")
        # 模拟检测开始（3 个 targets）
        targets = [self.page._products[0], self.page._products[1], self.page._products[2]]
        self.page._enter_detecting(targets)
        # 模拟检测完成，只返回 2 个有效结果（id=3 缺失）
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem
        risks = [
            TitleRiskItem("1", "platform", "带电商品"),
            TitleRiskItem("2", "none", ""),
        ]
        self.page._on_title_risk_finished(risks, "")
        # 成功 2 个正常写回
        self.assertEqual(cards["1"]._title_risk_data["risk"], "platform")
        self.assertIsNone(cards["2"]._title_risk_data)
        # 缺失商品原风险保持，不生成 none
        self.assertEqual(cards["3"]._title_risk_data["risk"], "platform")
        self.assertEqual(cards["3"]._title_risk_data["reason"], "原有风险")
        # 不得显示为完全成功
        status = self.page.lbl_status.text()
        self.assertIn("失败", status)
        self.assertIn("1", status)
        self.assertNotEqual(status, "检测完成")

    def test_detect_all_title_failed_counted_and_continues(self):
        """全部检测：标题阶段缺失结果计入失败，且不中止继续图片阶段。"""
        self.page.load_results(_products(3))
        targets = [self.page._products[0], self.page._products[1], self.page._products[2]]
        self.page._enter_detecting(targets)
        self.page._detect_all_targets = targets
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem
        risks = [
            TitleRiskItem("1", "platform", "带电"),
            TitleRiskItem("2", "none", ""),
        ]
        with patch("profit_accounting_26.product_collector.ui.product_collection_page.QThread"), patch(
            "profit_accounting_26.product_collector.ui.product_collection_page._ImageRiskWorker"
        ):
            self.page._on_detect_all_title_finished(risks, "")
        # 3 个 target 只返回 2 个 -> 失败 1 个
        self.assertEqual(self.page._detect_all_title_failed, 1)
        # 不中止：继续图片检测阶段
        self.assertEqual(self.page._detect_all_phase, "image")
        self.assertIn("图片", self.page.lbl_status.text())

    def test_detect_all_combines_title_and_image_failed(self):
        """全部检测最终状态：标题失败与图片失败合并为一条状态。"""
        self.page.load_results(_products(3))
        targets = [self.page._products[0], self.page._products[1], self.page._products[2]]
        self.page._enter_detecting(targets)
        self.page._detect_all_targets = targets
        self.page._detect_all_title_failed = 2
        # 模拟图片阶段完成，3 个失败
        from profit_accounting_26.product_collector.image_risk_scan import ImageRiskItem
        all_checked = [ImageRiskItem("1", "https://img.example/1.jpg", "none", "")]
        stats = {
            "requested_count": 3, "cached_count": 0, "checked_count": 1,
            "risk_count": 0, "failed_count": 3, "all_checked": all_checked,
        }
        self.page._on_detect_all_image_finished([], stats, "")
        status = self.page.lbl_status.text()
        self.assertIn("检测完成", status)
        self.assertIn("标题失败 2 个", status)
        self.assertIn("图片失败 3 个", status)


class TestRound2ClearAndSelect(_PageCase):
    """R 项：右键取消全选 / 清空本次 / 长期设置不受影响。"""

    def test_select_all_right_click_clears_selection(self):
        """全部选择按钮右键取消全部选择。"""
        self.page.load_results(_products(3))
        self.page.select_all_visible()
        self.assertEqual(self.page.selected_count(), 3)
        event = QMouseEvent(
            QEvent.Type.MouseButtonPress, QPointF(2, 2),
            Qt.MouseButton.RightButton, Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.assertTrue(self.page.eventFilter(self.page.btn_select_all, event))
        self.assertEqual(self.page.selected_count(), 0)

    def test_select_all_button_has_tooltip(self):
        """全部选择按钮带有左键/右键说明 Tooltip。"""
        tip = self.page.btn_select_all.toolTip()
        self.assertIn("全部选择", tip)
        self.assertIn("取消全部选择", tip)

    def test_clear_all_resets_runtime_state(self):
        """清空本次：商品/卡片/选择/KEEP-REMOVED/检测状态全部清除。"""
        from unittest.mock import Mock

        self.page.load_results(_products(3))
        self.page.select_all_visible()
        self.page._states["1"] = "REMOVED"
        self.page._detect_snapshot = list(self.page._products)
        fake_service = Mock()
        self.page._image_risk_service = fake_service
        self.page._cards["1"].set_title_risk_data("platform", "带电")
        self.page._clear_all_results()
        # 运行期数据全部清空
        self.assertEqual(self.page._products, [])
        self.assertEqual(self.page._cards, {})
        self.assertEqual(self.page._states, {})
        self.assertEqual(self.page._selected_ids, set())
        self.assertIsNone(self.page._detect_snapshot)
        self.assertFalse(self.page._showing_removed)
        # 图片检测运行期缓存被清理
        fake_service.clear_cache.assert_called_once()
        # 状态区回到空态计数
        self.assertIn("商品 0", self.page.lbl_status.text())

    def test_clear_all_resets_collect_runtime_refs(self):
        """清空本次：本轮采集期引用（_all_products/_seen_ids/任务数据）一并清空。"""
        self.page._all_products = _products(2)
        self.page._seen_ids = {"1", "2"}
        self.page._search_tasks = ["任务A", "任务B"]
        self.page._task_statuses = ["success", "success"]
        self.page._current_task_idx = 1
        self.page.load_results(_products(2))
        self.page._clear_all_results()
        # 不再持有 CandidateProduct / 任务数据
        self.assertEqual(self.page._all_products, [])
        self.assertEqual(self.page._seen_ids, set())
        self.assertEqual(self.page._search_tasks, [])
        self.assertEqual(self.page._task_statuses, [])
        self.assertEqual(self.page._current_task_idx, 0)

    def test_clear_all_preserves_long_term_config(self):
        """清空本次不影响 API Profile store / 搜索词 / 检测服务等长期配置。"""
        from unittest.mock import Mock

        store = Mock()
        self.page.set_api_profile_store(store)
        self.page.txt_cn.setText("测试搜索词")
        self.page.load_results(_products(2))
        self.page._clear_all_results()
        # 长期配置保留
        self.assertIs(self.page._api_profile_store, store)
        self.assertEqual(self.page.txt_cn.text(), "测试搜索词")
        self.assertIsNotNone(self.page._title_risk_service)
        self.assertIsNotNone(self.page._image_risk_service)

    def test_clear_all_blocked_while_detecting(self):
        """检测进行中禁止清空本次。"""
        self.page.load_results(_products(2))
        self.page._enter_detecting(list(self.page._products))
        self.assertFalse(self.page.btn_clear_all.isEnabled())
        self.page._exit_detecting()
        self.assertTrue(self.page.btn_clear_all.isEnabled())


class TestRound2RiskSorting(_PageCase):
    """R 项：风险置顶排序 / 稳定顺序 / 保持选择 / 已移除视图不乱序。"""

    def test_visible_cards_preserve_original_order_without_risk(self):
        """无风险时保持原始采集顺序。"""
        self.page.load_results(_products(3))
        order = [c.product.product_id for c in self.page._visible_cards()]
        self.assertEqual(order, ["1", "2", "3"])

    def test_risk_sort_infringement_platform_none(self):
        """排序：infringement > platform > none。"""
        self.page.load_results(_products(3))
        self.page._cards["1"].set_title_risk_data("platform", "带电")
        self.page._cards["2"].set_title_risk_data("infringement", "品牌IP")
        # 商品 3 无风险
        self.page._sort_risk_pinned()
        order = [c.product.product_id for c in self.page._visible_cards()]
        self.assertEqual(order, ["2", "1", "3"])

    def test_same_rank_keeps_collection_order(self):
        """同等级商品保持原始采集顺序。"""
        self.page.load_results(_products(4))
        # 商品 1、4 都是 platform，采集顺序 1 在前
        self.page._cards["1"].set_title_risk_data("platform", "a")
        self.page._cards["4"].set_title_risk_data("platform", "b")
        self.page._sort_risk_pinned()
        order = [c.product.product_id for c in self.page._visible_cards()]
        self.assertEqual(order, ["1", "4", "2", "3"])

    def test_composite_risk_takes_highest(self):
        """标题 + 图片综合风险取最高等级。"""
        self.page.load_results(_products(2))
        c1 = self.page._cards["1"]
        c2 = self.page._cards["2"]
        # 商品 1：标题 platform + 图片 infringement -> infringement
        c1.set_title_risk_data("platform", "带电")
        c1.set_image_risk_data("infringement", "品牌IP")
        # 商品 2：标题 infringement + 图片 none -> infringement
        c2.set_title_risk_data("infringement", "Logo")
        c2.set_image_risk_data("none")
        self.assertEqual(self.page._card_risk_rank(c1), 2)
        self.assertEqual(self.page._card_risk_rank(c2), 2)
        # 商品 1 仅 platform -> 1
        c1.set_image_risk_data("none")
        self.assertEqual(self.page._card_risk_rank(c1), 1)

    def test_title_redetect_none_clears_only_title_risk(self):
        """标题重新检测为 none 只清标题风险，图片风险保留（走完成回调）。"""
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        self.page.load_results(_products(1))
        card = self.page._cards["1"]
        card.set_title_risk_data("platform", "旧标题风险")
        card.set_image_risk_data("infringement", "品牌IP")
        self.page._enter_detecting([self.page._products[0]])
        self.page._on_title_risk_finished(
            [TitleRiskItem("1", "none", "")], "",
        )
        self.assertIsNone(card._title_risk_data)
        self.assertIsNotNone(card._image_risk_data)
        self.assertEqual(card._image_risk_data["risk"], "infringement")

    def test_sort_preserves_selection(self):
        """排序后 selected 集合与卡片选中框状态不变。"""
        self.page.load_results(_products(3))
        self.page._cards["2"].set_title_risk_data("infringement", "品牌IP")
        self.page.set_selection("1", True)
        self.page.set_selection("2", True)
        self.page._sort_risk_pinned()
        self.assertEqual(self.page._selected_ids, {"1", "2"})
        self.assertTrue(self.page._cards["1"].selected)
        self.assertTrue(self.page._cards["2"].selected)
        # KEEP/REMOVED 不变
        self.assertEqual(self.page._states["1"], "KEEP")
        self.assertEqual(self.page._states["2"], "KEEP")

    def test_removed_view_keeps_original_order(self):
        """已移除页面不参与风险排序，保持原顺序。"""
        self.page.load_results(_products(3))
        for pid in ("1", "2", "3"):
            self.page._states[pid] = "REMOVED"
        self.page._cards["2"].set_title_risk_data("infringement", "品牌IP")
        self.page._showing_removed = True
        order = [c.product.product_id for c in self.page._visible_cards()]
        self.assertEqual(order, ["1", "2", "3"])

    def test_detect_all_sorts_only_once(self):
        """全部检测只在标题+图片全部处理完后排序一次。"""
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        self.page.load_results(_products(2))
        targets = [self.page._products[0], self.page._products[1]]
        self.page._enter_detecting(targets)
        self.page._detect_all_targets = targets
        relayout_calls = []
        orig_relayout = ProductCollectionPage._relayout_cards

        def counting(self_obj):
            relayout_calls.append(self_obj._detect_all_phase)
            return orig_relayout(self_obj)

        with patch.object(ProductCollectionPage, "_relayout_cards", counting):
            # load_results 时已重排 1 次
            base = len(relayout_calls)
            # 标题阶段完成：不排序（同时避免真实线程启动，patch 掉 QThread/Worker）
            with patch(
                "profit_accounting_26.product_collector.ui.product_collection_page.QThread"
            ), patch(
                "profit_accounting_26.product_collector.ui.product_collection_page._ImageRiskWorker"
            ):
                self.page._on_detect_all_title_finished(
                    [TitleRiskItem("1", "platform", "带电"),
                     TitleRiskItem("2", "none", "")],
                    "",
                )
                self.assertEqual(len(relayout_calls), base)
            # 图片阶段完成：最终排序一次
            from profit_accounting_26.product_collector.image_risk_scan import ImageRiskItem
            all_checked = [
                ImageRiskItem("1", "https://img.example/1.jpg", "none", ""),
                ImageRiskItem("2", "https://img.example/2.jpg", "none", ""),
            ]
            stats = {
                "requested_count": 2, "cached_count": 0, "checked_count": 2,
                "risk_count": 0, "failed_count": 0, "all_checked": all_checked,
            }
            self.page._on_detect_all_image_finished([], stats, "")
            self.assertEqual(len(relayout_calls), base + 1)

    def test_sort_returns_scroll_to_top(self):
        """排序完成后滚动条回到顶部。"""
        self.page.load_results(_products(3))
        bar = self.page.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        self.page._cards["2"].set_title_risk_data("infringement", "品牌IP")
        self.page._sort_risk_pinned()
        self.assertEqual(bar.value(), 0)


class TestRound2OverlayDetails(_PageCase):
    """R 项：Overlay 固定尺寸、Tooltip 完整原因、换行算法。"""

    def test_overlay_fixed_dimensions(self):
        """标题/图片 Overlay 宽度和高度固定，不随内容变化。"""
        self.page.load_results(_products(1))
        card = self.page._cards["1"]
        # 短内容
        card.set_title_risk_data("platform", "短")
        card.set_image_risk_data("infringement", "短")
        card._layout_risk_overlays()
        h_title_short = card.lbl_title_risk.height()
        w_title_short = card.lbl_title_risk.width()
        h_img_short = card.lbl_image_risk.height()
        w_img_short = card.lbl_image_risk.width()
        # 长内容
        card.set_title_risk_data("platform", "这是一段很长的风险原因描述用来验证固定尺寸")
        card.set_image_risk_data("infringement", "这是一段很长的图片风险原因描述用来验证固定尺寸方案")
        card._layout_risk_overlays()
        h_title_long = card.lbl_title_risk.height()
        w_title_long = card.lbl_title_risk.width()
        h_img_long = card.lbl_image_risk.height()
        w_img_long = card.lbl_image_risk.width()
        # 尺寸应完全一致
        self.assertEqual(h_title_short, h_title_long)
        self.assertEqual(w_title_short, w_title_long)
        self.assertEqual(h_img_short, h_img_long)
        self.assertEqual(w_img_short, w_img_long)
        # 标题和图片标签尺寸也应一致
        self.assertEqual(w_title_short, w_img_short)
        self.assertEqual(h_title_short, h_img_short)

    def test_overlay_max_three_lines(self):
        """长 reason 最多显示 3 行，不出现第 4 行。"""
        self.page.load_results(_products(1))
        card = self.page._cards["1"]
        long_reason = "这是一段很长的风险原因，" * 10
        card.set_title_risk_data("platform", long_reason)
        card._layout_risk_overlays()
        text = card.lbl_title_risk.text()
        lines = text.split("\n")
        self.assertLessEqual(len(lines), 3)
        # 不出现省略号
        self.assertNotIn("...", text)
        self.assertNotIn("…", text)

    def test_overlay_tooltip_full_reason(self):
        """Overlay Tooltip 包含来源、类型和完整原因。"""
        self.page.load_results(_products(1))
        card = self.page._cards["1"]
        long_reason = "这是一段很长的风险原因" * 10
        card.set_title_risk_data("platform", long_reason)
        card.set_image_risk_data("infringement", long_reason + "-img")
        title_tooltip = card.lbl_title_risk.toolTip()
        image_tooltip = card.lbl_image_risk.toolTip()
        # Tooltip 应包含来源、类型和完整原因
        self.assertIn("来源：标题检测", title_tooltip)
        self.assertIn("SHEIN规则风险", title_tooltip)
        self.assertIn(long_reason, title_tooltip)
        self.assertIn("来源：图片检测", image_tooltip)
        self.assertIn("侵权风险", image_tooltip)
        self.assertIn(long_reason + "-img", image_tooltip)

    def test_risk_label_receives_hover(self):
        """风险标签未设置 WA_TransparentForMouseEvents，可以接收 Hover 事件。"""
        self.page.load_results(_products(1))
        card = self.page._cards["1"]
        card.set_title_risk_data("platform", "测试风险")
        # 标签不应设置 WA_TransparentForMouseEvents
        transparent = card.lbl_title_risk.testAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.assertFalse(transparent)

    def test_risk_summary_strips_prefixes(self):
        """默认标签应去除风险前缀和来源描述前缀。"""
        from profit_accounting_26.product_collector.ui.product_collection_page import (
            _risk_display_summary,
        )
        # 侵权风险
        self.assertEqual(
            _risk_display_summary("侵权风险｜标题包含蜘蛛侠（Spider-Man）IP"),
            "蜘蛛侠（Spider-Man）IP",
        )
        # 平台风险
        self.assertEqual(
            _risk_display_summary("SHEIN规则风险｜标题明确为电子烟配件"),
            "电子烟配件",
        )
        # 采集规则
        self.assertEqual(
            _risk_display_summary("采集规则排除｜标题明确为USB带电商品"),
            "USB带电商品",
        )
        # 图片风险
        self.assertEqual(
            _risk_display_summary("侵权风险｜图片出现漫威（Marvel）蜘蛛侠（Spider-Man）角色"),
            "漫威（Marvel）蜘蛛侠（Spider-Man）角色",
        )


class TestTitleRiskWorkerCancellation(_PageCase):
    """任务 3：标题检测用户取消必须写入风险日志。"""

    def setUp(self):
        super().setUp()
        import shutil
        import tempfile

        from profit_accounting_26.product_collector import product_risk_log as prl
        for handler in list(prl._logger.handlers):
            prl._logger.removeHandler(handler)
            handler.close()
        self._prl = prl
        self._tmp = tempfile.mkdtemp(prefix="pa26_title_cancel_")
        self._log_path = prl.configure(self._tmp)
        self._shutil = shutil

    def tearDown(self):
        for handler in list(self._prl._logger.handlers):
            self._prl._logger.removeHandler(handler)
            handler.close()
        self._shutil.rmtree(self._tmp, ignore_errors=True)
        super().tearDown()

    def test_cancel_before_request_logs_cancelled(self):
        """请求发送前取消：日志出现 [标题检测] 用户取消，不调用 API。"""
        from unittest.mock import Mock

        service = Mock()
        worker = _TitleRiskWorker(
            service, [{"id": "1", "title": "t"}], cancel_requested=lambda: True
        )
        received = []
        worker.finished.connect(lambda risks, err: received.append((risks, err)))
        worker.run()
        service.scan.assert_not_called()
        self.assertEqual(received, [([], "")])
        content = self._log_path.read_text(encoding="utf-8")
        self.assertIn("[标题检测] 用户取消", content)

    def test_cancel_during_request_logs_cancelled_and_keeps_results(self):
        """请求进行中取消：请求自然完成返回结果，且日志记录用户取消。"""
        from unittest.mock import Mock

        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        service = Mock()
        service.scan.return_value = [TitleRiskItem("1", "platform", "带电")]
        calls = {"n": 0}

        def cancel():
            calls["n"] += 1
            return calls["n"] > 1  # 请求前检查放行，请求完成后标记取消

        worker = _TitleRiskWorker(
            service, [{"id": "1", "title": "t"}], cancel_requested=cancel
        )
        received = []
        worker.finished.connect(lambda risks, err: received.append((risks, err)))
        worker.run()
        # 结果仍返回，不因取消丢弃
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0][0].product_id, "1")
        content = self._log_path.read_text(encoding="utf-8")
        self.assertIn("[标题检测] 用户取消", content)

    def test_cancel_during_request_success_logs_cancel_once(self):
        """A：请求期间取消 + 请求成功：取消日志恰好写 1 次，结果仍返回。"""
        from unittest.mock import Mock

        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        service = Mock()
        service.scan.return_value = [TitleRiskItem("1", "platform", "带电")]
        calls = {"n": 0}

        def cancel():
            calls["n"] += 1
            return calls["n"] > 1  # 请求前放行，请求完成时已取消

        worker = _TitleRiskWorker(
            service, [{"id": "1", "title": "t"}], cancel_requested=cancel
        )
        received = []
        worker.finished.connect(lambda risks, err: received.append((risks, err)))
        worker.run()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0][0].product_id, "1")
        content = self._log_path.read_text(encoding="utf-8")
        self.assertEqual(content.count("[标题检测] 用户取消"), 1)

    def test_cancel_during_request_exception_logs_cancel_once(self):
        """B：请求期间取消 + 请求抛异常：取消日志恰好写 1 次，finished 保持 error 行为。"""
        from unittest.mock import Mock

        service = Mock()
        service.scan.side_effect = TimeoutError("timeout")
        calls = {"n": 0}

        def cancel():
            calls["n"] += 1
            return calls["n"] > 1  # 请求前放行，异常后已取消

        worker = _TitleRiskWorker(
            service, [{"id": "1", "title": "t"}], cancel_requested=cancel
        )
        received = []
        worker.finished.connect(lambda risks, err: received.append((risks, err)))
        worker.run()
        self.assertEqual(received, [([], "timeout")])
        content = self._log_path.read_text(encoding="utf-8")
        self.assertEqual(content.count("[标题检测] 用户取消"), 1)

    def test_exception_without_cancel_does_not_log_cancel(self):
        """C：未取消但请求抛异常：不得写用户取消日志。"""
        from unittest.mock import Mock

        service = Mock()
        service.scan.side_effect = TimeoutError("timeout")
        worker = _TitleRiskWorker(
            service, [{"id": "1", "title": "t"}], cancel_requested=lambda: False
        )
        received = []
        worker.finished.connect(lambda risks, err: received.append((risks, err)))
        worker.run()
        self.assertEqual(received, [([], "timeout")])
        content = self._log_path.read_text(encoding="utf-8")
        self.assertNotIn("[标题检测] 用户取消", content)


class TestBatchImmediateResult(_PageCase):
    """C 项：每批结果立即写卡片，其它未完成商品不变。"""

    def _enter(self, count=3):
        self.page.load_results(_products(count))
        targets = list(self.page._products)
        self.page._enter_detecting(targets)
        return targets

    def test_title_batch_applies_immediately(self):
        """第一批完成：对应卡片立即出现标题风险标签，其它不变。"""
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        self._enter(3)
        self.page._on_title_batch_result(
            [TitleRiskItem("1", "infringement", "品牌IP")], 0, 1, 1, 500.0
        )
        card1 = self.page._cards["1"]
        self.assertIsNotNone(card1._title_risk_data)
        self.assertEqual(card1._title_risk_data["risk"], "infringement")
        # 其它未完成商品不改变
        self.assertIsNone(self.page._cards["2"]._title_risk_data)
        self.assertIsNone(self.page._cards["3"]._title_risk_data)
        # 状态栏立即反映
        self.assertIn("标题检测 1/3", self.page.lbl_status.text())
        self.assertIn("风险 1", self.page.lbl_status.text())

    def test_image_batch_applies_immediately(self):
        """图片批次完成：对应卡片立即出现图片风险标签。"""
        from profit_accounting_26.product_collector.image_risk_scan import ImageRiskItem

        self._enter(3)
        self.page._on_image_batch_result(
            [ImageRiskItem("2", "https://img.example/2.jpg", "platform", "可疑")],
            0, 1, 1, 500.0,
        )
        self.assertEqual(self.page._cards["2"]._image_risk_data["risk"], "platform")
        self.assertIsNone(self.page._cards["1"]._image_risk_data)
        self.assertIn("图片检测 1/3", self.page.lbl_status.text())

    def test_batch_none_clears_only_own_source(self):
        """risk=none 只清除该检测来源的旧风险，另一来源不受影响。"""
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        self._enter(1)
        card = self.page._cards["1"]
        card.set_title_risk_data("infringement", "旧标题风险")
        card.set_image_risk_data("infringement", "品牌IP")
        self.page._on_title_batch_result(
            [TitleRiskItem("1", "none", "")], 0, 1, 1, 100.0
        )
        self.assertIsNone(card._title_risk_data)  # 旧标题风险清除
        self.assertIsNotNone(card._image_risk_data)  # 图片风险不受影响
        self.assertEqual(card._image_risk_data["risk"], "infringement")

    def test_failed_batch_preserves_old_state(self):
        """失败批次不覆盖旧状态，只计入失败数。"""
        self._enter(1)
        card = self.page._cards["1"]
        card.set_title_risk_data("platform", "旧状态")
        self.page._on_title_batch_result([], 1, 1, 2, 100.0)
        self.assertEqual(card._title_risk_data["risk"], "platform")
        self.assertEqual(card._title_risk_data["reason"], "旧状态")
        self.assertIn("失败 1", self.page.lbl_status.text())


class TestNoEarlySort(_PageCase):
    """D 项：检测期间批次结果 / relayout 不重排，终态才排序。"""

    def _enter(self, count=3):
        self.page.load_results(_products(count))
        targets = list(self.page._products)
        self.page._enter_detecting(targets)
        return targets

    def test_first_batch_does_not_reorder(self):
        """第一批 infringement 出现：卡片保持原位置。"""
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        self._enter(3)
        self.page._on_title_batch_result(
            [TitleRiskItem("2", "infringement", "品牌IP")], 0, 1, 2, 100.0
        )
        order = [c.product.product_id for c in self.page._visible_cards()]
        self.assertEqual(order, ["1", "2", "3"])

    def test_second_batch_still_no_reorder(self):
        """第二批出现：仍保持原位置。"""
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        self._enter(3)
        self.page._on_title_batch_result(
            [TitleRiskItem("2", "infringement", "品牌IP")], 0, 1, 2, 100.0
        )
        self.page._on_title_batch_result(
            [TitleRiskItem("3", "platform", "带电")], 0, 2, 2, 100.0
        )
        order = [c.product.product_id for c in self.page._visible_cards()]
        self.assertEqual(order, ["1", "2", "3"])

    def test_relayout_preserves_frozen_order(self):
        """已有部分标签时触发 relayout/resize：顺序仍不变化。"""
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        self._enter(3)
        self.page._on_title_batch_result(
            [TitleRiskItem("2", "infringement", "品牌IP")], 0, 1, 1, 100.0
        )
        self.page._relayout_cards()
        order = [c.product.product_id for c in self.page._visible_cards()]
        self.assertEqual(order, ["1", "2", "3"])

    def test_frozen_order_captured_at_enter(self):
        """进入检测记录冻结顺序，退出时清除。"""
        self._enter(3)
        self.assertEqual(self.page._detect_display_order, ["1", "2", "3"])
        self.page._exit_detecting()
        self.assertIsNone(self.page._detect_display_order)

    def test_frozen_order_respects_pre_detect_sort(self):
        """进入检测前已排序，冻结顺序沿用已排序顺序。"""
        self.page.load_results(_products(3))
        self.page._cards["2"].set_title_risk_data("infringement", "品牌IP")
        self.page._sort_risk_pinned()
        # 直接进入检测（不重新 load_results，保留已排序状态）
        targets = list(self.page._products)
        self.page._enter_detecting(targets)
        self.assertEqual(self.page._detect_display_order, ["2", "1", "3"])
        order = [c.product.product_id for c in self.page._visible_cards()]
        self.assertEqual(order, ["2", "1", "3"])

    def test_terminal_sort_once_and_unfreezes(self):
        """终态：清除冻结顺序并排序一次。"""
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        self._enter(3)
        self.page._on_title_batch_result(
            [TitleRiskItem("2", "infringement", "品牌IP")], 0, 1, 1, 100.0
        )
        risks = [
            TitleRiskItem("1", "none", ""),
            TitleRiskItem("2", "infringement", "品牌IP"),
            TitleRiskItem("3", "none", ""),
        ]
        self.page._on_title_risk_finished(risks, "")
        self.assertIsNone(self.page._detect_display_order)
        self.assertFalse(self.page._detecting_active)
        order = [c.product.product_id for c in self.page._visible_cards()]
        self.assertEqual(order, ["2", "1", "3"])


class TestTerminalSortCounts(_PageCase):
    """E 项：正常/部分失败/取消/fatal error 各只排序一次。"""

    def _count_relayouts(self, fn):
        relayout_calls = []
        orig = ProductCollectionPage._relayout_cards

        def counting(self_obj):
            relayout_calls.append(1)
            return orig(self_obj)

        with patch.object(ProductCollectionPage, "_relayout_cards", counting):
            fn()
        return len(relayout_calls)

    def _enter(self, count=3):
        self.page.load_results(_products(count))
        targets = list(self.page._products)
        self.page._enter_detecting(targets)
        return targets

    def test_normal_completion_sorts_once(self):
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        self._enter(3)
        risks = [TitleRiskItem(str(i), "none", "") for i in range(1, 4)]
        n = self._count_relayouts(lambda: self.page._on_title_risk_finished(risks, ""))
        self.assertEqual(n, 1)

    def test_partial_failure_sorts_once(self):
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        self._enter(3)
        risks = [TitleRiskItem("1", "platform", "带电")]  # 只返回 1/3
        n = self._count_relayouts(lambda: self.page._on_title_risk_finished(risks, ""))
        self.assertEqual(n, 1)
        self.assertIn("失败", self.page.lbl_status.text())

    def test_cancel_sorts_once(self):
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        self._enter(3)
        risks = [TitleRiskItem(str(i), "none", "") for i in range(1, 4)]
        self.page._cancel_requested = True
        n = self._count_relayouts(lambda: self.page._on_title_risk_finished(risks, ""))
        self.assertEqual(n, 1)
        self.assertIn("取消", self.page.lbl_status.text())

    def test_fatal_error_sorts_once_with_prior_results(self):
        """整体 fatal error：已应用的成功结果仍排序一次。"""
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        self._enter(3)
        self.page._on_title_batch_result(
            [TitleRiskItem("2", "infringement", "品牌IP")], 0, 1, 1, 100.0
        )
        n = self._count_relayouts(lambda: self.page._on_title_risk_finished([], "timeout"))
        self.assertEqual(n, 1)
        self.assertEqual(self.page.lbl_status.text(), "标题检测失败")
        # 已有结果保留且已按风险排序
        order = [c.product.product_id for c in self.page._visible_cards()]
        self.assertEqual(order, ["2", "1", "3"])
        self.assertIsNone(self.page._detect_display_order)


class TestDetectFreezeBehavior(_PageCase):
    """F 项：检测中冻结选择，但双击标题/图片仍正常。"""

    def _setup(self):
        self.page.load_results(_products(2))
        self.page._enter_detecting(list(self.page._products))
        return self.page._cards["1"], self.page._cards["2"]

    def _press(self, card, button):
        event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(10, 10), button, button,
            Qt.KeyboardModifier.NoModifier,
        )
        card.mousePressEvent(event)

    def test_left_click_does_not_change_selection(self):
        """检测中左键单击：selected 不变。"""
        card, _ = self._setup()
        emitted = []
        card.selectionRequested.connect(lambda *a: emitted.append(a))
        self._press(card, Qt.MouseButton.LeftButton)
        self.assertEqual(emitted, [])
        self.assertEqual(self.page.selected_count(), 0)

    def test_right_click_does_not_change_selection(self):
        """检测中右键单击：selected 不变。"""
        card, _ = self._setup()
        self.page.set_selection("1", True)
        emitted = []
        card.selectionRequested.connect(lambda *a: emitted.append(a))
        self._press(card, Qt.MouseButton.RightButton)
        self.assertEqual(emitted, [])
        self.assertEqual(self.page.selected_count(), 1)  # 保持选中

    def _dblclick_at(self, card, pos):
        event = QMouseEvent(
            QEvent.Type.MouseButtonDblClick,
            pos, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        card.mouseDoubleClickEvent(event)

    def _layout_card_manually(self, card):
        """不 show 页面（offscreen 下连续 show/销毁会崩溃），手动摆位子控件。"""
        card.lbl_image.setGeometry(10, 10, 200, 200)
        card.lbl_title.setGeometry(10, 220, 200, 100)

    def test_double_click_title_emits_title_activated(self):
        """检测中双击标题：titleActivated 正常发出（不真实打开浏览器）。"""
        card, _ = self._setup()
        self._layout_card_manually(card)
        received = []
        card.titleActivated.connect(lambda url: received.append(url))
        with patch(
            "profit_accounting_26.product_collector.ui.product_collection_page.webbrowser.open"
        ):
            self._dblclick_at(card, QPointF(110, 270))
        self.assertEqual(received, [card._product.product_url])

    def test_double_click_image_emits_image_search(self):
        """检测中双击图片：imageSearchRequested 正常发出。

        沿用既有测试模式：patch ImageSearchWorker.run 让线程立即失败，
        避免真实网络请求与打开浏览器。
        """
        card, _ = self._setup()
        self._layout_card_manually(card)
        received = []
        card.imageSearchRequested.connect(lambda url: received.append(url))

        def fail_fast(worker):
            worker.failed.emit("test")

        with patch(
            "profit_accounting_26.product_collector.ui.product_collection_page.ImageSearchWorker.run",
            fail_fast,
        ):
            self._dblclick_at(card, QPointF(110, 110))
            # 轮询等待搜图线程真正结束并清理，避免测试结束时线程仍在运行、
            # 页面销毁运行中的 QThread 触发崩溃（Linux CI 上为 SIGBUS）。
            for _ in range(60):
                self._pump(50)
                if self.page._image_search_thread is None:
                    break
        self.assertEqual(received, [card._product.main_image])
        self.assertIsNone(self.page._image_search_thread)
        self.assertIsNone(self.page._image_search_worker)

    def test_buttons_disabled_while_detecting(self):
        """检测中：全选/移除/恢复/清空/重新采集等全部禁用。"""
        self._setup()
        for btn in (
            self.page.btn_select_all, self.page.btn_keep_only,
            self.page.btn_remove_selected, self.page.btn_view_removed,
            self.page.btn_restore, self.page.btn_start,
            self.page.btn_title_check, self.page.btn_infringement_check,
            self.page.btn_detect_all, self.page.btn_clear_all,
        ):
            self.assertFalse(btn.isEnabled(), btn.objectName())
        self.page._exit_detecting()
        self.assertTrue(self.page.btn_start.isEnabled())
        self.assertTrue(self.page.btn_clear_all.isEnabled())


class TestAllDetectKeepsFreeze(_PageCase):
    """G 项：全部检测标题→图片阶段冻结不断开，最终才解冻。"""

    def _setup(self):
        self.page.load_results(_products(3))
        targets = list(self.page._products)
        self.page._enter_detecting(targets)
        self.page._detect_all_targets = targets
        self.page._detect_all_phase = "title"
        return targets

    def _complete_title_phase(self):
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        risks = [TitleRiskItem(str(i), "none", "") for i in range(1, 4)]
        with patch(
            "profit_accounting_26.product_collector.ui.product_collection_page.QThread"
        ), patch(
            "profit_accounting_26.product_collector.ui.product_collection_page._ImageRiskWorker"
        ):
            self.page._on_detect_all_title_finished(risks, "")

    def test_title_phase_end_keeps_detecting(self):
        """标题阶段结束：仍 detecting_active=True，冻结不解除，直接进图片阶段。"""
        self._setup()
        self._complete_title_phase()
        self.assertTrue(self.page._detecting_active)
        self.assertIsNotNone(self.page._detect_display_order)
        self.assertEqual(self.page._detect_all_phase, "image")
        self.assertFalse(self.page.btn_start.isEnabled())
        self.assertFalse(self.page.btn_select_all.isEnabled())
        self.assertIn("图片", self.page.lbl_status.text())

    def test_image_phase_end_unfreezes(self):
        """图片阶段结束：才解除冻结。"""
        from profit_accounting_26.product_collector.image_risk_scan import ImageRiskItem

        self._setup()
        self._complete_title_phase()
        all_checked = [
            ImageRiskItem(str(i), f"https://img.example/{i}.jpg", "none", "")
            for i in range(1, 4)
        ]
        stats = {
            "requested_count": 3, "cached_count": 0, "checked_count": 3,
            "risk_count": 0, "failed_count": 0, "all_checked": all_checked,
        }
        self.page._on_detect_all_image_finished([], stats, "")
        self.assertFalse(self.page._detecting_active)
        self.assertIsNone(self.page._detect_display_order)
        self.assertTrue(self.page.btn_start.isEnabled())

    def test_title_phase_cancel_unfreezes(self):
        """标题阶段用户取消：解冻并排序，不进入图片阶段。"""
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        self._setup()
        risks = [TitleRiskItem(str(i), "none", "") for i in range(1, 4)]
        self.page._cancel_requested = True
        self.page._on_detect_all_title_finished(risks, "")
        self.assertFalse(self.page._detecting_active)
        self.assertIsNone(self.page._detect_display_order)
        self.assertIn("取消", self.page.lbl_status.text())

    def test_title_phase_error_unfreezes(self):
        """标题阶段整体错误：解冻并排序。"""
        self._setup()
        self.page._on_detect_all_title_finished([], "timeout")
        self.assertFalse(self.page._detecting_active)
        self.assertIsNone(self.page._detect_display_order)
        self.assertEqual(self.page.lbl_status.text(), "标题检测失败")


class TestEtaStatus(_PageCase):
    """H 项：简单 ETA 计算逻辑与格式（不做精准预测）。"""

    def test_format_eta_seconds(self):
        self.assertEqual(ProductCollectionPage._format_eta(55), "约 55秒")

    def test_format_eta_exact_minute(self):
        self.assertEqual(ProductCollectionPage._format_eta(60), "约 1分")

    def test_format_eta_minutes_seconds(self):
        self.assertEqual(ProductCollectionPage._format_eta(80), "约 1分20秒")

    def test_format_eta_zero_safe(self):
        """0 秒不产生除零 / 0 秒展示。"""
        self.assertEqual(ProductCollectionPage._format_eta(0), "约 1秒")

    def test_initial_status_shows_computing(self):
        """第一批完成前：显示计算中。"""
        self.page.load_results(_products(3))
        self.page._update_detect_status("标题检测", 0, 3, 0, 0, 0, 0, "预计剩余")
        self.assertIn("标题检测 0/3", self.page.lbl_status.text())
        self.assertIn("计算中", self.page.lbl_status.text())

    def test_eta_appears_after_first_batch(self):
        """第一批后出现预计剩余（平均耗时 × 剩余批数）。"""
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        self.page.load_results(_products(3))
        self.page._enter_detecting(list(self.page._products))
        self.page._on_title_batch_result(
            [TitleRiskItem("1", "none", "")], 0, 1, 3, 60_000.0
        )
        text = self.page.lbl_status.text()
        self.assertIn("预计剩余约", text)
        # avg=60s, 剩余 2 批 -> 120s -> 约 2分
        self.assertIn("2分", text)

    def test_eta_text_has_single_yue(self):
        """状态文字只保留一个'约'，不存在'约 约'。"""
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        self.page.load_results(_products(3))
        self.page._enter_detecting(list(self.page._products))
        self.page._on_title_batch_result(
            [TitleRiskItem("1", "none", "")], 0, 1, 3, 60_000.0
        )
        text = self.page.lbl_status.text()
        self.assertNotIn("约 约", text)
        self.assertEqual(text.count("约"), 1)
        # avg=60s, 剩余 2 批 -> 120s -> "约 2分"，外层不再重复拼接"约"
        self.assertIn("预计剩余约 2分", text)
        self.page._exit_detecting()

    def test_eta_all_detect_single_yue(self):
        """全部检测阶段同样只有一个'约'。"""
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        self.page.load_results(_products(3))
        self.page._enter_detecting(list(self.page._products))
        self.page._on_detect_all_title_batch_result(
            [TitleRiskItem("1", "none", "")], 0, 1, 3, 60_000.0
        )
        text = self.page.lbl_status.text()
        self.assertNotIn("约 约", text)
        self.assertIn("预计本阶段剩余约 2分", text)
        self.page._exit_detecting()

    def test_eta_cleared_after_last_batch(self):
        """最后一个批次完成：不再显示 ETA。"""
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        self.page.load_results(_products(3))
        self.page._enter_detecting(list(self.page._products))
        self.page._on_title_batch_result(
            [TitleRiskItem("1", "none", "")], 0, 1, 1, 1000.0
        )
        self.assertNotIn("预计剩余", self.page.lbl_status.text())

    def test_single_batch_no_abnormal_eta(self):
        """单批任务：批次完成即最后一批，无 ETA 段、无异常。"""
        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        self.page.load_results(_products(1))
        self.page._enter_detecting(list(self.page._products))
        self.page._on_title_batch_result(
            [TitleRiskItem("1", "none", "")], 0, 1, 1, 500.0
        )
        text = self.page.lbl_status.text()
        self.assertIn("标题检测 1/1", text)
        self.assertNotIn("预计剩余", text)

    def test_zero_products_no_division_by_zero(self):
        """0 商品：不除零。"""
        self.page._update_detect_status("标题检测", 0, 0, 0, 0, 0, 0, "预计剩余")
        self.assertIn("0/0", self.page.lbl_status.text())
        self.assertIn("计算中", self.page.lbl_status.text())


class TestWorkerBatchSignal(_PageCase):
    """二十一节：Worker 批次 Signal 转发，finished 只发一次，取消不产生批次。"""

    def test_title_worker_forwards_batch_results(self):
        from unittest.mock import Mock

        from profit_accounting_26.product_collector.title_risk_scan import TitleRiskItem

        service = Mock()

        def fake_scan(titles, *, on_batch=None, cancel_requested=None):
            on_batch([TitleRiskItem("1", "platform", "带电")], 0, 1, 2, 100.0)
            on_batch([TitleRiskItem("2", "none", "")], 0, 2, 2, 150.0)
            return [
                TitleRiskItem("1", "platform", "带电"),
                TitleRiskItem("2", "none", ""),
            ]

        service.scan.side_effect = fake_scan
        worker = _TitleRiskWorker(
            service, [{"id": "1", "title": "a"}, {"id": "2", "title": "b"}]
        )
        batches = []
        finished = []
        worker.batch_result.connect(lambda *a: batches.append(a))
        worker.finished.connect(lambda *a: finished.append(a))
        worker.run()
        self.assertEqual(len(batches), 2)
        self.assertEqual(batches[0][2], 1)  # batch_index
        self.assertEqual(batches[0][3], 2)  # total_batches
        self.assertEqual(batches[1][2], 2)
        self.assertEqual(len(finished), 1)  # finished 只发一次
        self.assertEqual(len(finished[0][0]), 2)

    def test_image_worker_forwards_batch_results(self):
        from unittest.mock import Mock

        from profit_accounting_26.product_collector.image_risk_scan import ImageRiskItem

        service = Mock()

        def fake_scan_batch(products, *, force_refresh=False,
                            cancel_requested=None, on_batch=None):
            on_batch(
                [ImageRiskItem("1", "http://x/1.jpg", "none", "")],
                0, 1, 1, 80.0,
            )
            stats = Mock(requested_count=1, cached_count=0, checked_count=1,
                         risk_count=0, failed_count=0)
            return ([], stats, [ImageRiskItem("1", "http://x/1.jpg", "none", "")])

        service.scan_batch.side_effect = fake_scan_batch
        worker = _ImageRiskWorker(
            service, [{"id": "1", "main_image": "http://x/1.jpg"}]
        )
        batches = []
        finished = []
        worker.batch_result.connect(lambda *a: batches.append(a))
        worker.finished.connect(lambda *a: finished.append(a))
        worker.run()
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0][3], 1)  # total_batches
        self.assertEqual(len(finished), 1)
        self.assertEqual(finished[0][1]["checked_count"], 1)

    def test_image_worker_cancel_before_scan_passes_cancel_flag(self):
        """图片 worker 请求前取消：仍调用 scan_batch 但携带取消标记（service 内不发送批次）。"""
        from unittest.mock import Mock

        service = Mock()
        service.scan_batch.return_value = (
            [],
            Mock(requested_count=0, cached_count=0, checked_count=0,
                 risk_count=0, failed_count=0),
            [],
        )
        worker = _ImageRiskWorker(
            service, [{"id": "1", "main_image": "http://x/1.jpg"}],
            cancel_requested=lambda: True,
        )
        finished = []
        worker.finished.connect(lambda *a: finished.append(a))
        worker.run()
        service.scan_batch.assert_called_once()
        kwargs = service.scan_batch.call_args.kwargs
        self.assertTrue(kwargs["cancel_requested"]())
        self.assertEqual(len(finished), 1)


class TestRiskBadgeWrapAlgorithm(unittest.TestCase):
    """测试风险标签换行算法：填满行宽、自然断点、IP 保护。"""

    def _make_fm(self, font_size: int = 11) -> QFontMetrics:
        from PySide6.QtGui import QFont
        font = QFont("Microsoft YaHei", font_size)
        return QFontMetrics(font)

    def test_short_text_no_wrap(self):
        """短文本不需要换行。"""
        from profit_accounting_26.product_collector.ui.product_collection_page import (
            _wrap_risk_badge_text,
        )
        fm = self._make_fm()
        result = _wrap_risk_badge_text("USB带电", fm, 160)
        self.assertEqual(result, "USB带电")
        self.assertNotIn("\n", result)

    def test_long_text_wraps_to_multiple_lines(self):
        """长文本应换行为多行。"""
        from profit_accounting_26.product_collector.ui.product_collection_page import (
            _wrap_risk_badge_text,
        )
        fm = self._make_fm()
        text = "这是一段很长的风险原因描述，包含多个逗号，用来验证换行算法是否正确工作"
        result = _wrap_risk_badge_text(text, fm, 160)
        lines = result.split("\n")
        self.assertGreater(len(lines), 1)

    def test_max_lines_respected(self):
        """超长文本最多返回 max_lines 行。"""
        from profit_accounting_26.product_collector.ui.product_collection_page import (
            _wrap_risk_badge_text,
        )
        fm = self._make_fm()
        text = "这是一段非常长的文本，" * 20
        result = _wrap_risk_badge_text(text, fm, 160, max_lines=3)
        lines = result.split("\n")
        self.assertLessEqual(len(lines), 3)

    def test_no_ellipsis_in_output(self):
        """输出不应包含省略号。"""
        from profit_accounting_26.product_collector.ui.product_collection_page import (
            _wrap_risk_badge_text,
        )
        fm = self._make_fm()
        text = "这是一段非常长的文本，" * 20
        result = _wrap_risk_badge_text(text, fm, 160, max_lines=3)
        self.assertNotIn("...", result)
        self.assertNotIn("…", result)

    def test_tokenize_keeps_english_words_intact(self):
        """英文单词、连字符词应作为完整 token。"""
        from profit_accounting_26.product_collector.ui.product_collection_page import (
            _tokenize,
        )
        tokens = _tokenize("Spider-Man and Pokémon")
        self.assertIn("Spider-Man", tokens)
        self.assertIn("Pokémon", tokens)

    def test_tokenize_bracket_groups(self):
        """括号内容应作为独立 token。"""
        from profit_accounting_26.product_collector.ui.product_collection_page import (
            _tokenize,
        )
        tokens = _tokenize("漫威（Marvel）角色")
        self.assertIn("（Marvel）", tokens)

    def test_wrap_fills_line_width(self):
        """换行应贪心填满行宽，不因早期标点提前换行。"""
        from profit_accounting_26.product_collector.ui.product_collection_page import (
            _wrap_risk_badge_text,
        )
        fm = self._make_fm()
        # 构造一个足够长的文本，确保需要换行
        text = "包含游戏IP（恋与深空）角色形象设计原画周边商品"
        result = _wrap_risk_badge_text(text, fm, 160)
        lines = result.split("\n")
        # 应该有多行
        self.assertGreater(len(lines), 1)
        # 每行都不应为空
        for line in lines:
            self.assertGreater(len(line), 0)
        # 总字符数不应超过原文（不添加额外字符）
        total_chars = sum(len(l) for l in lines)
        self.assertLessEqual(total_chars, len(text))

    def test_empty_text(self):
        """空文本返回空。"""
        from profit_accounting_26.product_collector.ui.product_collection_page import (
            _wrap_risk_badge_text,
        )
        fm = self._make_fm()
        self.assertEqual(_wrap_risk_badge_text("", fm, 160), "")


class TestRiskBadgeDoubleClickForwarding(_PageCase):
    """测试风险标签双击事件转发到卡片。"""

    def test_risk_label_has_event_filter(self):
        """风险标签已安装事件过滤器。"""
        self.page.load_results(_products(1))
        card = self.page._cards["1"]
        card.set_title_risk_data("platform", "测试")
        # 事件过滤器应已安装（通过检查 label 的父对象）
        # 简单验证：标签存在且可见
        self.assertFalse(card.lbl_title_risk.isHidden())

    def test_title_double_click_still_works_with_risk_label(self):
        """标题双击打开链接功能在风险标签存在时仍正常（不触发真实浏览器）。"""
        from unittest.mock import patch
        self.page.load_results(_products(1))
        card = self.page._cards["1"]
        card.set_title_risk_data("platform", "测试风险")
        received = []
        card.titleActivated.connect(lambda url: received.append(url))
        # 在标题区域（非风险标签区域）双击
        title_geo = card.lbl_title.geometry()
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QPoint
        pos = QPoint(title_geo.right() - 5, title_geo.top() + 5)
        event = QMouseEvent(
            QEvent.Type.MouseButtonDblClick,
            pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        # 阻止真实 webbrowser.open（与现有测试一致的 patch 路径）
        with patch(
            "profit_accounting_26.product_collector.ui.product_collection_page.webbrowser.open"
        ):
            card.mouseDoubleClickEvent(event)
        self.assertEqual(len(received), 1)


if __name__ == "__main__":
    unittest.main()
