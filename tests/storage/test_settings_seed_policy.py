"""阶段 1：默认利润规则一次性 seed / 不复活策略。"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

from profit_accounting_26.application import AppContext, SettingsService
from profit_accounting_26.application.settings_service import (
    DEFAULT_RULE_SEED_VERSION,
    DEFAULT_SUBSIDY_RULE,
)


def _fresh_settings(tmp_path: Path) -> dict:
    return SettingsService(tmp_path / "settings.json").load()


def test_fresh_data_dir_seeds_default_rule_exactly_once(tmp_path: Path):
    service = SettingsService(tmp_path / "settings.json")
    data = service.load()
    assert [rule["id"] for rule in data["profit_rules"]] == ["under_29_subsidy"]
    assert DEFAULT_RULE_SEED_VERSION in data["seed_versions"]

    # 重复 load 不重复 seed，磁盘上规则只出现一次
    again = service.load()
    assert again["profit_rules"] == data["profit_rules"]
    raw = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert len(raw["profit_rules"]) == 1


def test_app_context_first_init_seeds_default_rule_once(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    context = AppContext.create_default()
    rules = context.settings_service.load()["profit_rules"]
    assert [rule["id"] for rule in rules] == ["under_29_subsidy"]
    raw = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert len(raw["profit_rules"]) == 1
    assert DEFAULT_RULE_SEED_VERSION in raw["seed_versions"]


def test_delete_default_rule_does_not_resurrect_after_restart(tmp_path: Path):
    service = SettingsService(tmp_path / "settings.json")
    data = service.load()
    data["profit_rules"] = []
    data["selected_profit_rule_id"] = ""
    service.save(data)

    reloaded = _fresh_settings(tmp_path)
    assert reloaded["profit_rules"] == []
    assert DEFAULT_RULE_SEED_VERSION in reloaded["seed_versions"]


def test_legacy_file_without_rules_key_seeds_once_then_stays_deleted(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"display_name": "旧用户", "exchange_rate_usd_to_rmb": 7.1}),
        encoding="utf-8",
    )
    service = SettingsService(path)
    data = service.load()
    assert [rule["id"] for rule in data["profit_rules"]] == ["under_29_subsidy"]
    assert DEFAULT_RULE_SEED_VERSION in data["seed_versions"]

    # 用户删除后重启不再复活
    data["profit_rules"] = []
    service.save(data)
    reloaded = SettingsService(path).load()
    assert reloaded["profit_rules"] == []


def test_legacy_file_with_empty_rules_keeps_deletion(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"profit_rules": []}), encoding="utf-8")
    data = SettingsService(path).load()
    assert data["profit_rules"] == []
    assert DEFAULT_RULE_SEED_VERSION in data["seed_versions"]


def test_modify_default_rule_survives_restart(tmp_path: Path):
    service = SettingsService(tmp_path / "settings.json")
    data = service.load()
    data["profit_rules"][0]["adjustment_value"] = 3.49
    data["profit_rules"][0]["name"] = "SHEIN 修改后补贴"
    service.save(data)

    reloaded = _fresh_settings(tmp_path)
    assert reloaded["profit_rules"][0]["adjustment_value"] == 3.49
    assert reloaded["profit_rules"][0]["name"] == "SHEIN 修改后补贴"


def test_custom_rule_persists_with_default_rule(tmp_path: Path):
    service = SettingsService(tmp_path / "settings.json")
    data = service.load()
    custom = deepcopy(DEFAULT_SUBSIDY_RULE)
    custom.update({"id": "custom_rule", "name": "自定义规则", "condition_value": 50.0})
    data["profit_rules"].append(custom)
    service.save(data)

    reloaded = _fresh_settings(tmp_path)
    rule_ids = [rule["id"] for rule in reloaded["profit_rules"]]
    assert "under_29_subsidy" in rule_ids
    assert "custom_rule" in rule_ids


def test_forwarders_persist_across_restart(tmp_path: Path):
    service = SettingsService(tmp_path / "settings.json")
    data = service.load()
    forwarder = SettingsService.new_forwarder("测试货代", 88, 7, 8000)
    data["forwarders"] = [asdict(forwarder)]
    data["selected_forwarder_id"] = forwarder.id
    service.save(data)

    reloaded = _fresh_settings(tmp_path)
    assert [item["id"] for item in reloaded["forwarders"]] == [forwarder.id]
    assert reloaded["selected_forwarder_id"] == forwarder.id
