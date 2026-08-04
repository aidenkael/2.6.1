"""利润双场景记录编解码器。

负责在记录 payload 中附加 ``profit_scenarios`` 字段（schema_version
``2.6.1-dual-profit-v1``），并保证旧记录（只有单一售价/利润）可向后兼容读取。

设计原则：
- 采用附加字段，不破坏旧字段（``layers.calculated.*`` 保持原样）；
- 旧记录打开时，可读取的旧售价映射为无活动售价；
- 旧利润只作为兼容显示，不伪造双场景历史；
- 缺失的新字段安全为空；
- 不改 AI 原始数据、包装候选、物流快照和实际反馈字段。
"""

from __future__ import annotations

from typing import Any

from profit_accounting_26.domain.rules import (
    AdjustmentDirection,
    AdjustmentRule,
    AdjustmentType,
    CompareOp,
)

SCHEMA_VERSION = "2.6.1-dual-profit-v1"


def rules_to_snapshot(rules) -> list[dict[str, Any]]:
    """完整应用规则快照序列化（含未命中规则，重开时据此还原）。"""
    snapshot = []
    for rule in rules:
        snapshot.append(
            {
                "id": rule.id,
                "name": rule.name,
                "condition_field": rule.condition_field,
                "compare_op": str(rule.compare_op),
                "condition_value": rule.condition_value,
                "direction": str(rule.direction),
                "adjustment_type": str(rule.adjustment_type),
                "adjustment_value": rule.adjustment_value,
                "currency": rule.currency,
                "percent_base": rule.percent_base,
                "enabled": rule.enabled,
                "archived": rule.archived,
                "description": rule.description,
            }
        )
    return snapshot


def rules_from_snapshot(snapshot) -> tuple[AdjustmentRule, ...]:
    """从完整规则快照还原规则对象；无效条目安全跳过。"""
    rules: list[AdjustmentRule] = []
    if not isinstance(snapshot, list):
        return ()
    for raw in snapshot:
        if not isinstance(raw, dict):
            continue
        try:
            rule = AdjustmentRule(
                id=str(raw.get("id") or ""),
                name=str(raw.get("name") or ""),
                condition_field=str(raw.get("condition_field") or ""),
                compare_op=CompareOp(str(raw.get("compare_op") or "lt")),
                condition_value=float(raw.get("condition_value") or 0.0),
                direction=AdjustmentDirection(str(raw.get("direction") or "income")),
                adjustment_type=AdjustmentType(str(raw.get("adjustment_type") or "fixed")),
                adjustment_value=float(raw.get("adjustment_value") or 0.0),
                currency=str(raw.get("currency") or "RMB"),
                percent_base=raw.get("percent_base"),
                enabled=bool(raw.get("enabled", True)),
                archived=bool(raw.get("archived", False)),
                description=str(raw.get("description") or ""),
            )
            rule.validate()
        except (ValueError, TypeError, KeyError):
            continue
        rules.append(rule)
    return tuple(rules)


