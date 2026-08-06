"""记录兼容测试：利润双场景编解码器（profit_scenario_codec）。

覆盖契约 §14：
- 旧记录打开：旧售价映射为无活动售价，活动场景安全为空，不伪造双场景历史；
- 新记录保存后重开：profit_scenarios 全字段一致；
- 缺失字段安全为空；
- 不破坏旧字段（附加字段策略）。
"""

from __future__ import annotations

import pytest

from profit_accounting_26.application.profit_scenario_codec import (
    SCHEMA_VERSION,
    build_profit_scenarios,
    extract_profit_scenarios,
    is_legacy_record,
)


def _build_scenarios() -> dict:
    """构造一条典型的双场景快照（30 USD / 预留 10% / 活动后 27 USD）。"""
    return build_profit_scenarios(
        driver="no_activity_price",
        calculation_total_cost_rmb=200.0,
        shein_quote_usd=22.0,
        reserve_percent=10.0,
        no_activity_price_usd=30.0,
        no_activity_price_rmb=216.0,
        no_activity_profit_rmb=66.0,
        no_activity_profit_usd=66.0 / 7.2,
        no_activity_rule_status={"matched_count": 0, "total_income_rmb": 0.0, "total_cost_rmb": 0.0, "rules": []},
        activity_price_usd=27.0,
        activity_price_rmb=194.4,
        activity_profit_rmb=65.93,
        activity_profit_usd=65.93 / 7.2,
        activity_profit_rate_on_cost=0.32965,
        activity_rule_status={
            "matched_count": 1,
            "total_income_rmb": 21.53,
            "total_cost_rmb": 0.0,
            "rules": [
                {
                    "id": "under_29_subsidy",
                    "name": "SHEIN 29美元以下运费补贴",
                    "direction": "income",
                    "amount_rmb": 21.53,
                    "amount_original": 2.99,
                    "currency": "USD",
                }
            ],
        },
    )


def test_old_record_open_maps_to_no_activity_scenario():
    """旧记录打开：旧售价映射为无活动售价，活动场景不伪造。"""
    record = {
        "layers": {
            "calculated": {
                "sale_price_usd": 25.0,
                "exchange_rate": 7.2,
                "profit_rmb": 30.0,
                "calculation_cost_rmb": 150.0,
                "reserve_percent": 0,
                "profit_rate_percent": 20.0,
            }
        },
        "shein_quote_usd": 22.0,
    }
    scenarios = extract_profit_scenarios(record)
    assert scenarios is not None
    assert scenarios["no_activity"]["sale_price_usd"] == pytest.approx(25.0)
    assert scenarios["no_activity"]["sale_price_rmb"] == pytest.approx(180.0)
    assert scenarios["no_activity"]["profit_rmb"] == pytest.approx(30.0)
    # 活动场景安全为空，不伪造双场景历史
    assert scenarios["activity"]["sale_price_usd"] == 0.0
    assert scenarios["activity"]["profit_rmb"] == 0.0
    assert scenarios["driver"] == "no_activity_price"
    assert scenarios["shein_quote_usd"] == pytest.approx(22.0)
    assert is_legacy_record(scenarios) is True


def test_new_record_save_and_reopen_roundtrip():
    """新记录保存后重新打开：profit_scenarios 全字段一致。"""
    built = _build_scenarios()
    record = {"profit_scenarios": built}
    extracted = extract_profit_scenarios(record)
    assert extracted["schema_version"] == SCHEMA_VERSION
    assert extracted["driver"] == built["driver"]
    assert extracted["calculation_total_cost_rmb"] == pytest.approx(built["calculation_total_cost_rmb"])
    assert extracted["reserve_percent"] == pytest.approx(built["reserve_percent"])
    assert extracted["no_activity"] == built["no_activity"]
    assert extracted["activity"] == built["activity"]
    assert is_legacy_record(extracted) is False


def test_record_without_profit_data_returns_none():
    """无利润数据的记录返回 None（缺失字段安全为空）。"""
    assert extract_profit_scenarios({}) is None
    assert extract_profit_scenarios({"layers": {}}) is None
    assert extract_profit_scenarios({"layers": {"calculated": {}}}) is None
    assert is_legacy_record(None) is True


def test_legacy_record_with_missing_optional_fields_is_safe():
    """旧记录缺失汇率/预留等可选字段时安全取默认值，不崩溃。"""
    record = {"layers": {"calculated": {"sale_price_usd": 19.9}}}
    scenarios = extract_profit_scenarios(record)
    assert scenarios is not None
    assert scenarios["no_activity"]["sale_price_usd"] == pytest.approx(19.9)
    # 默认汇率 7.2 换算
    assert scenarios["no_activity"]["sale_price_rmb"] == pytest.approx(19.9 * 7.2)
    assert scenarios["reserve_percent"] == 0.0


def test_scenarios_field_is_additive_and_keeps_legacy_fields():
    """附加字段策略：profit_scenarios 与 layers.calculated 旧字段并存互不覆盖。"""
    built = _build_scenarios()
    record = {
        "layers": {"calculated": {"sale_price_usd": 30.0, "profit_rmb": 66.0}},
        "profit_scenarios": built,
    }
    extracted = extract_profit_scenarios(record)
    # 新记录优先读取 profit_scenarios，而不是旧 calculated 映射
    assert extracted["schema_version"] == SCHEMA_VERSION
    assert "_legacy_compatible" not in extracted
    assert extracted["no_activity"]["sale_price_usd"] == pytest.approx(30.0)
    assert extracted["activity"]["sale_price_usd"] == pytest.approx(27.0)
    # 旧字段保持原样
    assert record["layers"]["calculated"]["sale_price_usd"] == 30.0


def test_saved_snapshot_survives_later_rate_or_rule_changes():
    """保存后当前汇率或规则变化，重开仍保持保存时的快照。"""
    built = _build_scenarios()
    record = {
        "layers": {"calculated": {"sale_price_usd": 30.0}},
        "profit_scenarios": built,
    }
    # 模拟：保存后汇率从 7.2 变为 6.9、规则被修改/禁用
    # 记录本身不含任何“当前”汇率/规则状态，重开提取的仍是保存快照
    extracted = extract_profit_scenarios(record)
    assert extracted["calculation_total_cost_rmb"] == pytest.approx(200.0)
    assert extracted["no_activity"]["sale_price_rmb"] == pytest.approx(216.0)  # 7.2 快照
    assert extracted["no_activity"]["sale_price_rmb"] != pytest.approx(30.0 * 6.9)
    assert extracted["activity"]["rule_status"]["rules"][0]["name"] == "SHEIN 29美元以下运费补贴"
