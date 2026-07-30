import pytest

from profit_accounting_26.domain.rules import (
    AdjustmentDirection,
    AdjustmentRule,
    AdjustmentType,
    CompareOp,
)
from profit_accounting_26.engines.profit import calculate_profit


def subsidy_rule(enabled=True, archived=False):
    return AdjustmentRule(
        id="under_29_subsidy",
        name="29美元以下运费补贴",
        condition_field="sale_price_usd",
        compare_op=CompareOp.LT,
        condition_value=29,
        direction=AdjustmentDirection.INCOME,
        adjustment_type=AdjustmentType.FIXED,
        adjustment_value=2.99,
        currency="USD",
        enabled=enabled,
        archived=archived,
    )


def test_fixed_usd_income_rule_applies():
    result = calculate_profit(
        total_cost_rmb=100,
        sale_price_usd=20,
        exchange_rate=7,
        rules=[subsidy_rule()],
    )
    assert result.income_adjustment_rmb == pytest.approx(20.93)
    assert result.profit_rmb == pytest.approx(60.93)


def test_disabled_or_archived_rule_does_not_apply():
    for rule in (subsidy_rule(enabled=False), subsidy_rule(archived=True)):
        result = calculate_profit(
            total_cost_rmb=100,
            sale_price_usd=20,
            exchange_rate=7,
            rules=[rule],
        )
        assert result.income_adjustment_rmb == 0


def test_rule_does_not_apply_at_threshold():
    result = calculate_profit(
        total_cost_rmb=100,
        sale_price_usd=29,
        exchange_rate=7,
        rules=[subsidy_rule()],
    )
    assert result.income_adjustment_rmb == 0


def test_reverse_target_profit_applies_conditional_subsidy():
    from profit_accounting_26.engines.profit import sale_price_for_target_profit

    price = sale_price_for_target_profit(
        total_cost_rmb=100,
        target_profit_rmb=30,
        exchange_rate=7,
        rules=[subsidy_rule()],
    )
    assert price == pytest.approx((100 + 30 - 2.99 * 7) / 7)
    result = calculate_profit(
        total_cost_rmb=100,
        sale_price_usd=price,
        exchange_rate=7,
        rules=[subsidy_rule()],
    )
    assert result.profit_rmb == pytest.approx(30)


def test_reverse_target_profit_crosses_subsidy_threshold_when_needed():
    from profit_accounting_26.engines.profit import sale_price_for_target_profit

    price = sale_price_for_target_profit(
        total_cost_rmb=100,
        target_profit_rmb=125,
        exchange_rate=7,
        rules=[subsidy_rule()],
    )
    assert price >= 29
    result = calculate_profit(
        total_cost_rmb=100,
        sale_price_usd=price,
        exchange_rate=7,
        rules=[subsidy_rule()],
    )
    assert result.profit_rmb == pytest.approx(125)
