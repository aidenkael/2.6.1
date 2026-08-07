"""ForwarderCardsController 单测（第二阶段 Controller 拆分）。

覆盖：
1. 启用 N 家货代 → N 张动态 QuoteCard（停用/归档不建卡）；
2. 卡片顺序：义乌 → 深圳 → 其他按名称；
3. selected_forwarder_id 失效时 rebuild 自动回退第一家；
4. select_forwarder 后 ID 更新；
5. select_forwarder 后 forwarder_selection_changed=True；
6. select_forwarder 恰好触发 mark_dirty / recalculate 各一次；
7. 页面 settings 被整体替换后 rebuild 读取新 dict（provider 语义，
   不调用 settings_service.load()）；
8. CalculationPage 兼容代理与 clear_new 后 flag 复位。

约束：qapp 由 tests/conftest.py 的会话级 fixture 提供，禁止在本文件内
创建 QApplication。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QMessageBox

from profit_accounting_26.application import AppContext
from profit_accounting_26.ui.widgets import QuoteCard


@pytest.fixture
def temp_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


@pytest.fixture
def page(qapp, temp_context):
    from profit_accounting_26.ui.pages import CalculationPage

    p = CalculationPage(temp_context)
    yield p
    p.deleteLater()
    qapp.processEvents()


def _forwarder(forwarder_id: str, name: str, *, enabled: bool = True, archived: bool = False) -> dict:
    return {
        "id": forwarder_id,
        "name": name,
        "rate_rmb_per_kg": 80.0,
        "fixed_fee_rmb": 10.0,
        "volume_divisor": 8000.0,
        "enabled": enabled,
        "archived": archived,
    }


def _layout_card_ids(page) -> list[str]:
    """按布局实际顺序读取动态货代卡 ID。"""
    layout = page.forwarder_cards_layout
    ids: list[str] = []
    for index in range(layout.count()):
        widget = layout.itemAt(index).widget()
        if isinstance(widget, QuoteCard):
            ids.append(widget.forwarder_id)
    return ids


# 1. 启用 N 家货代 → N 张动态 QuoteCard；停用/归档不建卡
def test_enabled_forwarders_create_matching_cards(page):
    # defaults.json：深圳 + 义乌，均启用
    assert len(page.quote_cards) == 2
    assert set(page.quote_cards) == {"forwarder_shenzhen_default", "forwarder_yiwu_default"}

    page.settings["forwarders"] = [
        *page.settings["forwarders"],
        _forwarder("forwarder_guangzhou", "广州货代"),
        _forwarder("forwarder_disabled", "停用货代", enabled=False),
        _forwarder("forwarder_archived", "归档货代", archived=True),
    ]
    page.rebuild_quote_cards()

    assert len(page.quote_cards) == 3
    assert set(page.quote_cards) == {
        "forwarder_shenzhen_default",
        "forwarder_yiwu_default",
        "forwarder_guangzhou",
    }


# 2. 排序保持：义乌 → 深圳 → 其他按名称（名称按 Unicode 码点比较）
def test_card_order_yiwu_shenzhen_then_name(page):
    page.settings["forwarders"] = [
        _forwarder("forwarder_b", "B货代"),
        _forwarder("forwarder_shenzhen_default", "深圳货代"),
        _forwarder("forwarder_a", "A货代"),
        _forwarder("forwarder_yiwu_default", "义乌货代"),
    ]
    page.rebuild_quote_cards()

    assert _layout_card_ids(page) == [
        "forwarder_yiwu_default",
        "forwarder_shenzhen_default",
        "forwarder_a",
        "forwarder_b",
    ]


# 3. selected_forwarder_id 无效时 rebuild 自动回退第一家
def test_invalid_selection_falls_back_to_first_enabled(page):
    page.selected_forwarder_id = "forwarder_missing"
    page.rebuild_quote_cards()

    # 排序后第一家是义乌货代
    assert page.selected_forwarder_id == "forwarder_yiwu_default"
    assert page.quote_cards["forwarder_yiwu_default"].select_button.isChecked()
    assert not page.quote_cards["forwarder_shenzhen_default"].select_button.isChecked()


# 4. select_forwarder 后 ID 更新
def test_select_forwarder_updates_id(page):
    page.select_forwarder("forwarder_shenzhen_default")
    assert page.selected_forwarder_id == "forwarder_shenzhen_default"
    assert page.quote_cards["forwarder_shenzhen_default"].select_button.isChecked()


# 5. select_forwarder 后 forwarder_selection_changed=True
def test_select_forwarder_sets_flag(page):
    assert page.forwarder_selection_changed is False
    page.select_forwarder("forwarder_shenzhen_default")
    assert page.forwarder_selection_changed is True


# 6. mark_dirty_callback 与 recalculate_callback 各执行恰好一次
def test_select_forwarder_invokes_callbacks_exactly_once(page):
    controller = page.forwarder_cards_controller
    dirty_calls: list[int] = []
    recalc_calls: list[int] = []
    controller._mark_dirty_callback = lambda: dirty_calls.append(1)
    controller._recalculate_callback = lambda: recalc_calls.append(1)

    page.select_forwarder("forwarder_shenzhen_default")

    assert len(dirty_calls) == 1
    assert len(recalc_calls) == 1


# 7. settings 被页面替换后再次 rebuild：读取新 dict，不用旧 dict，不调 load()
def test_rebuild_follows_page_settings_replacement(page, monkeypatch):
    settings_a = page.settings  # A：页面构造时的 dict
    service = page.context.settings_service
    original_load = service.load
    original_forwarders = service.forwarders_from_settings
    load_calls: list[int] = []
    received: list[dict] = []
    monkeypatch.setattr(service, "load", lambda: load_calls.append(1) or original_load())
    monkeypatch.setattr(
        service,
        "forwarders_from_settings",
        lambda settings: received.append(settings) or original_forwarders(settings),
    )

    # 模拟 refresh_settings()：page.settings 被换成新 dict B（停用深圳、新增广州）
    settings_b = original_load()
    settings_b["forwarders"] = [
        _forwarder("forwarder_yiwu_default", "义乌货代"),
        _forwarder("forwarder_shenzhen_default", "深圳货代", enabled=False),
        _forwarder("forwarder_guangzhou", "广州货代"),
    ]
    page.settings = settings_b

    page.rebuild_quote_cards()

    # rebuild 读取的就是 B：深圳停用不建卡，广州建卡
    assert received == [settings_b]
    assert set(page.quote_cards) == {"forwarder_yiwu_default", "forwarder_guangzhou"}
    # Controller 未调用 settings_service.load()
    assert load_calls == []
    # 旧 dict A 未被触碰（仍是 2 家默认货代）
    assert len(settings_a["forwarders"]) == 2


# 8. CalculationPage 兼容代理与 clear_new 复位
def test_page_compat_proxies_and_clear_new_reset(page, monkeypatch):
    controller = page.forwarder_cards_controller

    assert page.quote_cards is controller.quote_cards

    page.selected_forwarder_id = "forwarder_shenzhen_default"
    assert controller.selected_forwarder_id == "forwarder_shenzhen_default"
    assert page.selected_forwarder_id == "forwarder_shenzhen_default"

    page.forwarder_selection_changed = False
    assert controller.forwarder_selection_changed is False

    # 用户切换货代 → flag 置位；clear_new 后复位
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    page.select_forwarder("forwarder_shenzhen_default")
    assert page.forwarder_selection_changed is True
    page.clear_new()
    assert page.forwarder_selection_changed is False
