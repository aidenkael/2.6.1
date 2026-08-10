from pathlib import Path
import json

from profit_accounting_26.application import SettingsService


def test_forwarder_stable_id_archive_and_restore():
    forwarder = SettingsService.new_forwarder("测试货代", 88, 7, 8000)
    archived = SettingsService.archive(forwarder)
    restored = SettingsService.restore(archived)
    assert archived.id == forwarder.id == restored.id
    assert archived.archived and not archived.enabled
    assert not restored.archived and not restored.enabled


def test_settings_can_be_copied_to_new_data_directory(tmp_path: Path):
    source = SettingsService(tmp_path / "old" / "settings.json")
    values = {"vision_api_endpoint": "https://example.test/v1", "vision_api_model": "vision-model"}
    source.save(values)

    SettingsService.save_copy(source.load(), tmp_path / "new" / "settings.json")

    migrated = SettingsService(tmp_path / "new" / "settings.json").load()
    assert migrated["vision_api_endpoint"] == "https://example.test/v1"
    assert migrated["vision_api_model"] == "vision-model"


# ---------------------------------------------------------------------------
# 失效 selected_profit_rule_id 修复测试
# ---------------------------------------------------------------------------


def test_stale_selected_rule_id_repaired_to_first_valid(tmp_path: Path):
    """selected_profit_rule_id 是不存在的非空旧 ID，load 后自动修正为第一个有效规则。"""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "profit_rules": [
            {
                "id": "under_29_subsidy",
                "name": "SHEIN 29美元以下运费补贴",
                "condition_field": "sale_price_usd",
                "compare_op": "lt",
                "condition_value": 29.0,
                "direction": "income",
                "adjustment_type": "fixed",
                "adjustment_value": 2.99,
                "currency": "USD",
                "enabled": True,
                "archived": False,
            }
        ],
        "selected_profit_rule_id": "rule_bc121c735f8d4c1f90f2abd959624982",  # 不存在的旧 ID
        "seed_versions": ["profit_rules_v1"],
    }), encoding="utf-8")

    service = SettingsService(settings_path)
    loaded = service.load()

    # 修正为第一个有效规则
    assert loaded["selected_profit_rule_id"] == "under_29_subsidy"
    # 确认已写回 settings.json
    persisted = json.loads(settings_path.read_text(encoding="utf-8"))
    assert persisted["selected_profit_rule_id"] == "under_29_subsidy"


def test_empty_selected_rule_id_preserved(tmp_path: Path):
    """selected_profit_rule_id 为空字符串时，即使存在有效规则也保持不变。"""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "profit_rules": [
            {
                "id": "under_29_subsidy",
                "name": "SHEIN 29美元以下运费补贴",
                "condition_field": "sale_price_usd",
                "compare_op": "lt",
                "condition_value": 29.0,
                "direction": "income",
                "adjustment_type": "fixed",
                "adjustment_value": 2.99,
                "currency": "USD",
                "enabled": True,
                "archived": False,
            }
        ],
        "selected_profit_rule_id": "",  # 用户明确选择"不使用规则"
        "seed_versions": ["profit_rules_v1"],
    }), encoding="utf-8")

    service = SettingsService(settings_path)
    loaded = service.load()

    # 空字符串保持不变
    assert loaded["selected_profit_rule_id"] == ""


def test_valid_selected_rule_id_unchanged(tmp_path: Path):
    """selected_profit_rule_id 指向有效 enabled 且非 archived 规则时，保持原 ID 不变。"""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "profit_rules": [
            {
                "id": "under_29_subsidy",
                "name": "SHEIN 29美元以下运费补贴",
                "condition_field": "sale_price_usd",
                "compare_op": "lt",
                "condition_value": 29.0,
                "direction": "income",
                "adjustment_type": "fixed",
                "adjustment_value": 2.99,
                "currency": "USD",
                "enabled": True,
                "archived": False,
            }
        ],
        "selected_profit_rule_id": "under_29_subsidy",  # 有效 ID
        "seed_versions": ["profit_rules_v1"],
    }), encoding="utf-8")

    service = SettingsService(settings_path)
    loaded = service.load()

    # 有效 ID 保持不变
    assert loaded["selected_profit_rule_id"] == "under_29_subsidy"


def test_selected_rule_id_pointing_to_disabled_or_archived_repaired(tmp_path: Path):
    """selected_profit_rule_id 指向 disabled 或 archived 规则时，视为失效并修正。"""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "profit_rules": [
            {
                "id": "disabled_rule",
                "name": "已禁用规则",
                "condition_field": "sale_price_usd",
                "compare_op": "lt",
                "condition_value": 29.0,
                "direction": "income",
                "adjustment_type": "fixed",
                "adjustment_value": 2.99,
                "currency": "USD",
                "enabled": False,  # disabled
                "archived": False,
            },
            {
                "id": "valid_rule",
                "name": "有效规则",
                "condition_field": "sale_price_usd",
                "compare_op": "lt",
                "condition_value": 30.0,
                "direction": "income",
                "adjustment_type": "fixed",
                "adjustment_value": 3.99,
                "currency": "USD",
                "enabled": True,
                "archived": False,
            }
        ],
        "selected_profit_rule_id": "disabled_rule",  # 指向 disabled 规则
        "seed_versions": ["profit_rules_v1"],
    }), encoding="utf-8")

    service = SettingsService(settings_path)
    loaded = service.load()

    # 修正为第一个有效启用规则
    assert loaded["selected_profit_rule_id"] == "valid_rule"


def test_selected_rule_id_with_no_valid_rules_becomes_empty(tmp_path: Path):
    """所有规则都 disabled/archived 时，selected_profit_rule_id 变为空字符串。"""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "profit_rules": [
            {
                "id": "disabled_rule",
                "name": "已禁用规则",
                "condition_field": "sale_price_usd",
                "compare_op": "lt",
                "condition_value": 29.0,
                "direction": "income",
                "adjustment_type": "fixed",
                "adjustment_value": 2.99,
                "currency": "USD",
                "enabled": False,
                "archived": False,
            }
        ],
        "selected_profit_rule_id": "disabled_rule",  # 指向唯一但 disabled 的规则
        "seed_versions": ["profit_rules_v1"],
    }), encoding="utf-8")

    service = SettingsService(settings_path)
    loaded = service.load()

    # 没有有效规则，清空
    assert loaded["selected_profit_rule_id"] == ""
