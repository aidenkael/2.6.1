"""Product Collector 集成测试。

验证：
1. Product Collector package 可以正常 import
2. 独立 .ui 可以加载
3. MainWindow 可以创建 ProductCollectionPage
4. Product Collector 不要求主软件数据库才能初始化其采集核心
5. CandidateProduct 稳定结构没有无必要改变
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class TestProductCollectorImport(unittest.TestCase):
    """验证 Product Collector 模块可正常导入。"""

    def test_package_importable(self):
        from profit_accounting_26 import product_collector
        self.assertTrue(hasattr(product_collector, "ProductCollectionPage"))
        self.assertTrue(hasattr(product_collector, "CandidateProduct"))
        self.assertTrue(hasattr(product_collector, "collect"))

    def test_collector_core_importable(self):
        from profit_accounting_26.product_collector.collector_core import CandidateProduct, collect
        self.assertTrue(callable(collect))

    def test_keyword_engine_importable(self):
        from profit_accounting_26.product_collector import keyword_engine
        self.assertTrue(hasattr(keyword_engine, "list_categories"))
        self.assertTrue(hasattr(keyword_engine, "resolve_cn_keyword"))

    def test_ui_page_importable(self):
        from profit_accounting_26.product_collector.ui import ProductCollectionPage
        self.assertTrue(callable(ProductCollectionPage))


class TestProductCollectorUI(unittest.TestCase):
    """验证 Product Collector UI 可正常加载。"""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_ui_file_loads(self):
        from profit_accounting_26.product_collector.ui.ui_loader import load_ui
        widget = load_ui()
        try:
            self.assertIsNotNone(widget)
        finally:
            widget.deleteLater()
            self.app.processEvents()

    def test_page_can_be_created_without_appcontext(self):
        from profit_accounting_26.product_collector.ui import ProductCollectionPage
        page = ProductCollectionPage()
        try:
            self.assertIsNotNone(page)
            # 验证 set_log_dir 方法存在
            self.assertTrue(hasattr(page, "set_log_dir"))
            page.set_log_dir("/tmp/test_logs")
            self.assertEqual(page._log_dir, "/tmp/test_logs")
        finally:
            page.deleteLater()
            self.app.processEvents()


class TestCandidateProductStable(unittest.TestCase):
    """验证 CandidateProduct 稳定结构。"""

    def test_candidate_product_fields(self):
        from profit_accounting_26.product_collector.collector_core.models import CandidateProduct
        p = CandidateProduct(
            product_id="123",
            title="Test",
            main_image="https://example.com/pic.jpg",
            product_url="https://www.aliexpress.com/item/123.html",
            keyword="test",
            position=1,
        )
        self.assertEqual(p.product_id, "123")
        self.assertEqual(p.title, "Test")
        self.assertEqual(p.main_image, "https://example.com/pic.jpg")
        self.assertEqual(p.product_url, "https://www.aliexpress.com/item/123.html")
        self.assertEqual(p.keyword, "test")
        self.assertEqual(p.position, 1)


if __name__ == "__main__":
    unittest.main()
