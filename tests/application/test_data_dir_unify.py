"""用户数据目录统一：所有用户数据只写当前运行的数据目录。

覆盖用户第六阶段清单（9-20）：
- 9/10/11/12/13：利润规则 / 货代 / API 保存 / API 删除 / API binding 只写
  current context data_dir，不再向 location.json 指向的另一目录镜像写入；
- 14/15/16：历史记录 / 图片 / 风险日志保存在 current data_dir；
- 17：新数据目录初始化得到默认货代（深圳 80+10 / 义乌 100+6 / divisor 8000）；
- 18：用户修改货代后重启不重新用 defaults 覆盖；
- 19：用户修改利润规则后重启仍存在；
- 20：用户清空利润规则后 seed 机制不擅自复活。
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PIL import Image as PILImage

from profit_accounting_26.application import AppContext, SettingsService
from profit_accounting_26.application.api_profile_store import ApiProfileStore
from profit_accounting_26.application.settings_service import DEFAULT_SUBSIDY_RULE
from profit_accounting_26.shared import ApplicationPaths, resource_path
from profit_accounting_26.ui.pages import settings_page as settings_mod
from profit_accounting_26.ui.pages import SettingsPage


class FakeMessage:
    """屏蔽弹窗，只记录调用。"""

    calls: list[tuple[str, str]] = []

    @classmethod
    def reset(cls) -> None:
        cls.calls = []

    @staticmethod
    def _record(kind):
        def _call(_parent, title, text, *args, **kwargs):
            FakeMessage.calls.append((kind, str(text)))
            return 0

        return _call

    information = staticmethod(_record("information"))
    warning = staticmethod(_record("warning"))
    critical = staticmethod(_record("critical"))


@pytest.fixture
def dual(tmp_path, monkeypatch):
    """current = 当前运行目录；other = location.json 指向的另一目录（旧镜像逻辑会双写它）。"""
    current = tmp_path / "current"
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setattr(
        ApplicationPaths,
        "location_config_path",
        classmethod(lambda _cls: tmp_path / "home" / "location.json"),
    )
    ApplicationPaths.save_data_dir(other)
    context = AppContext.create_default(paths=ApplicationPaths.from_data_dir(current))
    return context, current, other


@pytest.fixture
def page(qapp, monkeypatch, dual):
    context, _current, _other = dual
    FakeMessage.reset()
    monkeypatch.setattr(settings_mod, "QMessageBox", FakeMessage)
    widget = SettingsPage(context)
    yield widget
    widget.deleteLater()
    qapp.processEvents()


# ------------------------------------------------------------------
# 9-13：持久化只写 current context data_dir
# ------------------------------------------------------------------


def test_persist_rules_only_writes_current_data_dir(page, dual):
    _context, current, other = dual
    page.rules_data = [deepcopy(DEFAULT_SUBSIDY_RULE)]
    page._persist_rules_now()
    content = (current / "settings.json").read_text(encoding="utf-8")
    assert "under_29_subsidy" in content
    assert not (other / "settings.json").exists()


def test_persist_forwarders_only_writes_current_data_dir(page, dual):
    _context, current, other = dual
    forwarder = SettingsService.new_forwarder("深圳测试", 80.0, 10.0, 8000.0)
    page._load_forwarder_rows([asdict(forwarder)])
    page._persist_forwarders_now()
    content = (current / "settings.json").read_text(encoding="utf-8")
    assert "深圳测试" in content
    assert not (other / "settings.json").exists()


def test_save_api_profile_only_writes_current_data_dir(page, dual):
    _context, current, other = dual
    page.api_profile_name.setText("测试配置")
    page.vision_endpoint.setText("https://example.com/v1")
    page.vision_model.setText("model-x")
    page.save_api_profile()
    assert (current / "api_profiles.json").is_file()
    assert not (other / "api_profiles.json").exists()
    assert not (other / "api_keys.local.json").exists()


def test_delete_api_profile_only_touches_current_data_dir(page, dual, monkeypatch):
    _context, current, other = dual
    page.api_profile_name.setText("待删配置")
    page.vision_endpoint.setText("https://example.com/v1")
    page.vision_model.setText("model-x")
    page.save_api_profile()
    assert (current / "api_profiles.json").is_file()
    profile_id = str(page.api_profile_select.currentData() or "")
    assert profile_id
    monkeypatch.setattr(settings_mod, "confirm_action", lambda *a, **k: True)
    page._delete_api_profile()
    assert ApiProfileStore(current).load_public()["profiles"] == []
    assert not (other / "api_profiles.json").exists()
    assert not (other / "api_keys.local.json").exists()


def test_save_settings_binding_only_writes_current_data_dir(page, dual):
    _context, current, other = dual
    page.save_settings()
    assert (current / "settings.json").is_file()
    assert not (other / "settings.json").exists()
    assert not (other / "api_profiles.json").exists()


# ------------------------------------------------------------------
# 14-16：历史 / 图片 / 风险日志保存在 current data_dir
# ------------------------------------------------------------------


def test_history_record_goes_to_current_sqlite(tmp_path, monkeypatch):
    current = tmp_path / "current"
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setattr(
        ApplicationPaths,
        "location_config_path",
        classmethod(lambda _cls: tmp_path / "home" / "location.json"),
    )
    ApplicationPaths.save_data_dir(other)
    context = AppContext.create_default(paths=ApplicationPaths.from_data_dir(current))
    context.record_service.save(
        {"product_name": "测试记录", "status": "active"},
        images=[],
        ai_initial=None,
    )
    assert len(context.store.list_records(limit=10)) == 1
    assert not (other / "profit_accounting_26.sqlite3").exists()


def test_image_goes_to_current_images_dir(tmp_path):
    current = tmp_path / "current"
    paths = ApplicationPaths.from_data_dir(current)
    context = AppContext.create_default(paths=paths)
    source = tmp_path / "demo.png"
    PILImage.new("RGB", (16, 16), (200, 100, 50)).save(source, "PNG")
    reference = context.image_store.add_file(source, original_filename="demo.png")
    assert reference.image_id
    assert any((current / "images").rglob("*"))
    # storage_key 形如 images/originals/<hash>/<name>.png，相对 data_dir
    assert (current / reference.storage_key).is_file()


def test_risk_log_goes_to_current_logs_dir(tmp_path):
    from profit_accounting_26.product_collector import product_risk_log

    current = tmp_path / "current"
    paths = ApplicationPaths.from_data_dir(current)
    paths.ensure()
    product_risk_log.configure(current)
    log = product_risk_log.log_file_path(current)
    assert log == current / "logs" / "product_risk" / "product_risk.log"
    assert (current / "logs" / "product_risk").is_dir()


# ------------------------------------------------------------------
# 17-20：初始化与持久化语义
# ------------------------------------------------------------------


def test_new_dir_seeds_default_forwarders(tmp_path):
    paths = ApplicationPaths.from_data_dir(tmp_path / "new")
    service = SettingsService(
        paths.settings_path, defaults_path=resource_path("config/defaults.json")
    )
    settings = service.load()
    by_name = {item["name"]: item for item in settings["forwarders"]}
    shenzhen = by_name["深圳货代"]
    assert (
        shenzhen["rate_rmb_per_kg"],
        shenzhen["fixed_fee_rmb"],
        shenzhen["volume_divisor"],
    ) == (80.0, 10.0, 8000.0)
    yiwu = by_name["义乌货代"]
    assert (
        yiwu["rate_rmb_per_kg"],
        yiwu["fixed_fee_rmb"],
        yiwu["volume_divisor"],
    ) == (100.0, 6.0, 8000.0)


def test_user_forwarders_survive_restart(tmp_path):
    paths = ApplicationPaths.from_data_dir(tmp_path / "new")
    defaults_path = resource_path("config/defaults.json")
    service = SettingsService(paths.settings_path, defaults_path=defaults_path)
    settings = service.load()
    custom = SettingsService.new_forwarder("我的货代", 66.0, 9.0, 7000.0)
    settings["forwarders"] = [asdict(custom)]
    settings["selected_forwarder_id"] = custom.id
    service.save(settings)

    reloaded = SettingsService(paths.settings_path, defaults_path=defaults_path).load()
    assert [item["name"] for item in reloaded["forwarders"]] == ["我的货代"]
    assert reloaded["forwarders"][0]["rate_rmb_per_kg"] == 66.0
    assert reloaded["forwarders"][0]["volume_divisor"] == 7000.0


def test_user_profit_rules_survive_restart(tmp_path):
    paths = ApplicationPaths.from_data_dir(tmp_path / "new")
    defaults_path = resource_path("config/defaults.json")
    service = SettingsService(paths.settings_path, defaults_path=defaults_path)
    settings = service.load()
    custom = deepcopy(DEFAULT_SUBSIDY_RULE)
    custom.update({"id": "custom_rule", "name": "自定义规则", "adjustment_value": 5.0})
    settings["profit_rules"] = [custom]
    settings["selected_profit_rule_id"] = "custom_rule"
    service.save(settings)

    reloaded = SettingsService(paths.settings_path, defaults_path=defaults_path).load()
    assert [rule["id"] for rule in reloaded["profit_rules"]] == ["custom_rule"]
    assert reloaded["profit_rules"][0]["adjustment_value"] == 5.0


def test_seed_does_not_resurrect_deleted_rules(tmp_path):
    paths = ApplicationPaths.from_data_dir(tmp_path / "new")
    defaults_path = resource_path("config/defaults.json")
    service = SettingsService(paths.settings_path, defaults_path=defaults_path)
    settings = service.load()
    settings["profit_rules"] = []
    settings["selected_profit_rule_id"] = ""
    service.save(settings)

    reloaded = SettingsService(paths.settings_path, defaults_path=defaults_path).load()
    assert reloaded["profit_rules"] == []

    # seed 已标记：即使再移除 profit_rules 键，也不会重新补默认规则
    file = paths.settings_path
    payload = json.loads(file.read_text(encoding="utf-8"))
    payload.pop("profit_rules")
    file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    reloaded2 = SettingsService(paths.settings_path, defaults_path=defaults_path).load()
    assert reloaded2["profit_rules"] == []


def test_context_uses_selected_dir_for_settings_db_api(tmp_path):
    selected = tmp_path / "selected"
    paths = ApplicationPaths.from_data_dir(selected)
    context = AppContext.create_default(paths=paths)
    assert context.paths.data_dir == selected.resolve()
    assert context.api_profile_store.data_dir == selected.resolve()
    assert (selected / "settings.json").is_file()
    assert (selected / "profit_accounting_26.sqlite3").is_file()
    assert (selected / "images").is_dir()
