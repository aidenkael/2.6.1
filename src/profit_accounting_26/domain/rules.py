from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping


class CompareOp(StrEnum):
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    EQ = "eq"


class AdjustmentDirection(StrEnum):
    INCOME = "income"
    COST = "cost"


class AdjustmentType(StrEnum):
    FIXED = "fixed"
    PERCENT = "percent"


@dataclass(frozen=True, slots=True)
class AdjustmentRule:
    id: str
    name: str
    condition_field: str
    compare_op: CompareOp
    condition_value: float
    direction: AdjustmentDirection
    adjustment_type: AdjustmentType
    adjustment_value: float
    currency: str = "RMB"
    percent_base: str | None = None
    enabled: bool = True
    archived: bool = False
    description: str = ""

    def validate(self) -> None:
        if not self.id.strip() or not self.name.strip():
            raise ValueError("规则 ID 和名称不能为空")
        if self.adjustment_value < 0:
            raise ValueError("调整值不能为负数")
        if self.currency not in {"RMB", "USD"}:
            raise ValueError("仅支持 RMB 或 USD")
        if self.adjustment_type is AdjustmentType.PERCENT and not self.percent_base:
            raise ValueError("百分比规则必须指定基数")


def compare(left: float, op: CompareOp, right: float) -> bool:
    return {
        CompareOp.LT: left < right,
        CompareOp.LTE: left <= right,
        CompareOp.GT: left > right,
        CompareOp.GTE: left >= right,
        CompareOp.EQ: left == right,
    }[op]


def evaluate_rule(
    rule: AdjustmentRule,
    context: Mapping[str, float],
    *,
    exchange_rate: float,
) -> tuple[float, float]:
    """Return ``(income_adjustment_rmb, cost_adjustment_rmb)``."""
    rule.validate()
    if not rule.enabled or rule.archived:
        return 0.0, 0.0
    if rule.condition_field not in context:
        return 0.0, 0.0
    if not compare(float(context[rule.condition_field]), rule.compare_op, rule.condition_value):
        return 0.0, 0.0

    if rule.adjustment_type is AdjustmentType.FIXED:
        amount = rule.adjustment_value
    else:
        if rule.percent_base not in context:
            return 0.0, 0.0
        amount = float(context[rule.percent_base]) * rule.adjustment_value

    if rule.currency == "USD":
        if exchange_rate <= 0:
            raise ValueError("汇率必须大于 0")
        amount *= exchange_rate

    if rule.direction is AdjustmentDirection.INCOME:
        return amount, 0.0
    return 0.0, amount
