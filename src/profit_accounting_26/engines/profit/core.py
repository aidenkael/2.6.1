from __future__ import annotations

import math
from collections.abc import Iterable

from profit_accounting_26.domain.models import (
    DualProfitResult,
    ProfitResult,
    RuleEvaluation,
    ScenarioProfitResult,
)
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


# ---------------------------------------------------------------------------
# 双场景利润引擎（2.6.1-dual-profit-v1）
#
# 设计要点：
# 1. 每个场景按其真实售价独立执行规则（reserve_rate 恒为 0）；
# 2. 无活动场景用无活动售价判断规则，活动场景用活动后售价判断规则；
# 3. 活动后售价 = 无活动售价 ×（1 - 活动预留%）；
# 4. 利润率统一为 活动后利润 RMB / 计算总成本 RMB；
# 5. 保留旧 calculate_profit / sale_price_for_target_profit / sale_price_for_target_rate
#    的兼容性，不破坏已有测试和其他模块。
# ---------------------------------------------------------------------------


def _evaluate_rules_with_detail(
    rules: Iterable[AdjustmentRule],
    rule_context: dict[str, float],
    *,
    exchange_rate: float,
    scenario: str,
) -> tuple[float, float, tuple[RuleEvaluation, ...]]:
    """返回 (income_adjustment_rmb, cost_adjustment_rmb, rule_evaluations)。"""
    income_total = 0.0
    cost_total = 0.0
    evaluations: list[RuleEvaluation] = []
    for rule in rules:
        if not rule.enabled or rule.archived:
            evaluations.append(
                RuleEvaluation(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    scenario=scenario,
                    condition_field=rule.condition_field,
                    condition_value=rule.condition_value,
                    compare_op=str(rule.compare_op),
                    matched=False,
                    direction=str(rule.direction),
                    amount_rmb=0.0,
                    amount_original=0.0,
                    currency=rule.currency,
                )
            )
            continue
        income, cost = evaluate_rule(rule, rule_context, exchange_rate=exchange_rate)
        income_total += income
        cost_total += cost
        amount_rmb = income if income > 0 else cost
        evaluations.append(
            RuleEvaluation(
                rule_id=rule.id,
                rule_name=rule.name,
                scenario=scenario,
                condition_field=rule.condition_field,
                condition_value=rule.condition_value,
                compare_op=str(rule.compare_op),
                matched=(income > 0 or cost > 0),
                direction=str(rule.direction),
                amount_rmb=amount_rmb,
                amount_original=rule.adjustment_value,
                currency=rule.currency,
            )
        )
    return income_total, cost_total, tuple(evaluations)


def calculate_profit_scenario(
    *,
    sale_price_usd: float,
    total_cost_rmb: float,
    exchange_rate: float,
    rules: Iterable[AdjustmentRule] = (),
    scenario: str = "no_activity",
) -> ScenarioProfitResult:
    """单场景利润计算（reserve_rate 恒为 0）。

    每个场景按其真实售价独立判断规则。reserve 已在传入的售价中折算。
    """
    _validate_non_negative("总成本", total_cost_rmb)
    _validate_non_negative("售价", sale_price_usd)
    if exchange_rate <= 0:
        raise ValueError("汇率必须大于 0")

    sale_price_rmb = sale_price_usd * exchange_rate
    rule_context = {
        "sale_price_usd": sale_price_usd,
        "sale_price_rmb": sale_price_rmb,
        "revenue_after_reserve_rmb": sale_price_rmb,  # reserve=0
        "total_cost_rmb": total_cost_rmb,
    }
    income, cost, evaluations = _evaluate_rules_with_detail(
        rules, rule_context, exchange_rate=exchange_rate, scenario=scenario
    )
    profit = sale_price_rmb + income - total_cost_rmb - cost
    rate = None if total_cost_rmb == 0 else profit / total_cost_rmb
    profit_usd = profit / exchange_rate if exchange_rate > 0 else 0.0
    return ScenarioProfitResult(
        sale_price_usd=sale_price_usd,
        sale_price_rmb=sale_price_rmb,
        total_cost_rmb=total_cost_rmb,
        income_adjustment_rmb=income,
        cost_adjustment_rmb=cost,
        profit_rmb=profit,
        profit_usd=profit_usd,
        profit_rate_on_cost=rate,
        rule_evaluations=evaluations,
    )


