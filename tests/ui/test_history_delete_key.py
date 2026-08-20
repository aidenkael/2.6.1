"""历史记录 Delete 键 targeted tests（任务书十二节）。

覆盖：
- 历史表格有焦点 + 有选中行 → 按 Delete 直接调用同一个 _delete_selected()，
  确认框文案不变（复用 confirm_action）；
- 确认框确认 → 记录永久删除；确认框取消 → 记录保留；
- 焦点在历史搜索框 → Delete 只删除搜索文字，不删除历史记录；
- 不做 QApplication 全局 Delete 监听（只监听表格范围）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from profit_accounting_26.application import AppContext  # noqa: E402
from profit_accounting_26.ui.pages.history_page import HistoryPage  # noqa: E402


@pytest.fixture()
def context(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


def _create_record(context, product_name: str = "Delete键商品") -> str:
    payload = {
        "product_name": product_name,
        "product_link": f"https://detail.1688.com/offer/{product_name}.html",
        "product_cost_rmb": 10.0,
        "domestic_shipping_rmb": 0.0,
        "layers": {
            "adopted": {
                "selected_packaging": "正常档",
                "normal": {"length_cm": 4, "width_cm": 6, "height_cm": 7, "weight_g": 5},
                "conservative": {"length_cm": 4, "width_cm": 6, "height_cm": 7, "weight_g": 5},
                "bare": {},
            }
        },
    }
    return context.history_record_v2_service.create_record(
        payload, ai_initial=None,
        current_estimate={"length_cm": 4, "width_cm": 6, "height_cm": 7, "weight_g": 5},
    )


def _row_for(page: HistoryPage, record_id: str) -> int:
    for row in range(page.table.rowCount()):
        if page.selected_record_id() is None:
            page.table.selectRow(row)
        item = page.table.item(row, 0)
        if item is not None and item.data(256) == record_id:
            return row
    raise AssertionError(f"记录 {record_id} 不在表格中")


class TestTableDeleteKey:
    def test_delete_key_calls_delete_selected_and_deletes(self, qapp, context, monkeypatch):
        import profit_accounting_26.ui.pages.history_page as history_page_module

        called: list[bool] = []
        original = history_page_module.HistoryPage._delete_selected

        def spy(self):
            called.append(True)
            return original(self)

        monkeypatch.setattr(history_page_module, "confirm_action", lambda *a, **k: True)
        monkeypatch.setattr(history_page_module.HistoryPage, "_delete_selected", spy)
        record_id = _create_record(context)
        page = HistoryPage(context)
        page.table.selectRow(_row_for(page, record_id))
        page.table.setFocus()
        QTest.keyClick(page.table, Qt.Key.Key_Delete)
        assert called, "Delete 键必须调用同一个 _delete_selected()"
        assert page.table.rowCount() == 0
        with pytest.raises(KeyError):
            context.record_service.load(record_id)

    def test_delete_key_cancel_keeps_record(self, qapp, context, monkeypatch):
        import profit_accounting_26.ui.pages.history_page as history_page_module

        monkeypatch.setattr(history_page_module, "confirm_action", lambda *a, **k: False)
        record_id = _create_record(context)
        page = HistoryPage(context)
        page.table.selectRow(_row_for(page, record_id))
        page.table.setFocus()
        QTest.keyClick(page.table, Qt.Key.Key_Delete)
        assert page.table.rowCount() == 1
        assert context.record_service.load(record_id) is not None

    def test_delete_key_without_selection_is_noop(self, qapp, context, monkeypatch):
        import profit_accounting_26.ui.pages.history_page as history_page_module

        monkeypatch.setattr(history_page_module, "confirm_action", lambda *a, **k: True)
        _create_record(context)
        page = HistoryPage(context)
        page.table.setCurrentItem(None)  # 无选中行（currentRow == -1）
        page.table.setFocus()
        QTest.keyClick(page.table, Qt.Key.Key_Delete)
        assert page.table.rowCount() == 1, "无选中行时 Delete 键不得删除任何记录"


class TestSearchBoxDeleteSafe:
    def test_delete_in_search_box_only_edits_text(self, qapp, context, monkeypatch):
        import profit_accounting_26.ui.pages.history_page as history_page_module

        monkeypatch.setattr(history_page_module, "confirm_action", lambda *a, **k: True)
        record_id = _create_record(context)
        page = HistoryPage(context)
        page.show()
        page.search.setFocus()
        page.search.setText("Delete")  # 命中记录名（Delete键商品）
        page.search.setCursorPosition(5)  # Delet|e —— Delete 删除光标右侧字符
        QTest.keyClick(page.search, Qt.Key.Key_Delete)
        assert page.search.text() == "Delet", "搜索框 Delete 应只删除搜索文字"
        assert page.table.rowCount() == 1, "搜索框 Delete 不得删除历史记录"
        assert context.record_service.load(record_id) is not None
        page.close()

    def test_delete_key_scope_is_table_only(self, qapp, context, monkeypatch):
        """过滤器只监听表格范围：焦点在搜索框时 Delete 事件不进表格。"""
        import profit_accounting_26.ui.pages.history_page as history_page_module

        called: list[bool] = []
        original = history_page_module.HistoryPage._delete_selected

        def spy(self):
            called.append(True)
            return original(self)

        monkeypatch.setattr(history_page_module, "confirm_action", lambda *a, **k: True)
        monkeypatch.setattr(history_page_module.HistoryPage, "_delete_selected", spy)
        _create_record(context)
        page = HistoryPage(context)
        page.show()
        page.search.setFocus()
        page.search.setText("Delete")
        page.search.setCursorPosition(5)
        QTest.keyClick(page.search, Qt.Key.Key_Delete)
        assert not called, "搜索框焦点下 Delete 不得触发 _delete_selected"
        assert page.table.rowCount() == 1
        page.close()
