"""利润双场景引擎测试。

覆盖契约 §15.3 的 12 个利润联动场景：
1. 修改无活动售价
2. 修改无活动利润
3. 修改活动后利润且活动预留不变
4. 修改利润率
5. 修改活动预留且无活动售价不变
6. 修改计算总成本
7. 上方成本变化覆盖利润区手动成本
8. 汇率变化更新冻结币种
9. 两场景跨 29 USD 门槛时状态独立变化
10. 条件规则跳变下反推最低有效售价
11. 防递归，不产生多次信号风暴
12. 总成本为 0 时安全显示
"""

from __future__ import annotations

import pytest

from profit_accounting_26.domain.rules import (
    AdjustmentDirection,
    AdjustmentRule,
    AdjustmentType,
    CompareOp,
)
from profit_accounting_26.engines.profit import (
    calculate_dual_profit,
    calculate_profit_scenario,
    sale_price_for_scenario_target_profit,
)


# ---------------------------------------------------------------------------
# 测试用规则：售价低于 29 USD 时增加 2.99 USD 收入
# ---------------------------------------------------------------------------

def _subsidy_rule() -> AdjustmentRule:
    return AdjustmentRule(
        id="subsidy_29",
        name="低于29美元补贴",
        condition_field="sale_price_usd",
        compare_op=CompareOp.LT,
        condition_value=29.0,
        direction=AdjustmentDirection.INCOME,
        adjustment_type=AdjustmentType.FIXED,
        adjustment_value=2.99,
        currency="USD",
    )


RULES = (_subsidy_rule(),)
COST = 200.0
RATE = 7.2


# ---------------------------------------------------------------------------
# 场景 1: 修改无活动售价
# ---------------------------------------------------------------------------

def test_modify_no_activity_price():
    """无活动售价变化时，无活动利润和活动后利润同步更新。"""
    r1 = calculate_dual_profit(
        no_activity_price_usd=30.0, reserve_percent=10.0,
        total_cost_rmb=COST, exchange_rate=RATE, rules=RULES,
    )
    r2 = calculate_dual_profit(
        no_activity_price_usd=35.0, reserve_percent=10.0,
        total_cost_rmb=COST, exchange_rate=RATE, rules=RULES,
    )
    assert r2.no_activity.profit_rmb > r1.no_activity.profit_rmb
    assert r2.activity.profit_rmb > r1.activity.profit_rmb


# ---------------------------------------------------------------------------
# 场景 2: 修改无活动利润（反推售价）
# ---------------------------------------------------------------------------

def test_reverse_solve_no_activity_profit():
    """给定目标无活动利润，反推最低有效无活动售价。"""
    target = 50.0
    price = sale_price_for_scenario_target_profit(
        total_cost_rmb=COST, target_profit_rmb=target,
        exchange_rate=RATE, rules=RULES, scenario="no_activity",
    )
    result = calculate_profit_scenario(
        sale_price_usd=price, total_cost_rmb=COST,
        exchange_rate=RATE, rules=RULES, scenario="no_activity",
    )
    assert result.profit_rmb >= target - 0.01  # 允许浮点误差


# ---------------------------------------------------------------------------
# 场景 3: 修改活动后利润且活动预留不变
# ---------------------------------------------------------------------------

def test_reverse_solve_activity_profit():
    """给定目标活动后利润，反推无活动售价（活动预留不变）。"""
    target = 30.0
    reserve = 10.0
    # 反推活动后售价
    act_price = sale_price_for_scenario_target_profit(
        total_cost_rmb=COST, target_profit_rmb=target,
        exchange_rate=RATE, rules=RULES, scenario="activity",
    )
    # 反推无活动售价
    na_price = act_price / (1 - reserve / 100.0)
    result = calculate_dual_profit(
        no_activity_price_usd=na_price, reserve_percent=reserve,
        total_cost_rmb=COST, exchange_rate=RATE, rules=RULES,
    )
    assert abs(result.activity.profit_rmb - target) < 0.01


# ---------------------------------------------------------------------------
# 场景 4: 修改利润率
# ---------------------------------------------------------------------------

