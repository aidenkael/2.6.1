"""CalculationBinder 规则状态标签测试。

覆盖契约 §11：
- 多规则同时命中只显示合计；
- tooltip 逐条列出规则名称/场景/条件/方向/原币金额/换算 RMB；
- 两场景跨 29 USD 门槛独立判断（通过规则下拉单选 + 双场景刷新）。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from profit_accounting_26.domain.rules import (
    AdjustmentDirection,
    AdjustmentRule,
    AdjustmentType,
    CompareOp,
)
from profit_accounting_26.engines.profit import calculate_profit_scenario

# qapp 由 tests/conftest.py 的会话级 fixture 提供（整个测试会话共用一个
# QApplication）。禁止在本文件内创建 QApplication——反复创建/销毁
# QApplication 会在 Linux offscreen 平台下导致段错误。


class MockSettingsService:
    def load(self):
        return {"exchange_rate_usd_to_rmb": 7.2}


class MockContext:
    settings_service = MockSettingsService()


RATE = 7.2


def _income_rule(rule_id, name, threshold, amount, currency="USD"):
    return AdjustmentRule(
        id=rule_id,
        name=name,
        condition_field="sale_price_usd",
        compare_op=CompareOp.LT,
        condition_value=threshold,
        direction=AdjustmentDirection.INCOME,
        adjustment_type=AdjustmentType.FIXED,
        adjustment_value=amount,
        currency=currency,
    )


def _cost_rule(rule_id, name, threshold, amount, currency="RMB"):
    return AdjustmentRule(
        id=rule_id,
        name=name,
        condition_field="sale_price_usd",
        compare_op=CompareOp.LT,
        condition_value=threshold,
        direction=AdjustmentDirection.COST,
        adjustment_type=AdjustmentType.FIXED,
        adjustment_value=amount,
        currency=currency,
    )


@pytest.fixture
def binder(qapp):
    from profit_accounting_26.ui.ui_loader import load_calculation_panel
    from profit_accounting_26.ui.binders.calculation_binder import CalculationBinder

    ui = load_calculation_panel("profit")
    b = CalculationBinder(ui, MockContext())
    b._ui_root_ref = ui
    yield b


def _scenario_result(rules, price_usd, cost=100.0):
    return calculate_profit_scenario(
        sale_price_usd=price_usd,
        total_cost_rmb=cost,
        exchange_rate=RATE,
        rules=rules,
        scenario="no_activity",
    )


def test_multiple_rules_hit_show_combined_amount_and_tooltip(binder):
    """两条收入规则同时命中：标签只显示合计，tooltip 列出两条明细。"""
    rules = (_income_rule("sub_a", "补贴A", 29.0, 2.99), _income_rule("sub_b", "补贴B", 29.0, 1.00))
    result = _scenario_result(rules, price_usd=20.0)
    assert len([e for e in result.rule_evaluations if e.matched]) == 2

    binder._update_single_rule_status(binder.lbl_na_status, result, "no_activity")
    expected_total = (2.99 + 1.00) * RATE
    assert binder.lbl_na_status.text() == f"已触发 +¥{expected_total:.2f}"
    tip = binder.lbl_na_status.toolTip()
    assert "补贴A" in tip and "补贴B" in tip
    assert "场景" in tip and "条件" in tip and "方向" in tip and "换算 RMB" in tip


def test_income_minus_cost_rules_show_net_adjustment(binder):
    """一收入一成本同时命中：显示净值，净值为负时显示'已调整'警示。"""
    rules = (_income_rule("sub_a", "补贴A", 29.0, 1.00), _cost_rule("fee_a", "费用A", 29.0, 10.0))
    result = _scenario_result(rules, price_usd=20.0)

    binder._update_single_rule_status(binder.lbl_na_status, result, "no_activity")
    net = 1.00 * RATE - 10.0  # 7.2 - 10 = -2.8
    assert net < 0
    assert binder.lbl_na_status.text() == f"已调整 ¥{net:.2f}"
    tip = binder.lbl_na_status.toolTip()
    assert "补贴A" in tip and "费用A" in tip


def test_two_scenarios_judge_independently_across_threshold(binder):
    """选中 29 补贴规则后：无活动 30 USD 未触发，活动后 27 USD（预留 10%）已触发。"""
    rules = (_income_rule("sub_29", "29补贴", 29.0, 2.99),)
    binder.set_rules(rules)
    binder.set_calculation_cost(100.0)
    # 通过规则下拉选中唯一规则
    idx = binder.cmb_role_find("sub_29")
    assert idx >= 0
    binder.cmb_rule.setCurrentIndex(idx)
    # 预留 10%，无活动售价 30 USD
    binder._profit_updating = True
    binder.spin_reserve.setValue(10.0)
    binder._profit_updating = False
    binder._reserve_percent = 10.0
    binder._profit_driver = "no_activity_price"
    binder.txt_na_price_usd.setValue(30.0)
    binder._refresh_all()

    # 无活动 30 >= 29 → 未触发；活动后 30×0.9=27 < 29 → 已触发 +¥21.53
    assert binder.lbl_na_status.text() == "未触发"
    assert binder.lbl_na_status.toolTip() == ""
    assert binder.txt_act_price_usd.value() == pytest.approx(27.0)
    expected = 2.99 * RATE
    assert binder.lbl_act_status.text() == f"已触发 +¥{expected:.2f}"
    assert "29补贴" in binder.lbl_act_status.toolTip()
