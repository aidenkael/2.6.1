import pytest

from profit_accounting_26.engines.profit import (
    calculate_profit,
    sale_price_for_target_profit,
    sale_price_for_target_rate,
)


def test_profit_forward_calculation():
    result = calculate_profit(
        total_cost_rmb=100,
        sale_price_usd=20,
        exchange_rate=7,
        reserve_rate=0.1,
    )
    assert result.sale_price_rmb == pytest.approx(140)
    assert result.revenue_after_reserve_rmb == pytest.approx(126)
    assert result.profit_rmb == pytest.approx(26)
    assert result.profit_rate_on_cost == pytest.approx(0.26)


def test_target_profit_reverse():
    price = sale_price_for_target_profit(
        total_cost_rmb=100,
        target_profit_rmb=30,
        exchange_rate=7,
        reserve_rate=0.1,
    )
    assert price == pytest.approx(130 / 0.9 / 7)


def test_target_rate_reverse():
    price = sale_price_for_target_rate(
        total_cost_rmb=100,
        target_rate_on_cost=0.3,
        exchange_rate=7,
    )
    assert price == pytest.approx(130 / 7)


def test_profit_rejects_invalid_exchange_rate():
    with pytest.raises(ValueError):
        calculate_profit(total_cost_rmb=1, sale_price_usd=1, exchange_rate=0)