def test_profit_rate_driver():
    """利润率 = 活动后利润 / 计算总成本。"""
    r = calculate_dual_profit(
        no_activity_price_usd=40.0, reserve_percent=10.0,
        total_cost_rmb=COST, exchange_rate=RATE, rules=(),
    )
    expected_rate = r.activity.profit_rmb / COST
    assert abs(r.profit_rate - expected_rate) < 1e-6


# ---------------------------------------------------------------------------
# 场景 5: 修改活动预留且无活动售价不变
# ---------------------------------------------------------------------------

def test_reserve_change():
    """活动预留变化时，活动后售价和利润变化，无活动售价不变。"""
    na_price = 30.0
    r1 = calculate_dual_profit(
        no_activity_price_usd=na_price, reserve_percent=5.0,
        total_cost_rmb=COST, exchange_rate=RATE, rules=(),
    )
    r2 = calculate_dual_profit(
        no_activity_price_usd=na_price, reserve_percent=15.0,
        total_cost_rmb=COST, exchange_rate=RATE, rules=(),
    )
    assert r1.no_activity.sale_price_usd == r2.no_activity.sale_price_usd == na_price
    assert r2.activity.sale_price_usd < r1.activity.sale_price_usd
    assert r2.activity.profit_rmb < r1.activity.profit_rmb


# ---------------------------------------------------------------------------
# 场景 6: 修改计算总成本
# ---------------------------------------------------------------------------

def test_cost_change():
    """计算总成本变化时，两场景利润同步变化。"""
    r1 = calculate_dual_profit(
        no_activity_price_usd=30.0, reserve_percent=10.0,
        total_cost_rmb=200.0, exchange_rate=RATE, rules=(),
    )
    r2 = calculate_dual_profit(
        no_activity_price_usd=30.0, reserve_percent=10.0,
        total_cost_rmb=250.0, exchange_rate=RATE, rules=(),
    )
    assert r2.no_activity.profit_rmb < r1.no_activity.profit_rmb
    assert r2.activity.profit_rmb < r1.activity.profit_rmb


# ---------------------------------------------------------------------------
# 场景 7: 上方成本变化覆盖利润区手动成本
# ---------------------------------------------------------------------------

def test_cost_overwrite():
    """上方成本变化时，利润区计算总成本被覆盖。"""
    # 模拟 set_calculation_cost 覆盖
    cost1 = 200.0
    cost2 = 220.0
    r1 = calculate_dual_profit(
        no_activity_price_usd=30.0, reserve_percent=10.0,
        total_cost_rmb=cost1, exchange_rate=RATE, rules=(),
    )
    r2 = calculate_dual_profit(
        no_activity_price_usd=30.0, reserve_percent=10.0,
        total_cost_rmb=cost2, exchange_rate=RATE, rules=(),
    )
    assert r2.calculation_total_cost_rmb == cost2
    assert r2.no_activity.total_cost_rmb == cost2


# ---------------------------------------------------------------------------
# 场景 8: 汇率变化更新冻结币种
# ---------------------------------------------------------------------------

def test_exchange_rate_change():
    """汇率变化时，RMB 售价和利润同步变化，USD 售价保持不变。"""
    r1 = calculate_dual_profit(
        no_activity_price_usd=30.0, reserve_percent=10.0,
        total_cost_rmb=COST, exchange_rate=7.2, rules=(),
    )
    r2 = calculate_dual_profit(
        no_activity_price_usd=30.0, reserve_percent=10.0,
        total_cost_rmb=COST, exchange_rate=7.5, rules=(),
    )
    assert r1.no_activity.sale_price_usd == r2.no_activity.sale_price_usd == 30.0
    assert r2.no_activity.sale_price_rmb > r1.no_activity.sale_price_rmb


# ---------------------------------------------------------------------------
# 场景 9: 两场景跨 29 USD 门槛时状态独立变化
# ---------------------------------------------------------------------------

