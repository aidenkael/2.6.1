"""计算总成本（calculation_total_cost_rmb）所有权回归。

不变量：``calculation_total_cost_rmb`` 是上游状态，只允许两条变更路径：
1. CalculationPage 因上游成本输入变化显式调用 ``set_calculation_cost``；
2. 用户显式编辑计算成本输入。

下游利润控件（活动后利润率 / 标价利率 / 活动预留 / 售价 / 利润额 / 规则）
编辑退出历史快照时，绝不得隐式改写或"恢复"成本。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QWidget

from profit_accounting_26.ui.binders.calculation_binder import CalculationBinder


class MockSettingsService:
    def load(self):
        return {"exchange_rate_usd_to_rmb": 7.2}


class MockContext:
    settings_service = MockSettingsService()


RATE = 7.2


@pytest.fixture
def binder(qapp):
    from profit_accounting_26.ui.ui_loader import load_main_window

    ui = load_main_window()
    page = ui.findChild(QWidget, "pageCalculation")
    instance = CalculationBinder(page, MockContext())
    instance._ui_root_ref = ui  # 防止 .ui 根节点被 GC
    yield instance


def _save_snapshot_record(binder: CalculationBinder, cost: float = 100.0) -> None:
    """构造并保存一条成本=cost 的记录 payload（无活动售价 30 USD）。"""
    binder.reset()
    binder.set_exchange_rate(RATE)
    binder.set_calculation_cost(cost)
    binder._profit_driver = "no_activity_price"
    binder.txt_na_price_usd.setValue(30.0)
    binder._profit_driver = "profit_rate"
    payload = binder.export_profit_scenarios()
    binder.load_from_record({"profit_scenarios": payload})


def _simulate_internal_recalc_during_load(binder: CalculationBinder, live_cost: float) -> None:
    """模拟 load_record_payload 内部 recalculate/set_calculation_cost 捕获当前成本。"""
    binder._loading_record = True
    try:
        binder.set_calculation_cost(live_cost)
    finally:
        binder._loading_record = False


def test_loaded_snapshot_shows_saved_cost(binder):
    _save_snapshot_record(binder, cost=100.0)
    assert binder.is_in_snapshot_mode() is True
    assert binder._calculation_total_cost_rmb == pytest.approx(100.0)
    assert binder.txt_cost_rmb.value() == pytest.approx(100.0)


def test_profit_rate_edit_keeps_snapshot_cost_100(binder):
    """核心缺陷回归：快照显示成本 100、内部另捕获当前成本 110 时，
    仅编辑活动后利润率必须保持成本 100（不得恢复为 110）。"""
    _save_snapshot_record(binder, cost=100.0)
    _simulate_internal_recalc_during_load(binder, live_cost=110.0)

    rate_before = binder.spin_profit_rate.value()
    binder.spin_profit_rate.setValue(rate_before + 5.0)

    assert binder.is_in_snapshot_mode() is False
    assert binder._calculation_total_cost_rmb == pytest.approx(100.0)
    assert binder.txt_cost_rmb.value() == pytest.approx(100.0)


@pytest.mark.parametrize(
    "edit",
    ["list_price_rate", "reserve", "na_price", "na_profit", "act_profit"],
)
def test_all_downstream_profit_edits_keep_snapshot_cost(binder, edit):
    """所有下游利润 driver 编辑（含预留/售价/利润额/规则路径）都不得改写成本。"""
    _save_snapshot_record(binder, cost=100.0)
    _simulate_internal_recalc_during_load(binder, live_cost=110.0)

    if edit == "list_price_rate":
        binder.txt_list_price_rate.setValue(binder.txt_list_price_rate.value() + 3.0)
    elif edit == "reserve":
        binder.spin_reserve.setValue(binder.spin_reserve.value() + 5.0)
    elif edit == "na_price":
        binder.txt_na_price_usd.setValue(binder.txt_na_price_usd.value() + 1.0)
    elif edit == "na_profit":
        binder.txt_na_profit_rmb.setValue(binder.txt_na_profit_rmb.value() + 5.0)
    elif edit == "act_profit":
        binder.txt_act_profit_rmb.setValue(binder.txt_act_profit_rmb.value() + 5.0)

    assert binder._calculation_total_cost_rmb == pytest.approx(100.0)
    assert binder.txt_cost_rmb.value() == pytest.approx(100.0)


def test_rule_change_keeps_snapshot_cost(binder):
    _save_snapshot_record(binder, cost=100.0)
    _simulate_internal_recalc_during_load(binder, live_cost=110.0)

    # 切到“全部启用规则”（最后一项），触发 currentIndexChanged 退出快照
    binder.cmb_rule.setCurrentIndex(binder.cmb_rule.count() - 1)
    assert binder.is_in_snapshot_mode() is False
    assert binder._calculation_total_cost_rmb == pytest.approx(100.0)
    assert binder.txt_cost_rmb.value() == pytest.approx(100.0)


def test_user_explicit_cost_edit_wins_and_survives_profit_edits(binder):
    """用户显式把成本改为 120 后，后续利润率编辑保持 120。"""
    _save_snapshot_record(binder, cost=100.0)
    _simulate_internal_recalc_during_load(binder, live_cost=110.0)

    binder.txt_cost_rmb.setValue(120.0)  # 用户显式编辑计算成本输入
    assert binder._calculation_total_cost_rmb == pytest.approx(120.0)

    rate_before = binder.spin_profit_rate.value()
    binder.spin_profit_rate.setValue(rate_before - 2.0)

    assert binder._calculation_total_cost_rmb == pytest.approx(120.0)
    assert binder.txt_cost_rmb.value() == pytest.approx(120.0)


def test_upstream_explicit_set_calculation_cost_wins(binder):
    """CalculationPage 显式 set_calculation_cost(130) 后，后续利润编辑保持 130。"""
    _save_snapshot_record(binder, cost=100.0)

    binder.set_calculation_cost(130.0)  # 上游物流/商品成本变化
    assert binder._calculation_total_cost_rmb == pytest.approx(130.0)
    assert binder.is_in_snapshot_mode() is False

    rate_before = binder.spin_profit_rate.value()
    binder.spin_profit_rate.setValue(rate_before + 1.0)

    assert binder._calculation_total_cost_rmb == pytest.approx(130.0)
    assert binder.txt_cost_rmb.value() == pytest.approx(130.0)


def test_exchange_rate_restore_semantics_unchanged(binder):
    """快照退出时恢复"当前设置"汇率是既有设计（当前推算用当前设置）；
    本测试锁定该语义不被成本所有权修复意外改变。"""
    _save_snapshot_record(binder, cost=100.0)  # 保存时汇率 7.2
    binder.capture_current_settings(exchange_rate=7.0, rules=(), selected_rule_id="")

    rate_before = binder.spin_profit_rate.value()
    binder.spin_profit_rate.setValue(rate_before + 5.0)

    assert binder._exchange_rate == pytest.approx(7.0)  # 当前设置汇率
    assert binder._calculation_total_cost_rmb == pytest.approx(100.0)  # 成本不恢复