def calculate_dual_profit(
    *,
    no_activity_price_usd: float,
    reserve_percent: float,
    total_cost_rmb: float,
    exchange_rate: float,
    rules: Iterable[AdjustmentRule] = (),
) -> DualProfitResult:
    """双场景利润计算。

    - 无活动场景：用 no_activity_price_usd 判断规则；
    - 活动场景：用 no_activity_price_usd ×（1 - reserve_percent/100）判断规则；
    - 利润率 = 活动后利润 RMB / 计算总成本 RMB。
    """
    _validate_non_negative("无活动售价", no_activity_price_usd)
    _validate_non_negative("总成本", total_cost_rmb)
    if exchange_rate <= 0:
        raise ValueError("汇率必须大于 0")
    if not 0 <= reserve_percent < 100:
        raise ValueError("活动预留百分比必须在 0（含）到 100（不含）之间")

    rules_tuple = tuple(rules)
    reserve_rate = reserve_percent / 100.0

    no_activity = calculate_profit_scenario(
        sale_price_usd=no_activity_price_usd,
        total_cost_rmb=total_cost_rmb,
        exchange_rate=exchange_rate,
        rules=rules_tuple,
        scenario="no_activity",
    )
    activity_price_usd = no_activity_price_usd * (1 - reserve_rate)
    activity = calculate_profit_scenario(
        sale_price_usd=activity_price_usd,
        total_cost_rmb=total_cost_rmb,
        exchange_rate=exchange_rate,
        rules=rules_tuple,
        scenario="activity",
    )
    profit_rate = None if total_cost_rmb == 0 else activity.profit_rmb / total_cost_rmb
    return DualProfitResult(
        calculation_total_cost_rmb=total_cost_rmb,
        exchange_rate=exchange_rate,
        reserve_percent=reserve_percent,
        no_activity=no_activity,
        activity=activity,
        profit_rate=profit_rate,
    )


def sale_price_for_scenario_target_profit(
    *,
    total_cost_rmb: float,
    target_profit_rmb: float,
    exchange_rate: float,
    rules: Iterable[AdjustmentRule] = (),
    scenario: str = "no_activity",
) -> float:
    """单场景反推：返回能达到目标利润的最低非负有效售价。

    复用现有 sale_price_for_target_profit 的条件跳变分段二分搜索，
    传入 reserve_rate=0（因为双场景下 reserve 已在售价中折算）。
    """
    return sale_price_for_target_profit(
        total_cost_rmb=total_cost_rmb,
        target_profit_rmb=target_profit_rmb,
        exchange_rate=exchange_rate,
        reserve_rate=0.0,
        rules=rules,
    )


def sale_price_for_dual_activity_target(
    *,
    total_cost_rmb: float,
    target_activity_profit_rmb: float,
    reserve_percent: float,
    exchange_rate: float,
    rules: Iterable[AdjustmentRule] = (),
) -> float:
    """双场景反推：给定目标活动后利润，反推无活动售价 USD。

    活动后售价 = 无活动售价 ×（1 - reserve）。
    先反推活动后售价（reserve=0 的单场景），再除以（1 - reserve）。
    """
    _validate_non_negative("总成本", total_cost_rmb)
    if exchange_rate <= 0:
        raise ValueError("汇率必须大于 0")
    if not 0 <= reserve_percent < 100:
        raise ValueError("活动预留百分比必须在 0（含）到 100（不含）之间")

    reserve_rate = reserve_percent / 100.0
    activity_price = sale_price_for_scenario_target_profit(
        total_cost_rmb=total_cost_rmb,
        target_profit_rmb=target_activity_profit_rmb,
        exchange_rate=exchange_rate,
        rules=rules,
        scenario="activity",
    )
    if reserve_rate >= 1:
        raise ValueError("活动预留比例过大，无法反推无活动售价")
    return activity_price / (1 - reserve_rate)