def test_threshold_independent():
    """无活动售价 30 USD（不触发），活动后售价 27 USD（触发补贴）。"""
    r = calculate_dual_profit(
        no_activity_price_usd=30.0, reserve_percent=10.0,
        total_cost_rmb=COST, exchange_rate=RATE, rules=RULES,
    )
    # 无活动场景：30 USD >= 29，不触发
    na_matched = [e for e in r.no_activity.rule_evaluations if e.matched]
    assert len(na_matched) == 0
    # 活动场景：27 USD < 29，触发
    act_matched = [e for e in r.activity.rule_evaluations if e.matched]
    assert len(act_matched) == 1
    assert act_matched[0].rule_id == "subsidy_29"


# ---------------------------------------------------------------------------
# 场景 10: 条件规则跳变下反推最低有效售价
# ---------------------------------------------------------------------------

def test_jump_aware_reverse_solve():
    """条件规则跳变下，反推返回最低非负有效售价。"""
    # 目标利润需要触发补贴（售价 < 29）
    target = 20.0
    price = sale_price_for_scenario_target_profit(
        total_cost_rmb=COST, target_profit_rmb=target,
        exchange_rate=RATE, rules=RULES, scenario="no_activity",
    )
    # 验证反推的售价确实达到目标利润
    result = calculate_profit_scenario(
        sale_price_usd=price, total_cost_rmb=COST,
        exchange_rate=RATE, rules=RULES, scenario="no_activity",
    )
    assert result.profit_rmb >= target - 0.01
    assert price >= 0


# ---------------------------------------------------------------------------
# 场景 11: 防递归
# ---------------------------------------------------------------------------

def test_anti_recursion():
    """CalculationBinder 防递归标志在刷新后正确复位。"""
    import os
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    from PySide6.QtWidgets import QApplication, QWidget
    app = QApplication.instance() or QApplication([])
    from profit_accounting_26.ui.ui_loader import load_main_window
    from profit_accounting_26.ui.binders.calculation_binder import CalculationBinder

    ui = load_main_window()
    page = ui.findChild(QWidget, "pageCalculation")

    class MockContext:
        class _ss:
            def load(self): return {"exchange_rate_usd_to_rmb": 7.2}
        settings_service = _ss()

    binder = CalculationBinder(page, MockContext())
    binder.set_calculation_cost(200.0)
    binder.txt_na_price_usd.setValue(30.0)
    assert binder._profit_updating is False  # 刷新后应复位
    # 多次触发不应产生异常
    for _ in range(5):
        binder.txt_na_price_usd.setValue(30.0 + _)
    assert binder._profit_updating is False


# ---------------------------------------------------------------------------
# 场景 12: 总成本为 0 时安全显示
# ---------------------------------------------------------------------------

def test_zero_cost_safe():
    """总成本为 0 时，利润率显示 None，不出现无穷或异常。"""
    r = calculate_dual_profit(
        no_activity_price_usd=30.0, reserve_percent=10.0,
        total_cost_rmb=0.0, exchange_rate=RATE, rules=(),
    )
    assert r.profit_rate is None
    assert r.no_activity.profit_rate_on_cost is None
    assert r.activity.profit_rate_on_cost is None
    # 利润值仍然有效
    assert r.no_activity.profit_rmb == 30.0 * RATE  # 无成本，利润=售价


# ---------------------------------------------------------------------------
# 向后兼容测试
# ---------------------------------------------------------------------------

def test_old_calculate_profit_still_works():
    """旧 calculate_profit 接口仍可正常调用。"""
    from profit_accounting_26.engines.profit import calculate_profit
    result = calculate_profit(
        total_cost_rmb=200.0, sale_price_usd=30.0,
        exchange_rate=7.2, reserve_rate=0.1, rules=(),
    )
    assert result.profit_rmb == 30.0 * 7.2 * 0.9 - 200.0


def test_old_sale_price_for_target_profit_still_works():
    """旧 sale_price_for_target_profit 接口仍可正常调用。"""
    from profit_accounting_26.engines.profit import sale_price_for_target_profit
    price = sale_price_for_target_profit(
        total_cost_rmb=200.0, target_profit_rmb=50.0,
        exchange_rate=7.2, reserve_rate=0.0, rules=(),
    )
    assert price > 0
