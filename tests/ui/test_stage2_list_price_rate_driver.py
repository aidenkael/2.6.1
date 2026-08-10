"""阶段 2：标价利率可编辑反推 + 利润区三板块微调。

覆盖合同要求的计算场景：
1. 新记录默认 reserve=15% / 活动后利润率=25%，行为与阶段2前一致；
2. 标价利率 30% → 目标标价利润 = 总成本×30%，复用现有 solver 反推；
3. 补贴规则触发时通过现有 solver 反推，不绕过规则；
4. 先改标价利率再改活动后利润率 → 活动后利润率成为 driver；
5. 先改标价利率再改 SHEIN标价 → 标价售价成为 driver；
6. 先改标价利率再发生上游成本变化 → 保持原正式逻辑（回到活动后利润率 driver）；
7. 活动预留变化 → 保持活动后利润率目标逻辑；
8. 历史快照加载 → 标价利率按保存时标价利润/保存时成本派生显示；
9. 打开历史后直接编辑标价利率 → 退出快照模式，按当前设置推算；
10. 负标价利率可输入、保存、显示、反推。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QDoubleSpinBox, QGridLayout, QWidget

from profit_accounting_26.domain.rules import (
    AdjustmentDirection,
    AdjustmentRule,
    AdjustmentType,
    CompareOp,
)
from profit_accounting_26.ui.binders.calculation_binder import (
    DRIVER_NO_ACTIVITY_PRICE,
    DRIVER_NO_ACTIVITY_PROFIT,
    DRIVER_NO_ACTIVITY_PROFIT_RATE,
    DRIVER_PROFIT_RATE,
)


class MockSettingsService:
    def load(self):
        return {"exchange_rate_usd_to_rmb": 7.2}


class MockContext:
    settings_service = MockSettingsService()


RATE = 7.2


@pytest.fixture
def binder(qapp):
    from profit_accounting_26.ui.ui_loader import load_main_window
    from profit_accounting_26.ui.binders.calculation_binder import CalculationBinder

    ui = load_main_window()
    page = ui.findChild(QWidget, "pageCalculation")
    instance = CalculationBinder(page, MockContext())
    instance._ui_root_ref = ui
    yield instance


def _make_binder(qapp):
    from profit_accounting_26.ui.ui_loader import load_main_window
    from profit_accounting_26.ui.binders.calculation_binder import CalculationBinder

    ui = load_main_window()
    page = ui.findChild(QWidget, "pageCalculation")
    instance = CalculationBinder(page, MockContext())
    instance._ui_root_ref = ui
    return instance


def _subsidy_rule() -> AdjustmentRule:
    return AdjustmentRule(
        id="under_29_subsidy",
        name="SHEIN 29美元以下运费补贴",
        condition_field="sale_price_usd",
        compare_op=CompareOp.LT,
        condition_value=29.0,
        direction=AdjustmentDirection.INCOME,
        adjustment_type=AdjustmentType.FIXED,
        adjustment_value=2.99,
        currency="USD",
    )


def test_new_record_defaults_unchanged(binder):
    """新记录默认 15% / 25%，driver 与阶段2前一致。"""
    assert binder.spin_reserve.value() == pytest.approx(15.0)
    assert binder.spin_profit_rate.value() == pytest.approx(25.0)
    assert binder._profit_driver == DRIVER_PROFIT_RATE

    binder.set_calculation_cost(100.0)
    expected_price = (100.0 + 25.0) / (1 - 0.15) / RATE
    assert binder.txt_na_price_usd.value() == pytest.approx(expected_price, abs=0.01)
    assert binder.spin_profit_rate.value() == pytest.approx(25.0)


def test_list_price_rate_drives_reverse_solve(binder):
    """标价利率 30%：目标标价利润 = 总成本×30%，反推标价正确。"""
    binder.set_calculation_cost(100.0)
    binder.txt_list_price_rate.setValue(30.0)

    assert binder._profit_driver == DRIVER_NO_ACTIVITY_PROFIT_RATE
    assert binder.txt_list_price_rate.value() == pytest.approx(30.0)
    expected_na_price = (100.0 + 30.0) / RATE
    assert binder.txt_na_price_usd.value() == pytest.approx(expected_na_price, abs=0.01)
    assert binder.txt_na_profit_rmb.value() == pytest.approx(30.0, abs=0.01)

    # 活动区由现有双场景算法计算
    act_price = binder.txt_na_price_usd.value() * (1 - 0.15)
    assert binder.txt_act_price_usd.value() == pytest.approx(act_price, abs=0.01)
    expected_act_profit = binder._no_activity_price_usd * (1 - 0.15) * RATE - 100.0
    assert binder.txt_act_profit_rmb.value() == pytest.approx(expected_act_profit, abs=0.01)
    assert binder.spin_profit_rate.value() == pytest.approx(
        binder.txt_act_profit_rmb.value() / 100.0 * 100.0, abs=0.01
    )


def test_subsidy_rule_uses_solver_not_naive(binder):
    """补贴触发时修改标价利率：必须走 solver，不能 cost×(1+利润率) 绕过规则。"""
    binder.set_rules((_subsidy_rule(),))
    binder.set_selected_rule_id("under_29_subsidy")
    binder.set_calculation_cost(100.0)
    binder.txt_list_price_rate.setValue(30.0)

    assert binder._profit_driver == DRIVER_NO_ACTIVITY_PROFIT_RATE
    naive_price = (100.0 * 1.30) / RATE  # 18.06：绕过补贴的简单算法
    assert binder.txt_na_price_usd.value() < naive_price
    assert binder.txt_na_price_usd.value() == pytest.approx(15.07, abs=0.02)
    assert binder.txt_na_profit_rmb.value() == pytest.approx(30.0, abs=0.1)
    assert "已触发" in binder.lbl_na_status.text()


def test_rate_then_activity_rate_switches_driver(binder):
    """先改标价利率，随后改活动后利润率 → 活动后利润率成为 driver。"""
    binder.set_calculation_cost(100.0)
    binder.txt_list_price_rate.setValue(30.0)
    assert binder._profit_driver == DRIVER_NO_ACTIVITY_PROFIT_RATE

    binder.spin_profit_rate.setValue(35.0)
    assert binder._profit_driver == DRIVER_PROFIT_RATE


def test_rate_then_na_price_switches_driver(binder):
    """先改标价利率，随后改 SHEIN标价 → 标价售价成为 driver。"""
    binder.set_calculation_cost(100.0)
    binder.txt_list_price_rate.setValue(30.0)
    assert binder._profit_driver == DRIVER_NO_ACTIVITY_PROFIT_RATE

    binder.txt_na_price_usd.setValue(20.0)
    assert binder._profit_driver == DRIVER_NO_ACTIVITY_PRICE


def test_rate_then_upstream_cost_change_keeps_old_logic(binder):
    """标价利率编辑后发生上游成本变化：回到活动后利润率 driver，不变成永久 sticky。"""
    binder.set_calculation_cost(100.0)
    binder.txt_list_price_rate.setValue(30.0)
    derived_act_rate = binder.spin_profit_rate.value()
    assert binder._profit_driver == DRIVER_NO_ACTIVITY_PROFIT_RATE

    binder.set_calculation_cost(150.0)
    assert binder._profit_driver == DRIVER_PROFIT_RATE
    assert binder.spin_profit_rate.value() == pytest.approx(derived_act_rate, abs=0.01)


def test_reserve_change_keeps_activity_rate_target(binder):
    """活动预留变化：保持当前活动后利润率目标，重算其余依赖值。"""
    binder.set_calculation_cost(100.0)
    binder.txt_list_price_rate.setValue(30.0)
    rate_target = binder.spin_profit_rate.value()

    binder.spin_reserve.setValue(20.0)
    assert binder._profit_driver == DRIVER_PROFIT_RATE
    assert binder.spin_profit_rate.value() == pytest.approx(rate_target, abs=0.01)


def test_history_load_derives_rate_from_snapshot(qapp):
    """历史加载：标价利率按保存时标价利润/保存时成本派生，不按当前重算。"""
    b1 = _make_binder(qapp)
    b1.set_calculation_cost(200.0)
    b1._profit_driver = DRIVER_NO_ACTIVITY_PROFIT
    b1.txt_na_profit_rmb.setValue(50.0)  # 标价利率 = 25%
    snapshot = b1.export_profit_scenarios()

    b2 = _make_binder(qapp)
    b2.set_calculation_cost(100.0)  # 当前成本不同，不得按当前重算
    b2.load_from_record({"profit_scenarios": snapshot})

    assert b2.is_in_snapshot_mode()
    assert b2.txt_cost_rmb.value() == pytest.approx(200.0)
    assert b2.txt_na_profit_rmb.value() == pytest.approx(50.0)
    assert b2.txt_list_price_rate.value() == pytest.approx(25.0, abs=0.01)


def test_edit_rate_in_snapshot_exits_to_current(qapp):
    """打开历史后直接编辑标价利率：退出快照，按当前设置重新推算。"""
    b1 = _make_binder(qapp)
    b1.set_calculation_cost(200.0)
    b1._profit_driver = DRIVER_NO_ACTIVITY_PROFIT
    b1.txt_na_profit_rmb.setValue(50.0)
    snapshot = b1.export_profit_scenarios()

    b2 = _make_binder(qapp)
    b2.load_from_record({"profit_scenarios": snapshot})
    assert b2.is_in_snapshot_mode()

    b2.txt_list_price_rate.setValue(40.0)
    assert not b2.is_in_snapshot_mode()
    assert b2._profit_driver == DRIVER_NO_ACTIVITY_PROFIT_RATE
    # 按当前设置重算：目标标价利润 = 200 × 40% = 80
    assert b2.txt_na_profit_rmb.value() == pytest.approx(80.0, abs=0.01)
    expected_na_price = (200.0 + 80.0) / RATE
    assert b2.txt_na_price_usd.value() == pytest.approx(expected_na_price, abs=0.01)


def test_negative_rate_input_save_reload(qapp):
    """负标价利率可输入、保存、显示、反推。"""
    binder = _make_binder(qapp)
    binder.set_calculation_cost(100.0)
    binder.txt_list_price_rate.setValue(-10.0)

    assert binder._profit_driver == DRIVER_NO_ACTIVITY_PROFIT_RATE
    assert binder.txt_list_price_rate.value() == pytest.approx(-10.0)
    expected_price = (100.0 - 10.0) / RATE
    assert binder.txt_na_price_usd.value() == pytest.approx(expected_price, abs=0.01)
    assert binder.txt_na_profit_rmb.value() == pytest.approx(-10.0, abs=0.01)

    snapshot = binder.export_profit_scenarios()
    reloaded = _make_binder(qapp)
    reloaded.load_from_record({"profit_scenarios": snapshot})
    assert reloaded.txt_list_price_rate.value() == pytest.approx(-10.0, abs=0.01)


def test_profit_fields_final_order_and_light_group_gap(qapp, binder):
    """9 字段最终排列 + 三板块仅靠组间轻量空隙区分。"""
    page = binder.page
    top = page.window()
    top.resize(1920, 1080)
    top.show()
    qapp.processEvents()

    def center_x(name: str) -> float:
        widget = page.findChild(QDoubleSpinBox, name)
        assert widget is not None, f"缺少字段 {name}"
        return widget.mapTo(page, widget.rect().center()).x()

    order = [
        "txtSheinPriceRmb",      # 1 SHEIN核价
        "txtCalculatedCostRmb",  # 2 计算总成本
        "txtNoActivityPriceRmb", # 3 SHEIN标价
        "txtListPriceProfitRate",# 4 标价利率
        "txtNoActivityProfitRmb",# 5 标价利润
        "spinPromotionReserve",  # 6 活动预留
        "spinProfitRate",        # 7 利润率（活动后）
        "txtActivityPriceRmb",   # 8 活动后售价
        "txtActivityProfitRmb",  # 9 活动后利润
    ]
    xs = [center_x(name) for name in order]
    assert xs == sorted(xs), f"9 字段水平顺序错误: {list(zip(order, xs))}"

    def gap(left_name: str, right_name: str) -> float:
        left = page.findChild(QDoubleSpinBox, left_name)
        right = page.findChild(QDoubleSpinBox, right_name)
        return (
            right.mapTo(page, right.rect().topLeft()).x()
            - left.mapTo(page, left.rect().topRight()).x()
        )

    internal_gap = gap("txtNoActivityPriceRmb", "txtListPriceProfitRate")
    group_gap_1 = gap("txtCalculatedCostRmb", "txtNoActivityPriceRmb")
    group_gap_2 = gap("txtNoActivityProfitRmb", "spinPromotionReserve")
    assert group_gap_1 > internal_gap, "核价成本区→标价区缺少组间空隙"
    assert group_gap_2 > internal_gap, "标价区→活动区缺少组间空隙"

    grid = page.findChild(QGridLayout, "profitFieldsGrid")
    assert grid is not None
    # 组间空隙为固定 6px 的轻量间隔（不使用大卡片/分隔线）
    from PySide6.QtWidgets import QFrame

    for name in ("profitGroupSpacer1", "profitGroupSpacer2"):
        spacer = page.findChild(QFrame, name)
        assert spacer is not None and spacer.width() == 6, f"{name} 应保持 6px 轻量空隙"
