"""Settings 物流校准规则（校准包版本管理）测试（Stage 4 Commit 2）。

覆盖：
- 进入 Settings 自动加载版本列表；
- 导入后自动刷新；
- 任意版本启用与 active 状态刷新；
- 删除普通版本 / 删除 active 后 fallback 到 builtin；
- builtin 不可删除；
- 新区没有 Refresh / Rollback 按钮。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QPushButton, QWidget

from profit_accounting_26.application import AppContext
from profit_accounting_26.ui.pages import settings_page as settings_mod
from profit_accounting_26.ui.pages import SettingsPage

# qapp 由 tests/conftest.py 的会话级 fixture 提供


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


def make_package_file(tmp_path: Path, name: str, version: str) -> Path:
    source = tmp_path / name
    source.write_text(
        json.dumps(
            {
                "version": version,
                "samples": [
                    {
                        "sample_id": f"S-{version}",
                        "product_type": "soft_pouch",
                        "material": "pvc",
                        "rigidity": "soft",
                        "size_reduction_ratio": 0.6,
                        "usable_for_rule_learning": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return source


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


class FakeFileDialog:
    selected: str = ""

    @staticmethod
    def getOpenFileName(*_args, **_kwargs):
        return FakeFileDialog.selected, ""


@pytest.fixture
def page(qapp, context, monkeypatch):
    FakeMessage.reset()
    monkeypatch.setattr(settings_mod, "QMessageBox", FakeMessage)
    widget = SettingsPage(context)
    yield widget
    widget.deleteLater()
    qapp.processEvents()


def row_of(page: SettingsPage, version: str) -> int:
    table = page.calibration_table
    for row in range(table.rowCount()):
        if table.item(row, 0).text() == version:
            return row
    return -1


def test_settings_auto_loads_calibration_list_on_entry(qapp, page, context):
    table = page.calibration_table
    builtin = context.calibration_manager.active_package()
    assert table.rowCount() == len(context.calibration_manager.list_packages())
    row = row_of(page, builtin["version"])
    assert row >= 0
    assert table.item(row, 1).text() == "当前启用"
    assert builtin["version"] in page.calibration_status.text()


def test_import_package_refreshes_list_and_activates(qapp, page, context, tmp_path, monkeypatch):
    source = make_package_file(tmp_path, "custom.json", "custom-v2")
    FakeFileDialog.selected = str(source)
    monkeypatch.setattr(settings_mod, "QFileDialog", FakeFileDialog)

    page._import_calibration_package()

    row = row_of(page, "custom-v2")
    assert row >= 0
    assert page.calibration_table.item(row, 1).text() == "当前启用"
    assert context.calibration_manager.active_package()["version"] == "custom-v2"
    assert context.packaging_service.calibration_version == "custom-v2"
    assert "custom-v2" in page.calibration_status.text()


def test_activate_any_version_updates_active_state(qapp, page, context, tmp_path, monkeypatch):
    source = make_package_file(tmp_path, "custom.json", "custom-v2")
    FakeFileDialog.selected = str(source)
    monkeypatch.setattr(settings_mod, "QFileDialog", FakeFileDialog)
    page._import_calibration_package()

    builtin = next(
        item
        for item in context.calibration_manager.list_packages()
        if item["metadata"].get("builtin")
    )
    page.calibration_table.selectRow(row_of(page, builtin["version"]))
    page._activate_selected_calibration()

    assert context.calibration_manager.active_package()["id"] == builtin["id"]
    assert context.packaging_service.calibration_version == builtin["version"]
    row = row_of(page, builtin["version"])
    assert page.calibration_table.item(row, 1).text() == "当前启用"
    assert page.calibration_table.item(row_of(page, "custom-v2"), 1).text() == "未启用"


def test_delete_non_active_version(qapp, page, context, tmp_path, monkeypatch):
    source = make_package_file(tmp_path, "custom.json", "custom-v2")
    FakeFileDialog.selected = str(source)
    monkeypatch.setattr(settings_mod, "QFileDialog", FakeFileDialog)
    page._import_calibration_package()
    # 再导入一个并启用，然后删除未启用的 custom-v2
    second = make_package_file(tmp_path, "second.json", "second-v3")
    FakeFileDialog.selected = str(second)
    page._import_calibration_package()

    monkeypatch.setattr(settings_mod, "confirm_action", lambda *a, **k: True)
    page.calibration_table.selectRow(row_of(page, "custom-v2"))
    page._delete_selected_calibration()

    assert row_of(page, "custom-v2") == -1
    versions = {item["version"] for item in context.calibration_manager.list_packages()}
    assert "custom-v2" not in versions
    assert context.calibration_manager.active_package()["version"] == "second-v3"


def test_delete_active_version_falls_back_to_builtin(qapp, page, context, tmp_path, monkeypatch):
    source = make_package_file(tmp_path, "custom.json", "custom-v2")
    FakeFileDialog.selected = str(source)
    monkeypatch.setattr(settings_mod, "QFileDialog", FakeFileDialog)
    page._import_calibration_package()

    monkeypatch.setattr(settings_mod, "confirm_action", lambda *a, **k: True)
    page.calibration_table.selectRow(row_of(page, "custom-v2"))
    page._delete_selected_calibration()

    builtin = context.calibration_manager.active_package()
    assert builtin["metadata"].get("builtin") is True
    row = row_of(page, builtin["version"])
    assert page.calibration_table.item(row, 1).text() == "当前启用"
    assert row_of(page, "custom-v2") == -1
    assert context.packaging_service.calibration_version == builtin["version"]


def test_delete_cancelled_keeps_package(qapp, page, context, tmp_path, monkeypatch):
    source = make_package_file(tmp_path, "custom.json", "custom-v2")
    FakeFileDialog.selected = str(source)
    monkeypatch.setattr(settings_mod, "QFileDialog", FakeFileDialog)
    page._import_calibration_package()

    monkeypatch.setattr(settings_mod, "confirm_action", lambda *a, **k: False)
    page.calibration_table.selectRow(row_of(page, "custom-v2"))
    page._delete_selected_calibration()

    assert row_of(page, "custom-v2") >= 0
    assert context.calibration_manager.active_package()["version"] == "custom-v2"


def test_builtin_delete_button_disabled_and_rejected(qapp, page, context, monkeypatch):
    builtin = next(
        item
        for item in context.calibration_manager.list_packages()
        if item["metadata"].get("builtin")
    )
    page.calibration_table.selectRow(row_of(page, builtin["version"]))
    assert not page.btn_delete_calibration.isEnabled()

    # 即使绕过按钮状态直接调用，Manager 层也拒绝删除
    monkeypatch.setattr(settings_mod, "confirm_action", lambda *a, **k: True)
    page._delete_selected_calibration()
    assert row_of(page, builtin["version"]) >= 0
    assert context.calibration_manager.active_package()["id"] == builtin["id"]


def test_no_refresh_or_rollback_buttons_in_settings(qapp, page):
    section = page._root.findChild(QWidget, "calibrationSection")
    assert section is not None
    buttons = [btn.text() for btn in section.findChildren(QPushButton)]
    assert buttons == ["导入校准包", "启用所选版本", "删除所选版本"]
