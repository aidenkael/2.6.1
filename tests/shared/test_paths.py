from pathlib import Path

from profit_accounting_26.shared import ApplicationPaths


def test_persisted_data_directory_is_used_when_environment_is_absent(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        ApplicationPaths,
        "location_config_path",
        classmethod(lambda _cls: tmp_path / "home" / "location.json"),
    )
    monkeypatch.delenv("PROFIT_ACCOUNTING_DATA_DIR", raising=False)
    selected = tmp_path / "selected-data"
    saved = ApplicationPaths.save_data_dir(selected)
    paths = ApplicationPaths.default()
    assert saved == selected.resolve()
    assert paths.data_dir == selected.resolve()


def test_environment_data_directory_has_priority_for_non_ui_callers(tmp_path: Path, monkeypatch):
    """default() 保留测试/工具注入通道：环境变量优先于 location.json。"""
    monkeypatch.setattr(
        ApplicationPaths,
        "location_config_path",
        classmethod(lambda _cls: tmp_path / "home" / "location.json"),
    )
    ApplicationPaths.save_data_dir(tmp_path / "configured")
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path / "environment"))
    assert ApplicationPaths.default().data_dir == tmp_path / "environment"


def test_ui_default_uses_configured_location_and_ignores_environment(tmp_path: Path, monkeypatch):
    """正式 UI 启动：location.json 是唯一权威，环境变量不得覆盖用户选择。"""
    monkeypatch.setattr(
        ApplicationPaths,
        "location_config_path",
        classmethod(lambda _cls: tmp_path / "home" / "location.json"),
    )
    configured = tmp_path / "configured"
    ApplicationPaths.save_data_dir(configured)
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path / "environment"))
    paths = ApplicationPaths.ui_default()
    assert paths is not None
    assert paths.data_dir == configured.resolve()


def test_ui_default_returns_none_without_location_file(tmp_path: Path, monkeypatch):
    """首次运行：无 location.json 时必须返回 None，由 UI 引导选择，禁止静默回退默认目录。"""
    monkeypatch.setattr(
        ApplicationPaths,
        "location_config_path",
        classmethod(lambda _cls: tmp_path / "home" / "location.json"),
    )
    monkeypatch.delenv("PROFIT_ACCOUNTING_DATA_DIR", raising=False)
    assert ApplicationPaths.ui_default() is None


def test_ui_default_ignores_environment_when_no_location(tmp_path: Path, monkeypatch):
    """首次运行即使存在环境变量也必须由用户选择目录（UI 不读环境变量）。"""
    monkeypatch.setattr(
        ApplicationPaths,
        "location_config_path",
        classmethod(lambda _cls: tmp_path / "home" / "location.json"),
    )
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path / "environment"))
    assert ApplicationPaths.ui_default() is None
