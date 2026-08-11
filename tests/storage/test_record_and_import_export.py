from __future__ import annotations

from pathlib import Path

from profit_accounting_26.application import RecordService
from profit_accounting_26.application.image_session import SessionImage
from profit_accounting_26.domain.models import ImageType
from profit_accounting_26.shared import ApplicationPaths
from profit_accounting_26.storage import SQLiteStore


def make_paths(tmp_path: Path) -> ApplicationPaths:
    return ApplicationPaths(
        data_dir=tmp_path,
        database_path=tmp_path / "app.sqlite3",
        settings_path=tmp_path / "settings.json",
        images_dir=tmp_path / "images",
        exports_dir=tmp_path / "exports",
        calibration_packages_dir=tmp_path / "calibration_packages",
    )


def test_record_service_persists_image_without_moving_source(tmp_path: Path):
    paths = make_paths(tmp_path / "data")
    paths.ensure()
    store = SQLiteStore(paths.database_path)
    store.initialize()
    source = tmp_path / "source.png"
    source.write_bytes(b"image")
    image = SessionImage(source, ImageType.MAIN, "a" * 64, source.name)
    service = RecordService(store, paths)
    record_id = service.save({"product_name": "sample"}, images=[image])
    record = service.load(record_id)
    assert source.exists()
    saved = paths.data_dir / record["images"][0]["relative_path"]
    assert saved.exists()
    assert record["images"][0]["original_name"] == "source.png"
