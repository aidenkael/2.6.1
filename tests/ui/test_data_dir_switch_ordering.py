"""阶段 1：数据目录切换的提交顺序与失败回滚语义。

- location.json 只在 sync_user_config 全部成功后才写入；
- 配置同步失败时 location.json 保持原 data_dir，并弹出明确失败提示。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from profit_accounting_26.application.settings_migration import SyncSummary
from profit_accounting_26.shared import ApplicationPaths
from profit_accounting_26.ui.binders.main_window_binder import MainWindowBinder


class _FakeSettingsService:
    def load(self) -> dict:
        return {}


class _FakePaths:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.database_path = data_dir / "profit_accounting_26.sqlite3"


class _FakeContext:
    def __init__(self, data_dir: Path) -> None:
        self.paths = _FakePaths(data_dir)
        self.settings_service = _FakeSettingsService()
        self.store = object()


def _install_location_json(tmp_path: Path, monkeypatch, target: Path) -> None:
    monkeypatch.setattr(
        ApplicationPaths,
        "location_config_path",
        classmethod(lambda cls: tmp_path / "home" / "location.json"),
    )
    ApplicationPaths.save_data_dir(target)


def test_location_json_unchanged_when_config_sync_fails(tmp_path: Path, monkeypatch):
    import profit_accounting_26.application.settings_migration as migration_module
    import profit_accounting_26.ui.binders.main_window_binder as binder_module

    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    _install_location_json(tmp_path, monkeypatch, old_dir)
    assert ApplicationPaths.configured_data_dir() == old_dir.resolve()

    def _boom(*_args, **_kwargs):
        raise RuntimeError("模拟配置同步失败")

    monkeypatch.setattr(migration_module, "sync_user_config", _boom)
    monkeypatch.setattr(
        binder_module.QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *_a, **_k: str(new_dir)),
    )
    errors: list = []
    monkeypatch.setattr(
        binder_module.QMessageBox,
        "critical",
        staticmethod(lambda *_a, **_k: errors.append(_a)),
    )

    binder = MainWindowBinder(object(), _FakeContext(old_dir))
    binder.change_data_directory()

    assert errors, "同步失败必须弹出明确失败提示"
    assert "配置同步失败" in str(errors[0])
    # location.json 内容仍指向旧 data_dir
    payload = json.loads(
        ApplicationPaths.location_config_path().read_text(encoding="utf-8")
    )
    assert payload["data_dir"] == str(old_dir.resolve())
    assert ApplicationPaths.configured_data_dir() == old_dir.resolve()


def test_location_json_committed_only_after_sync_succeeds(tmp_path: Path, monkeypatch):
    import profit_accounting_26.application.settings_migration as migration_module
    import profit_accounting_26.ui.binders.main_window_binder as binder_module

    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    _install_location_json(tmp_path, monkeypatch, old_dir)

    observed: dict[str, Path | None] = {}

    def _recording_sync(source, target, **_kwargs):
        observed["during_sync"] = ApplicationPaths.configured_data_dir()
        assert target == new_dir.resolve()
        return SyncSummary(copied_files=["settings.json"])

    monkeypatch.setattr(migration_module, "sync_user_config", _recording_sync)
    monkeypatch.setattr(
        binder_module.QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *_a, **_k: str(new_dir)),
    )
    monkeypatch.setattr(
        binder_module.QMessageBox,
        "information",
        staticmethod(lambda *_a, **_k: None),
    )

    binder = MainWindowBinder(object(), _FakeContext(old_dir))
    binder.change_data_directory()

    # 同步执行期间 location.json 仍指向旧目录，同步成功后才会切换
    assert observed["during_sync"] == old_dir.resolve()
    assert ApplicationPaths.configured_data_dir() == new_dir.resolve()
