"""商品采集页最小测试。

只覆盖本轮要求的最小点：
1. ProductCollectionPage 可以创建
2. 新导航页存在（NAV_ITEMS + main_window.ui 占位）
3. KEEP / REMOVED 基本状态正确
4. 复制链接只包含 KEEP 商品
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QPushButton, QWidget

from profit_accounting_26.product_collection.models import CandidateProduct
from profit_accounting_26.ui.main_window import NAV_ITEMS
from profit_accounting_26.ui.pages.product_collection_page import ProductCollectionPage
from profit_accounting_26.ui.ui_loader import load_main_window


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


def test_page_can_be_created(qapp):
    page = ProductCollectionPage()
    assert page is not None
    assert page.lbl_status.text() == "状态：待采集"
    page.deleteLater()
    qapp.processEvents()


def test_new_navigation_page_exists(qapp):
    assert NAV_ITEMS == ["新商品测算", "商品采集", "历史记录管理", "设置"]
    ui = load_main_window()
    try:
        assert ui.findChild(QPushButton, "btnNavProductCollection") is not None
        assert ui.findChild(QWidget, "pageProductCollection") is not None
    finally:
        ui.deleteLater()
        qapp.processEvents()


def test_keep_removed_states(qapp):
    page = ProductCollectionPage()
    page._fetch_images = False
    page.load_results(_products(3))
    try:
        assert page.keep_count() == 3
        assert page.removed_count() == 0

        page.remove_product("1")
        assert page.keep_count() == 2
        assert page.removed_count() == 1
        assert page._states["1"] == "REMOVED"

        page.restore_product("1")
        assert page.keep_count() == 3
        assert page.removed_count() == 0
        assert page._states["1"] == "KEEP"
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_copy_links_only_keep(qapp):
    page = ProductCollectionPage()
    page._fetch_images = False
    page.load_results(_products(3))
    try:
        page.remove_product("1")
        text = page.kept_links()
        assert text == "\n".join(
            [f"https://www.aliexpress.com/item/{i}.html" for i in (2, 3)]
        )
        written = []
        page._write_clipboard = lambda t: written.append(t)
        page._notice = lambda *args, **kwargs: None
        copied = page.copy_kept_links()
        assert copied == text
        assert written == [text]
    finally:
        page.deleteLater()
        qapp.processEvents()
