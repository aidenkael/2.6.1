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


def test_environment_data_directory_has_priority(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        ApplicationPaths,
        "location_config_path",
        classmethod(lambda _cls: tmp_path / "home" / "location.json"),
    )
    ApplicationPaths.save_data_dir(tmp_path / "configured")
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path / "environment"))
    assert ApplicationPaths.default().data_dir == tmp_path / "environment"
