from pathlib import Path

import pytest

from profit_accounting_26.application import ImageSession
from profit_accounting_26.domain.models import ImageType


def test_image_types_are_exactly_three():
    assert {item.value for item in ImageType} == {"主图", "商品信息", "尺寸/重量"}


def test_add_hash_remove_and_clear(tmp_path: Path):
    image = tmp_path / "sample.png"
    image.write_bytes(b"fake-png-content")
    session = ImageSession()
    item = session.add_path(image, ImageType.MAIN)
    assert len(item.sha256) == 64
    assert item.original_name == "sample.png"
    assert session.dirty
    assert session.remove(0) == item
    session.clear()
    assert not session.dirty


def test_slot_count_bounds_and_capacity(tmp_path: Path):
    with pytest.raises(ValueError):
        ImageSession(2)
    session = ImageSession(3)
    for index in range(3):
        path = tmp_path / f"{index}.jpg"
        path.write_bytes(str(index).encode())
        session.add_path(path, ImageType.PRODUCT_INFO)
    extra = tmp_path / "extra.jpg"
    extra.write_bytes(b"extra")
    with pytest.raises(ValueError):
        session.add_path(extra, ImageType.MAIN)
