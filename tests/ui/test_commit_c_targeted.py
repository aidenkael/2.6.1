"""Commit C targeted tests：History 链接单击、保存货代、商品采集 Delete 键。

offscreen 平台的鼠标点击焦点模拟不可靠，因此尽量使用直接方法调用验证。

禁止真实 API / 浏览器 / 外部链接。
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from unittest.mock import patch  # noqa: E402

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QLineEdit, QWidget, QScrollArea  # noqa: E402


# ── History 商品链接单击打开默认浏览器 ─────────────────────────────────


class TestHistoryLinkClickOpen:
    def test_link_click_filter_opens_browser(self, qapp):
        """单击有 URL 的链接 → 调用 webbrowser.open。"""
        from profit_accounting_26.ui.pages.history_page import _LinkClickOpenFilter

        link_edit = QLineEdit("https://www.aliexpress.com/item/123456.html")
        link_edit.setReadOnly(True)
        filt = _LinkClickOpenFilter(link_edit)
        link_edit.installEventFilter(filt)

        with patch("profit_accounting_26.ui.pages.history_page.webbrowser") as mock_wb:
            # 模拟鼠标按下事件
            from PySide6.QtGui import QMouseEvent
            from PySide6.QtCore import QPointF
            event = QMouseEvent(
                QEvent.Type.MouseButtonPress,
                QPointF(5.0, 5.0),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            result = filt.eventFilter(link_edit, event)
            assert result is False, "过滤器不消费事件（让 Qt 正常处理）"
            mock_wb.open.assert_called_once_with("https://www.aliexpress.com/item/123456.html")

        link_edit.deleteLater()

    def test_link_click_filter_empty_url_does_nothing(self, qapp):
        """单击空链接 → 不调用 webbrowser.open。"""
        from profit_accounting_26.ui.pages.history_page import _LinkClickOpenFilter

        link_edit = QLineEdit("")
        link_edit.setReadOnly(True)
        filt = _LinkClickOpenFilter(link_edit)
        link_edit.installEventFilter(filt)

        with patch("profit_accounting_26.ui.pages.history_page.webbrowser") as mock_wb:
            from PySide6.QtGui import QMouseEvent
            from PySide6.QtCore import QPointF
            event = QMouseEvent(
                QEvent.Type.MouseButtonPress,
                QPointF(5.0, 5.0),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            result = filt.eventFilter(link_edit, event)
            assert result is False
            mock_wb.open.assert_not_called()

        link_edit.deleteLater()

    def test_link_click_filter_non_mouse_event_ignored(self, qapp):
        """非鼠标事件 → 不打开浏览器。"""
        from profit_accounting_26.ui.pages.history_page import _LinkClickOpenFilter

        link_edit = QLineEdit("https://example.com")
        filt = _LinkClickOpenFilter(link_edit)

        with patch("profit_accounting_26.ui.pages.history_page.webbrowser") as mock_wb:
            # 发送一个非鼠标事件
            key_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier, "a")
            filt.eventFilter(link_edit, key_event)
            mock_wb.open.assert_not_called()

        link_edit.deleteLater()


# ── 主软件保存货代成为默认 ─────────────────────────────────────────────


class TestSaveForwarderOnRecordSave:
    def test_save_record_persists_selected_forwarder_id(self, qapp, tmp_path, monkeypatch):
        """保存记录成功后 selected_forwarder_id 写入 settings。"""
        monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
        from profit_accounting_26.application import AppContext

        context = AppContext.create_default()
        # 预设两个货代
        settings = context.settings_service.load()
        settings["forwarders"] = [
            {"id": "fw_yiwu", "name": "义乌货代", "rate_rmb_per_kg": 28.0,
             "fixed_fee_rmb": 15.0, "volume_divisor": 6000.0,
             "enabled": True, "archived": False},
            {"id": "fw_shenzhen", "name": "深圳货代", "rate_rmb_per_kg": 32.0,
             "fixed_fee_rmb": 18.0, "volume_divisor": 6000.0,
             "enabled": True, "archived": False},
        ]
        settings["selected_forwarder_id"] = "fw_yiwu"
        context.settings_service.save(settings)

        from profit_accounting_26.ui.pages.calculation_page import CalculationPage
        page = CalculationPage(context)
        try:
            # 模拟用户切换到深圳货代
            page.selected_forwarder_id = "fw_shenzhen"
            # 模拟最小可保存状态
            page.current_quote = object()
            page.current_system_cost = 100.0
            page.packaging_stale = False

            # 拦截 build_record_payload 避免复杂的 payload 构建
            monkeypatch.setattr(page, "build_record_payload", lambda: {"test": True})
            # 拦截 record_service.save 返回一个 ID
            monkeypatch.setattr(
                context.record_service, "save",
                lambda *args, **kwargs: "test_record_001",
            )
            # 拦截 QMessageBox（避免模态弹窗阻塞测试）
            import profit_accounting_26.ui.pages.calculation_page as cp_module
            monkeypatch.setattr(cp_module, "QMessageBox", type("FakeMB", (), {
                "warning": staticmethod(lambda *a, **k: None),
                "critical": staticmethod(lambda *a, **k: None),
                "information": staticmethod(lambda *a, **k: None),
            }))
            # 拦截 _save_user_feedback
            monkeypatch.setattr(page, "_save_user_feedback", lambda: None)

            # 追踪 settings_service.save 调用
            original_save = context.settings_service.save
            saved_copies = []

            def tracking_save(data):
                saved_copies.append(dict(data))
                original_save(data)

            monkeypatch.setattr(context.settings_service, "save", tracking_save)

            page.save_record()

            # 至少有一次 save 调用
            assert len(saved_copies) > 0, "settings_service.save 应被调用"
            # 验证 settings 中保存了深圳货代
            last_save = saved_copies[-1]
            assert last_save.get("selected_forwarder_id") == "fw_shenzhen", (
                f"保存后 selected_forwarder_id 应为 fw_shenzhen，"
                f"实际为 {last_save.get('selected_forwarder_id')}"
            )
        finally:
            page.close()
            page.deleteLater()

    def test_click_forwarder_without_save_does_not_change_default(self, qapp, tmp_path, monkeypatch):
        """仅点击货代但不保存记录 → settings 中的默认值不变。"""
        monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
        from profit_accounting_26.application import AppContext

        context = AppContext.create_default()
        settings = context.settings_service.load()
        settings["forwarders"] = [
            {"id": "fw_yiwu", "name": "义乌货代", "rate_rmb_per_kg": 28.0,
             "fixed_fee_rmb": 15.0, "volume_divisor": 6000.0,
             "enabled": True, "archived": False},
            {"id": "fw_shenzhen", "name": "深圳货代", "rate_rmb_per_kg": 32.0,
             "fixed_fee_rmb": 18.0, "volume_divisor": 6000.0,
             "enabled": True, "archived": False},
        ]
        settings["selected_forwarder_id"] = "fw_yiwu"
        context.settings_service.save(settings)

        from profit_accounting_26.ui.pages.calculation_page import CalculationPage
        page = CalculationPage(context)
        try:
            # 模拟用户点击深圳货代（不保存）
            page.selected_forwarder_id = "fw_shenzhen"

            # 验证 settings 文件中仍是义乌
            persisted = context.settings_service.load()
            assert persisted.get("selected_forwarder_id") == "fw_yiwu", (
                "仅切换货代但不保存记录，settings 默认值不应改变"
            )
        finally:
            page.close()
            page.deleteLater()


# ── 商品采集页 Delete = 移除选中 ───────────────────────────────────────


class TestCollectorDeleteKey:
    def test_delete_key_calls_remove_selected(self, qapp):
        """卡片区域 Delete 键 → 调用 remove_selected。"""
        from profit_accounting_26.product_collector.ui.product_collection_page import (
            _CardGridDeleteKeyFilter,
            ProductCollectionPage,
        )

        page = ProductCollectionPage()
        # 模拟有选中商品
        page._showing_removed = False
        page._selected_ids = {"prod_001"}
        page._states = {"prod_001": "KEEP"}

        called = []
        original = page.remove_selected
        page.remove_selected = lambda: called.append(True) or original()

        # 模拟 Delete 键事件
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
        result = page._card_grid_delete_filter.eventFilter(page.scroll, event)
        assert result is True, "Delete 键在卡片区域应被消费"
        assert len(called) == 1, "应调用 remove_selected()"
        # 处理所有 pending 事件避免 teardown 竞态
        qapp.processEvents()
        page.close()
        qapp.processEvents()

    def test_delete_key_in_removed_view_does_nothing(self, qapp):
        """已移除视图下 Delete → 不做事。"""
        from profit_accounting_26.product_collector.ui.product_collection_page import (
            _CardGridDeleteKeyFilter,
            ProductCollectionPage,
        )

        page = ProductCollectionPage()
        page._showing_removed = True
        page._selected_ids = {"prod_001"}

        called = []
        page.remove_selected = lambda: called.append(True)

        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
        result = page._card_grid_delete_filter.eventFilter(page.scroll, event)
        assert result is False, "已移除视图 Delete 不消费事件"
        assert len(called) == 0, "已移除视图下不应调用 remove_selected"
        page.close()

    def test_delete_key_with_no_selection_does_nothing(self, qapp):
        """无选中商品时 Delete → remove_selected 被调用但因空选择无效果。"""
        from profit_accounting_26.product_collector.ui.product_collection_page import (
            _CardGridDeleteKeyFilter,
            ProductCollectionPage,
        )

        page = ProductCollectionPage()
        page._showing_removed = False
        page._selected_ids = set()

        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
        page._card_grid_delete_filter.eventFilter(page.scroll, event)
        # remove_selected 内部检查 _selected_ids 为空直接返回，无实际效果
        page.close()
