"""ImageStore V1 测试：SHA256 去重、缩略图、原图不被修改、缺失安全、引用查询。"""

from __future__ import annotations

from pathlib import Path

import pytest

from profit_accounting_26.storage import SQLiteStore
from profit_accounting_26.storage.image_store import ImageReference, ImageStore


@pytest.fixture()
def store(tmp_path: Path):
    sqlite = SQLiteStore(tmp_path / "app.sqlite3")
    sqlite.initialize()
    image_store = ImageStore(sqlite, tmp_path)
    image_store.initialize()
    return image_store


def _write_png(path: Path, *, size: int = 16, color=(200, 30, 30), qapp=None) -> Path:
    from PySide6.QtGui import QColor, QImage

    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(QColor(*color))
    assert image.save(str(path), "PNG")
    return path


def test_same_bytes_stored_once(qapp, store, tmp_path: Path):
    source = _write_png(tmp_path / "a.png")
    first = store.add_file(source)
    second = store.add_file(source)
    third = store.add_bytes(source.read_bytes(), suffix=".png")
    assert first.image_hash == second.image_hash == third.image_hash
    assert first.image_id == second.image_id == third.image_id
    originals = list((tmp_path / "images" / "originals").rglob("*"))
    originals = [item for item in originals if item.is_file()]
    assert len(originals) == 1
    assert len(store.list_all()) == 1


def test_different_images_get_different_hashes(qapp, store, tmp_path: Path):
    red = store.add_file(_write_png(tmp_path / "red.png", color=(255, 0, 0)))
    blue = store.add_file(_write_png(tmp_path / "blue.png", color=(0, 0, 255)))
    assert red.image_hash != blue.image_hash
    assert red.image_id != blue.image_id
    assert len(store.list_all()) == 2


def test_thumbnail_generated_and_original_untouched(qapp, store, tmp_path: Path):
    source = _write_png(tmp_path / "big.png", size=600)
    before = source.read_bytes()
    reference = store.add_file(source)
    assert reference.thumbnail_key is not None
    thumbnail_path = store.thumbnail_path(reference)
    assert thumbnail_path is not None and thumbnail_path.is_file()
    assert thumbnail_path.suffix == ".jpg"
    # 缩略图宽度不超过限制
    from PySide6.QtGui import QImage

    thumbnail = QImage(str(thumbnail_path))
    assert 0 < thumbnail.width() <= 240
    # 原图完整保留且未被修改
    original_path = store.original_path(reference)
    assert original_path.is_file()
    assert original_path.read_bytes() == before
    assert original_path != thumbnail_path


def test_missing_file_and_bad_extension_fail_safely(qapp, store, tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        store.add_file(tmp_path / "不存在.png")
    text_file = tmp_path / "note.txt"
    text_file.write_text("不是图片")
    with pytest.raises(ValueError):
        store.add_file(text_file)


def test_corrupt_image_keeps_original_without_thumbnail(qapp, store):
    reference = store.add_bytes(b"not-a-real-png-byte-content", suffix=".png")
    assert store.original_path(reference).is_file()
    assert reference.thumbnail_key is None
    assert store.thumbnail_path(reference) is None


def test_storage_keys_are_relative_paths(qapp, store, tmp_path: Path):
    reference = store.add_file(_write_png(tmp_path / "x.png"))
    assert reference.storage_key.startswith("images/originals/")
    assert ":" not in reference.storage_key
    assert not reference.storage_key.startswith(("/", "\\"))
    assert reference.thumbnail_key.startswith("images/thumbnails/")


def test_is_referenced_matches_record_images(qapp, store, tmp_path: Path):
    reference = store.add_file(_write_png(tmp_path / "ref.png"))
    assert store.is_referenced(reference.image_id) is False
    store.store.save_new_record({
        "product_name": "商品",
        "images": [{"image_id": reference.image_id, "sha256": reference.image_hash,
                      "storage_key": reference.storage_key}],
    })
    assert store.is_referenced(reference.image_id) is True
    # 旧格式（relative_path + sha256）也能匹配
    other = store.add_bytes(b"another-payload", suffix=".png")
    store.store.save_new_record({
        "product_name": "旧商品",
        "images": [{"relative_path": "images/legacy/x.png", "sha256": other.image_hash}],
    })
    assert store.is_referenced(other.image_id) is True
    assert store.is_referenced("不存在的id") is False


def test_reference_serialization_roundtrip(qapp, store, tmp_path: Path):
    reference = store.add_file(_write_png(tmp_path / "round.png"))
    restored = ImageReference.from_row({**reference.to_dict(), "sha256": reference.image_hash,
                                         "image_id": reference.image_id})
    assert restored == reference
    assert store.get(reference.image_id) == reference
    assert store.by_hash(reference.image_hash) == reference
