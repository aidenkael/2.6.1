"""记录快照保持测试。

覆盖验收要求：保存后当前汇率或规则变化，重开仍保持保存时的快照。

- RecordService.save 持久化 profit_scenarios 快照；
- 保存后修改 settings 的汇率/利润规则；
- RecordService.load 返回的 profit_scenarios 仍为保存值，不被当前状态污染。
"""

from __future__ import annotations

from profit_accounting_26.application import RecordService, SettingsService
from profit_accounting_26.application.profit_scenario_codec import SCHEMA_VERSION
from profit_accounting_26.shared import ApplicationPaths
from profit_accounting_26.shared.paths import resource_path
from profit_accounting_26.storage import SQLiteStore


class _MiniContext:
    def __init__(self, record_service, settings_service):
        self.record_service = record_service
        self.settings_service = settings_service


def _make_context(tmp_path):
    paths = ApplicationPaths(
        data_dir=tmp_path,
        database_path=tmp_path / "app.sqlite3",
        settings_path=tmp_path / "settings.json",
        images_dir=tmp_path / "images",
        exports_dir=tmp_path / "exports",
        calibration_packages_dir=tmp_path / "calibration_packages",
    )
    paths.ensure()
    store = SQLiteStore(paths.database_path)
    store.initialize()
    settings_service = SettingsService(
        paths.settings_path, defaults_path=resource_path("config/defaults.json")
    )
    settings_service.load()
    record_service = RecordService(store, paths)
    return _MiniContext(record_service, settings_service)


def test_saved_snapshot_kept_after_rate_and_rule_changes(tmp_path):
    context = _make_context(tmp_path)
    record_service = context.record_service

    scenarios = {
        "schema_version": SCHEMA_VERSION,
        "driver": "no_activity_price",
        "calculation_total_cost_rmb": 117.0,
        "shein_quote_usd": 0.0,
        "reserve_percent": 10.0,
        "no_activity": {"sale_price_usd": 30.0, "sale_price_rmb": 216.0,
                        "profit_rmb": 99.0, "profit_usd": 13.75, "rule_status": {}},
        "activity": {"sale_price_usd": 27.0, "sale_price_rmb": 194.4,
                     "profit_rmb": 98.93, "profit_usd": 13.74,
                     "profit_rate_on_cost": 0.8455, "rule_status": {}},
    }
    record_id = record_service.save(
        {"product_name": "快照测试", "profit_scenarios": scenarios,
         "layers": {"calculated": {"sale_price_usd": 30.0, "exchange_rate": 7.2}}},
        images=[],
    )

    # 保存后修改汇率并禁用全部利润规则
    settings = context.settings_service.load()
    settings["exchange_rate_usd_to_rmb"] = 6.9
    for rule in settings.get("profit_rules", []):
        rule["enabled"] = False
    context.settings_service.save(settings)

    loaded = record_service.load(record_id)
    snap = loaded["profit_scenarios"]
    # 快照保持保存值，不随当前汇率/规则变化
    assert snap["calculation_total_cost_rmb"] == 117.0
    assert snap["no_activity"]["sale_price_rmb"] == 216.0
    assert snap["no_activity"]["profit_rmb"] == 99.0
    assert snap["activity"]["sale_price_usd"] == 27.0
    assert snap["no_activity"]["sale_price_usd"] == 30.0
    # 保存的旧汇率仍记录在 layers.calculated 中
    assert loaded["layers"]["calculated"]["exchange_rate"] == 7.2


def test_legacy_saved_record_snapshot_untouched_by_new_fields(tmp_path):
    """旧格式记录保存后，重开不被新字段写坏（附加字段策略）。"""
    context = _make_context(tmp_path)
    record_service = context.record_service

    legacy_payload = {
        "product_name": "旧记录",
        "layers": {"calculated": {"sale_price_usd": 25.0, "exchange_rate": 7.2,
                                  "profit_rmb": 30.0, "calculation_cost_rmb": 150.0}},
    }
    record_id = record_service.save(legacy_payload, images=[])

    settings = context.settings_service.load()
    settings["exchange_rate_usd_to_rmb"] = 6.5
    context.settings_service.save(settings)

    loaded = record_service.load(record_id)
    assert loaded["layers"]["calculated"]["sale_price_usd"] == 25.0
    assert loaded["layers"]["calculated"]["exchange_rate"] == 7.2
    # 旧记录不含 profit_scenarios，打开时由 codec 兼容映射（不写入记录）
    assert "profit_scenarios" not in loaded
