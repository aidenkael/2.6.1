"""第四轮修正一：0 是合法金额，不得阻止物流与总成本计算。

覆盖任务书第十九节 A 组：
1. product_cost = 0，包装有效、货代有效 → current_quote 正常产生；
2. domestic_shipping = 0 → 正常计算；
3. 两者同时 = 0 → 正常计算物流和系统总成本；
4. product_cost 0 保存后仍然是 0，不是 None；
5. 0 不触发"请填写有效商品成本"阻断；
6. 系统总成本仍正确等于各成本之和；
7. 利润区和系统总成本仍使用同一个 total cost。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from dataclasses import asdict

from profit_accounting_26.application import AppContext, SettingsService
from profit_accounting_26.ui.pages import CalculationPage


@pytest.fixture
def temp_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


@pytest.fixture
def page(qapp, temp_context):
    widget = CalculationPage(temp_context)
    yield widget
    widget.deleteLater()


def _ensure_forwarders(page):
    settings = page.context.settings_service.load()
    shenzhen = SettingsService.new_forwarder("深圳货代", 80.0, 10.0, 8000.0)
    settings["forwarders"] = [asdict(shenzhen)]
    settings["selected_forwarder_id"] = shenzhen.id
    page.context.settings_service.save(settings)
    page.refresh_settings()
    return shenzhen.id


def _arm(page, cost: float, shipping: float):
    """填充完整计算场景（成本 + 包装 + 货代）。"""
    page.product_cost.setValue(cost)
    page.domestic_shipping.setValue(shipping)
    # 当前采用（右卡）是唯一正式包装计算输入
    page.conservative_fields["length"].setValue(25.0)
    page.conservative_fields["width"].setValue(18.0)
    page.conservative_fields["height"].setValue(6.0)
    page.conservative_fields["weight"].setValue(320.0)
    _ensure_forwarders(page)
    page.recalculate()


def test_zero_product_cost_allows_calculation(page):
    """第 1/5 项：商品成本 = 0 时仍正常产生报价，不弹"请填写有效商品成本"。"""
    _arm(page, cost=0.0, shipping=5.0)
    assert page.current_quote is not None
    assert page.current_system_cost is not None
    assert page.current_system_cost > 0  # 物流部分仍正常计算


def test_zero_domestic_shipping_allows_calculation(page):
    """第 2 项：国内运费 = 0 时正常计算。"""
    _arm(page, cost=66.80, shipping=0.0)
    assert page.current_quote is not None
    assert page.current_system_cost is not None


def test_both_zero_allows_full_chain(page):
    """第 3 项：成本与运费同时 = 0 时物流和系统总成本仍正常计算。"""
    _arm(page, cost=0.0, shipping=0.0)
    assert page.current_quote is not None
    assert page.current_system_cost is not None
    # 总成本此时就是纯物流成本，且 > 0（尾程/头程/服务费有效）
    assert page.current_system_cost == pytest.approx(page.current_quote.total_logistics_rmb)


def test_zero_product_cost_stays_zero_after_save_and_reload(qapp, page, monkeypatch):
    """第 4 项：product_cost 0 保存后仍然是 0，不能变成 None。"""
    import PySide6.QtWidgets as qw

    monkeypatch.setattr(qw.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(qw.QMessageBox, "warning", lambda *a, **k: None)
    _arm(page, cost=0.0, shipping=0.0)
    page.save_record()
    rid = page.record_id
    assert rid

    record = page.context.record_service.load(rid)
    assert record.get("product_cost_rmb") == 0.0
    assert record.get("domestic_shipping_rmb") == 0.0
    # observation 采集链路同样保持 0，而非 None
    observation = page.collect_observation()
    assert observation.product_cost_rmb == 0.0
    assert observation.domestic_shipping_rmb == 0.0
    # 重新打开记录后控件仍为 0
    page.load_record_payload(rid)
    assert page.product_cost.value() == pytest.approx(0.0)
    assert page.domestic_shipping.value() == pytest.approx(0.0)


def test_system_total_equals_cost_sum(page):
    """第 6 项：系统总成本 = 采购成本 + 国内运费 + 头程 + 服务费 + 尾程 RMB。"""
    _arm(page, cost=23.80, shipping=4.00)
    quote = page.current_quote
    expected = 23.80 + 4.00 + quote.total_logistics_rmb
    assert page.current_system_cost == pytest.approx(expected)
    # quote 内部拆分：头程(计费重×单价) + 固定服务费 + 尾程 RMB
    assert quote.total_logistics_rmb == pytest.approx(
        quote.weight_fee_rmb + quote.fixed_fee_rmb + page.tail_fee_rmb.value()
    )


def test_profit_area_and_system_total_share_same_cost(page):
    """第 7 项：利润区和系统总成本使用同一个 total cost（0 成本下也成立）。"""
    _arm(page, cost=0.0, shipping=0.0)
    assert page.profit_binder._calculation_total_cost_rmb == pytest.approx(
        page.current_system_cost, abs=0.01
    )
