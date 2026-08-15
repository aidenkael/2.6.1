"""数据目录切换（用户数据目录统一）：切换只写 location.json，重启后生效。

新语义（第四阶段 D）：
- 选择目标文件夹 → 只写 location.json，不复制 settings / API / 数据库 / 图片；
- 不自动合并或覆盖目标目录已有数据；
- 当前进程继续使用旧目录，直到重启；
- 选择当前目录本身 → 不写 location.json，直接提示。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

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


def _install_location_json(tmp_path: Path, monkeypatch, target: Path) -> None:
    monkeypatch.setattr(
        ApplicationPaths,
        "location_config_path",
        classmethod(lambda cls: tmp_path / "home" / "location.json"),
    )
    ApplicationPaths.save_data_dir(target)


def _location_target(tmp_path: Path) -> Path:
    payload = json.loads(
        ApplicationPaths.location_config_path().read_text(encoding="utf-8")
    )
    return Path(payload["data_dir"])


def test_switch_writes_location_without_copying_any_files(tmp_path: Path, monkeypatch):
    import profit_accounting_26.ui.binders.main_window_binder as binder_module

    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    _install_location_json(tmp_path, monkeypatch, old_dir)
    # 旧目录已有真实数据
    (old_dir / "settings.json").write_text(
        json.dumps({"forwarders": [{"name": "旧数据"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (old_dir / "api_profiles.json").write_text("{}", encoding="utf-8")

    infos: list = []
    monkeypatch.setattr(
        binder_module.QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *_a, **_k: str(new_dir)),
    )
    monkeypatch.setattr(
        binder_module.QMessageBox,
        "information",
        staticmethod(lambda *_a, **_k: infos.append(_a)),
    )

    binder = MainWindowBinder(object(), _FakeContext(old_dir))
    binder.change_data_directory()

    # location.json 指向新目录
    assert _location_target(tmp_path) == new_dir.resolve()
    # 新目录不产生任何自动复制/创建的数据文件
    assert not (new_dir / "settings.json").exists()
    assert not (new_dir / "api_profiles.json").exists()
    assert not (new_dir / "api_keys.local.json").exists()
    assert not (new_dir / "profit_accounting_26.sqlite3").exists()
    # 提示明确"重启后切换"
    assert infos, "必须弹出切换提示"
    assert "重启后切换" in infos[0][2]
    assert str(old_dir) in infos[0][2]
    # 旧目录数据原样
    assert "旧数据" in (old_dir / "settings.json").read_text(encoding="utf-8")


def test_switch_does_not_overwrite_existing_target_settings(
    tmp_path: Path, monkeypatch
):
    import profit_accounting_26.ui.binders.main_window_binder as binder_module

    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()
    _install_location_json(tmp_path, monkeypatch, old_dir)
    # 目标目录已有用户数据（模拟用户先手动放了一份 settings.json）
    target_settings = {
        "display_name": "目标目录用户设置",
        "forwarders": [{"name": "目标货代", "rate_rmb_per_kg": 999.0}],
    }
    (new_dir / "settings.json").write_text(
        json.dumps(target_settings, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (new_dir / "api_profiles.json").write_text('{"profiles": []}', encoding="utf-8")

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

    assert _location_target(tmp_path) == new_dir.resolve()
    # 目标目录已有 settings 绝对不得被覆盖
    content = json.loads((new_dir / "settings.json").read_text(encoding="utf-8"))
    assert content == target_settings
    assert (new_dir / "api_profiles.json").read_text(encoding="utf-8") == '{"profiles": []}'


def test_switch_to_current_directory_is_noop(tmp_path: Path, monkeypatch):
    import profit_accounting_26.ui.binders.main_window_binder as binder_module

    old_dir = tmp_path / "old"
    old_dir.mkdir()
    _install_location_json(tmp_path, monkeypatch, old_dir)
    before = _location_target(tmp_path)

    infos: list = []
    monkeypatch.setattr(
        binder_module.QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *_a, **_k: str(old_dir)),
    )
    monkeypatch.setattr(
        binder_module.QMessageBox,
        "information",
        staticmethod(lambda *_a, **_k: infos.append(_a)),
    )

    binder = MainWindowBinder(object(), _FakeContext(old_dir))
    binder.change_data_directory()

    assert _location_target(tmp_path) == before
    assert infos, "必须提示当前目录就是数据目录"
    assert "就是当前数据目录" in infos[0][2]
