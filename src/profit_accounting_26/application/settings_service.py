from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from profit_accounting_26.domain.models import Forwarder
from profit_accounting_26.shared import StaleDataDirectoryError, ensure_data_dir_allowed
from profit_accounting_26.domain.rules import (
    AdjustmentDirection,
    AdjustmentRule,
    AdjustmentType,
    CompareOp,
)


DEFAULT_SUBSIDY_RULE = {
    "id": "under_29_subsidy",
    "name": "SHEIN 29美元以下运费补贴",
    "condition_field": "sale_price_usd",
    "compare_op": "lt",
    "condition_value": 29.0,
    "direction": "income",
    "adjustment_type": "fixed",
    "adjustment_value": 2.99,
    "currency": "USD",
    "percent_base": None,
    "enabled": True,
    "archived": False,
    "description": "最终售价低于29美元时增加2.99美元收入。",
}

# 一次性 seed 标记：默认利润规则只在首次初始化（或旧文件缺少该键）时补一次。
# 用户删除后即使文件缺少 profit_rules 键也不会再次复活。
DEFAULT_RULE_SEED_VERSION = "profit_rules_v1"


class SettingsService:
    def __init__(self, path: str | Path, *, defaults_path: str | Path | None = None) -> None:
        self.path = Path(path)
        self.defaults_path = Path(defaults_path) if defaults_path else None

    def _default_data(self) -> dict:
        if self.defaults_path and self.defaults_path.is_file():
            data = json.loads(self.defaults_path.read_text(encoding="utf-8"))
        else:
            data = {
                "schema_version": 1,
                "display_name": "用户",
                "exchange_rate_usd_to_rmb": 7.2,
                "default_tail_fee_rmb": 40.0,
                "default_tail_fee_usd": 40.0 / 7.2,
                "image_slot_count": 5,
                "image_slot_types": ["主图", "商品信息", "尺寸/重量", "商品信息", "尺寸/重量"],
                "forwarders": [],
            }
        data.setdefault("profit_rules", [deepcopy(DEFAULT_SUBSIDY_RULE)])
        data.setdefault("image_slot_types", ["主图", "商品信息", "尺寸/重量", "商品信息", "尺寸/重量"])
        data.setdefault("log_level", "INFO")
        data.setdefault("log_retention_days", 30)
        return data

    def _creation_allowed(self) -> bool:
        """settings 文件所在数据目录缺失时是否允许创建。

        生命周期守卫：目录已被 location.json 抛弃且已删除时，
        load 不得静默重建目录/文件（返回默认值的内存副本即可）。
        """
        try:
            ensure_data_dir_allowed(self.path.parent)
        except StaleDataDirectoryError:
            return False
        return True

    def load(self) -> dict:
        if not self.path.is_file():
            data = self._default_data()
            data.setdefault("seed_versions", [])
            if DEFAULT_RULE_SEED_VERSION not in data["seed_versions"]:
                data["seed_versions"].append(DEFAULT_RULE_SEED_VERSION)
            if self._creation_allowed():
                self.save(data)
            return data
        current = json.loads(self.path.read_text(encoding="utf-8"))
        defaults = self._default_data()
        merged = {**defaults, **current}
        merged.setdefault("forwarders", defaults.get("forwarders", []))
        seed_versions = list(current.get("seed_versions", []))
        merged["profit_rules"] = self._resolve_profit_rules(current, seed_versions)
        merged["seed_versions"] = seed_versions
        needs_save = DEFAULT_RULE_SEED_VERSION not in seed_versions
        if DEFAULT_RULE_SEED_VERSION not in seed_versions:
            # 一次性迁移：旧文件缺失 seed 标记时补记，避免后续"缺失就补回"。
            seed_versions.append(DEFAULT_RULE_SEED_VERSION)
        # 修复失效的 selected_profit_rule_id
        if self._repair_stale_selected_rule_id(merged):
            needs_save = True
        if needs_save:
            self.save(merged)
        return merged
    
    @staticmethod
    def _repair_stale_selected_rule_id(settings: dict) -> bool:
        """检查并修复失效的 selected_profit_rule_id。
    
        如果 selected_profit_rule_id 是非空字符串但不在 enabled=True 且 archived=False
        的规则中，则自动修正为第一个有效规则 ID；如果没有有效规则则清空。
        空字符串保持不变（代表用户明确选择"不使用规则"）。
    
        返回 True 表示发生了修正，需要持久化。
        """
        selected = str(settings.get("selected_profit_rule_id") or "")
        if not selected:
            # 空字符串代表用户明确选择"不使用规则"，保持不变
            return False
        # 找出所有有效规则：enabled=True 且 archived=False
        valid_rule_ids = [
            str(rule.get("id"))
            for rule in settings.get("profit_rules", [])
            if rule.get("enabled", True) and not rule.get("archived", False)
        ]
        if selected in valid_rule_ids:
            # selected ID 仍然有效，无需修正
            return False
        # selected ID 已失效，修正为第一个有效规则或清空
        settings["selected_profit_rule_id"] = valid_rule_ids[0] if valid_rule_ids else ""
        return True

    @classmethod
    def _resolve_profit_rules(cls, current: dict, seed_versions: list[str]) -> list:
        """按一次性 seed 语义解析利润规则，禁止缺失时每次补回默认规则。"""
        if "profit_rules" in current:
            return current["profit_rules"]
        if DEFAULT_RULE_SEED_VERSION not in seed_versions:
            return [deepcopy(DEFAULT_SUBSIDY_RULE)]
        return []

    def save(self, data: dict) -> None:
        # 生命周期守卫：数据目录已被 location.json 抛弃且被删除时拒绝重建，
        # 不允许陈旧会话复活废弃目录（目录仍存在时照常写入，会话延续）。
        ensure_data_dir_allowed(self.path.parent)
        self.save_copy(data, self.path)

    @staticmethod
    def save_copy(data: dict, path: str | Path) -> None:
        """Atomically persist settings to an explicitly selected data directory."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(target)

    @staticmethod
    def new_forwarder(name: str, rate: float, fixed_fee: float, divisor: float) -> Forwarder:
        forwarder = Forwarder(
            id=f"forwarder_{uuid4().hex}",
            name=name,
            rate_rmb_per_kg=rate,
            fixed_fee_rmb=fixed_fee,
            volume_divisor=divisor,
        )
        forwarder.validate()
        return forwarder

    @staticmethod
    def archive(forwarder: Forwarder) -> Forwarder:
        data = asdict(forwarder)
        data["archived"] = True
        data["enabled"] = False
        return Forwarder(**data)

    @staticmethod
    def restore(forwarder: Forwarder) -> Forwarder:
        data = asdict(forwarder)
        data["archived"] = False
        data["enabled"] = False
        return Forwarder(**data)

    @staticmethod
    def forwarders_from_settings(settings: dict) -> list[Forwarder]:
        output: list[Forwarder] = []
        for item in settings.get("forwarders", []):
            try:
                output.append(Forwarder(**item))
            except (TypeError, ValueError):
                continue
        return output

    @staticmethod
    def rules_from_settings(settings: dict) -> list[AdjustmentRule]:
        rules: list[AdjustmentRule] = []
        for raw in settings.get("profit_rules", []):
            try:
                rules.append(
                    AdjustmentRule(
                        id=str(raw["id"]),
                        name=str(raw["name"]),
                        condition_field=str(raw["condition_field"]),
                        compare_op=CompareOp(str(raw["compare_op"])),
                        condition_value=float(raw["condition_value"]),
                        direction=AdjustmentDirection(str(raw["direction"])),
                        adjustment_type=AdjustmentType(str(raw["adjustment_type"])),
                        adjustment_value=float(raw["adjustment_value"]),
                        currency=str(raw.get("currency") or "RMB"),
                        percent_base=raw.get("percent_base"),
                        enabled=bool(raw.get("enabled", True)),
                        archived=bool(raw.get("archived", False)),
                        description=str(raw.get("description") or ""),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return rules

    @staticmethod
    def rule_to_dict(rule: AdjustmentRule) -> dict:
        data = asdict(rule)
        data["compare_op"] = rule.compare_op.value
        data["direction"] = rule.direction.value
        data["adjustment_type"] = rule.adjustment_type.value
        return data
