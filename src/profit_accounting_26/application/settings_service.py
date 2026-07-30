from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from profit_accounting_26.domain.models import Forwarder
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
        return data

    def load(self) -> dict:
        if not self.path.is_file():
            data = self._default_data()
            self.save(data)
            return data
        current = json.loads(self.path.read_text(encoding="utf-8"))
        defaults = self._default_data()
        merged = {**defaults, **current}
        merged.setdefault("profit_rules", defaults["profit_rules"])
        merged.setdefault("forwarders", defaults.get("forwarders", []))
        return merged

    def save(self, data: dict) -> None:
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