def build_profit_scenarios(
    *,
    driver: str,
    calculation_total_cost_rmb: float,
    shein_quote_usd: float,
    reserve_percent: float,
    no_activity_price_usd: float,
    no_activity_price_rmb: float,
    no_activity_profit_rmb: float,
    no_activity_profit_usd: float,
    no_activity_rule_status: dict[str, Any] | None,
    activity_price_usd: float,
    activity_price_rmb: float,
    activity_profit_rmb: float,
    activity_profit_usd: float,
    activity_profit_rate_on_cost: float | None,
    activity_rule_status: dict[str, Any] | None,
    exchange_rate: float = 0.0,
    applied_rule_ids: list[str] | None = None,
    applied_rules: list[dict[str, Any]] | None = None,
    selected_rule_id: str = "",
    legacy_compatible: bool = False,
) -> dict[str, Any]:
    """构建 ``profit_scenarios`` 字段。

    ``driver`` 取值：``profit_rate`` / ``no_activity_price`` /
    ``no_activity_profit`` / ``activity_profit``。

    记录快照附加字段（验收修正轮新增）：
    - ``exchange_rate``：保存时汇率，重开时用它而非当前设置；
    - ``applied_rule_ids``：实际应用的规则 ID 集合；
    - ``applied_rules``：完整应用规则快照（含未命中规则，重开时据此还原）；
    - ``selected_rule_id``：保存时规则下拉选择（可为 ``__all_enabled__``）；
    - ``legacy_compatible``：是否为旧记录兼容映射（新记录恒为 False）。
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "driver": driver,
        "calculation_total_cost_rmb": calculation_total_cost_rmb,
        "shein_quote_usd": shein_quote_usd,
        "reserve_percent": reserve_percent,
        "exchange_rate": exchange_rate,
        "applied_rule_ids": list(applied_rule_ids or []),
        "applied_rules": list(applied_rules or []),
        "selected_rule_id": selected_rule_id,
        "legacy_compatible": legacy_compatible,
        "no_activity": {
            "sale_price_usd": no_activity_price_usd,
            "sale_price_rmb": no_activity_price_rmb,
            "profit_rmb": no_activity_profit_rmb,
            "profit_usd": no_activity_profit_usd,
            "rule_status": no_activity_rule_status or {},
        },
        "activity": {
            "sale_price_usd": activity_price_usd,
            "sale_price_rmb": activity_price_rmb,
            "profit_rmb": activity_profit_rmb,
            "profit_usd": activity_profit_usd,
            "profit_rate_on_cost": activity_profit_rate_on_cost,
            "rule_status": activity_rule_status or {},
        },
    }


def extract_profit_scenarios(record: dict[str, Any]) -> dict[str, Any] | None:
    """从记录中提取双场景利润数据。

    - 新记录：直接返回 ``profit_scenarios`` 字段；
    - 旧记录：将旧售价映射为无活动售价，缺失字段安全为空，不伪造双场景历史；
    - 无利润数据的记录：返回 None。
    """
    scenarios = record.get("profit_scenarios")
    if isinstance(scenarios, dict):
        # 确保新记录的 schema_version 标记存在
        result = dict(scenarios)
        result.setdefault("schema_version", SCHEMA_VERSION)
        # 验收修正轮新增字段：旧版本保存的记录缺失时安全回填
        layers = record.get("layers", {})
        calculated = layers.get("calculated", {}) if isinstance(layers, dict) else {}
        if not result.get("exchange_rate"):
            result["exchange_rate"] = float(calculated.get("exchange_rate", 7.2) or 7.2)
        result.setdefault("applied_rule_ids", [])
        result.setdefault("applied_rules", [])
        result.setdefault("selected_rule_id", "")
        result.setdefault("legacy_compatible", bool(result.get("_legacy_compatible", False)))
        return result

    # 旧记录兼容：从 layers.calculated 读取单一售价/利润
    layers = record.get("layers", {})
    calculated = layers.get("calculated", {}) if isinstance(layers, dict) else {}
    old_sale_price = calculated.get("sale_price_usd")
    if old_sale_price is None:
        # 也检查顶层旧字段
        old_sale_price = record.get("sale_price_usd")
    if old_sale_price is None:
        return None

    exchange_rate = float(calculated.get("exchange_rate", 7.2) or 7.2)
    old_reserve = float(calculated.get("reserve_percent", 0) or 0)
    old_profit = float(calculated.get("profit_rmb", 0) or 0)
    old_rate = calculated.get("profit_rate_percent")
    old_shein = float(record.get("shein_quote_usd", 0) or 0)

    old_sale_price = float(old_sale_price)
    no_activity_price_rmb = old_sale_price * exchange_rate
    no_activity_profit_usd = old_profit / exchange_rate if exchange_rate > 0 else 0.0

    # 活动场景：旧记录只有单场景，不伪造活动后数据，安全为空
    return {
        "schema_version": SCHEMA_VERSION,
        "driver": "no_activity_price",  # 旧记录默认以无活动售价为基准
        "calculation_total_cost_rmb": float(calculated.get("calculation_cost_rmb", 0) or 0),
        "shein_quote_usd": old_shein,
        "reserve_percent": old_reserve,
        "exchange_rate": exchange_rate,
        "applied_rule_ids": [],
        "applied_rules": [],
        "selected_rule_id": str(calculated.get("selected_profit_rule_id") or ""),
        "legacy_compatible": True,
        "no_activity": {
            "sale_price_usd": old_sale_price,
            "sale_price_rmb": no_activity_price_rmb,
            "profit_rmb": old_profit,
            "profit_usd": no_activity_profit_usd,
            "rule_status": {},
        },
        "activity": {
            "sale_price_usd": 0.0,
            "sale_price_rmb": 0.0,
            "profit_rmb": 0.0,
            "profit_usd": 0.0,
            "profit_rate_on_cost": float(old_rate) if old_rate is not None else None,
            "rule_status": {},
        },
        "_legacy_compatible": True,  # 标记：旧记录兼容映射，非真实双场景
    }


def is_legacy_record(scenarios: dict[str, Any] | None) -> bool:
    """判断是否为旧记录兼容映射（非真实双场景历史）。"""
    if scenarios is None:
        return True
    return bool(scenarios.get("legacy_compatible") or scenarios.get("_legacy_compatible"))
