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

SCHEMA_VERSION = "2.6.1-dual-profit-v1"


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
) -> dict[str, Any]:
    """构建 ``profit_scenarios`` 字段。

    ``driver`` 取值：``profit_rate`` / ``no_activity_price`` /
    ``no_activity_profit`` / ``activity_profit``。
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "driver": driver,
        "calculation_total_cost_rmb": calculation_total_cost_rmb,
        "shein_quote_usd": shein_quote_usd,
        "reserve_percent": reserve_percent,
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
    return bool(scenarios.get("_legacy_compatible"))
