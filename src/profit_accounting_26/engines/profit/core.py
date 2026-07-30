from __future__ import annotations

import math
from collections.abc import Iterable

from profit_accounting_26.domain.models import ProfitResult
from profit_accounting_26.domain.rules import AdjustmentRule, evaluate_rule


def _validate_non_negative(name: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{name}不能为负数")


def calculate_profit(
    *,
    total_cost_rmb: float,
    sale_price_usd: float,
    exchange_rate: float,
    reserve_rate: float = 0.0,
    rules: Iterable[AdjustmentRule] = (),
    context: dict[str, float] | None = None,
) -> ProfitResult:
    _validate_non_negative("总成本", total_cost_rmb)
    _validate_non_negative("售价", sale_price_usd)
    if exchange_rate <= 0:
        raise ValueError("汇率必须大于 0")
    if not 0 <= reserve_rate < 1:
        raise ValueError("活动预留比例必须在 0（含）到 1（不含）之间")

    sale_price_rmb = sale_price_usd * exchange_rate
    revenue_after_reserve = sale_price_rmb * (1 - reserve_rate)
    rule_context = {
        "sale_price_usd": sale_price_usd,
        "sale_price_rmb": sale_price_rmb,
        "revenue_after_reserve_rmb": revenue_after_reserve,
        "total_cost_rmb": total_cost_rmb,
        **(context or {}),
    }
    income_adjustment = 0.0
    cost_adjustment = 0.0
    for rule in rules:
        income, cost = evaluate_rule(rule, rule_context, exchange_rate=exchange_rate)
        income_adjustment += income
        cost_adjustment += cost

    profit = revenue_after_reserve + income_adjustment - total_cost_rmb - cost_adjustment
    rate = None if total_cost_rmb == 0 else profit / total_cost_rmb
    return ProfitResult(
        sale_price_usd=sale_price_usd,
        sale_price_rmb=sale_price_rmb,
        revenue_after_reserve_rmb=revenue_after_reserve,
        total_cost_rmb=total_cost_rmb,
        income_adjustment_rmb=income_adjustment,
        cost_adjustment_rmb=cost_adjustment,
        profit_rmb=profit,
        profit_rate_on_cost=rate,
    )


def sale_price_for_target_profit(
    *,
    total_cost_rmb: float,
    target_profit_rmb: float,
    exchange_rate: float,
    reserve_rate: float = 0.0,
    net_adjustment_rmb: float = 0.0,
    rules: Iterable[AdjustmentRule] = (),
) -> float:
    _validate_non_negative("总成本", total_cost_rmb)
    if exchange_rate <= 0:
        raise ValueError("汇率必须大于 0")
    if not 0 <= reserve_rate < 1:
        raise ValueError("活动预留比例必须在 0（含）到 1（不含）之间")
    rules = tuple(rules)
    if not rules:
        required_revenue = total_cost_rmb + target_profit_rmb - net_adjustment_rmb
        return required_revenue / (1 - reserve_rate) / exchange_rate

    # Conditional rules can create jumps (for example a subsidy below USD 29).
    # Between rule thresholds the result is linear, so search each interval and
    # return the lowest non-negative price that reaches the target.
    target = target_profit_rmb

    def profit_at(price: float) -> float:
        return calculate_profit(
            total_cost_rmb=total_cost_rmb,
            sale_price_usd=max(0.0, price),
            exchange_rate=exchange_rate,
            reserve_rate=reserve_rate,
            rules=rules,
        ).profit_rmb + net_adjustment_rmb

    breakpoints = {0.0}
    revenue_factor = exchange_rate * (1 - reserve_rate)
    for rule in rules:
        if not rule.enabled or rule.archived:
            continue
        if rule.condition_field == "sale_price_usd":
            breakpoints.add(max(0.0, rule.condition_value))
        elif rule.condition_field == "sale_price_rmb":
            breakpoints.add(max(0.0, rule.condition_value / exchange_rate))
        elif rule.condition_field == "revenue_after_reserve_rmb" and revenue_factor > 0:
            breakpoints.add(max(0.0, rule.condition_value / revenue_factor))

    base_guess = max(
        1.0,
        (total_cost_rmb + target_profit_rmb - net_adjustment_rmb)
        / (1 - reserve_rate)
        / exchange_rate,
    )
    high = max(base_guess * 2.0, max(breakpoints) + 10.0, 64.0)
    for _ in range(30):
        if profit_at(high) >= target:
            break
        high *= 2.0
    else:
        raise ValueError("无法在合理售价范围内达到目标利润")
    breakpoints.add(high)
    points = sorted(point for point in breakpoints if point <= high)
    candidates: list[float] = []

    def consider(price: float) -> None:
        price = max(0.0, price)
        if profit_at(price) + 1e-7 >= target:
            candidates.append(price)

    for point in points:
        consider(point)
        if point > 0:
            consider(math.nextafter(point, -math.inf))
        consider(math.nextafter(point, math.inf))

    for left, right in zip(points, points[1:], strict=False):
        lo = math.nextafter(left, math.inf)
        hi = math.nextafter(right, -math.inf)
        if lo > hi:
            continue
        left_profit = profit_at(lo)
        right_profit = profit_at(hi)
        if left_profit >= target:
            candidates.append(lo)
            continue
        if right_profit < target or right_profit <= left_profit:
            continue
        for _ in range(80):
            middle = (lo + hi) / 2.0
            if profit_at(middle) >= target:
                hi = middle
            else:
                lo = middle
        consider(hi)

    if not candidates:
        raise ValueError("当前利润规则下不存在可满足目标的售价")
    return min(candidates)


def sale_price_for_target_rate(
    *,
    total_cost_rmb: float,
    target_rate_on_cost: float,
    exchange_rate: float,
    reserve_rate: float = 0.0,
    net_adjustment_rmb: float = 0.0,
    rules: Iterable[AdjustmentRule] = (),
) -> float:
    target_profit = total_cost_rmb * target_rate_on_cost
    return sale_price_for_target_profit(
        total_cost_rmb=total_cost_rmb,
        target_profit_rmb=target_profit,
        exchange_rate=exchange_rate,
        reserve_rate=reserve_rate,
        net_adjustment_rmb=net_adjustment_rmb,
        rules=rules,
    )
