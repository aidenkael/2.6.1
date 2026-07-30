from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path

from profit_accounting_26.domain.models import ImageType


_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


@dataclass(frozen=True, slots=True)
class SessionImage:
    path: Path
    image_type: ImageType
    sha256: str
    original_name: str


class ImageSession:
    def __init__(self, slot_count: int = 5) -> None:
        self._validate_slot_count(slot_count)
        self.slot_count = slot_count
        self.images: list[SessionImage] = []
        self.dirty = False

    @staticmethod
    def _validate_slot_count(value: int) -> None:
        if not 3 <= value <= 6:
            raise ValueError("图片框数量必须在 3 到 6 之间")

    def set_slot_count(self, value: int) -> None:
        self._validate_slot_count(value)
        if value < len(self.images):
            raise ValueError("减少图片框前必须先移除超出数量的图片")
        self.slot_count = value
        self.dirty = True

    @staticmethod
    def _from_path(path: str | Path, image_type: ImageType) -> SessionImage:
        file_path = Path(path)
        if not file_path.is_file():
            raise FileNotFoundError(file_path)
        if file_path.suffix.lower() not in _ALLOWED_EXTENSIONS:
            raise ValueError("不支持的图片格式")
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        return SessionImage(file_path, image_type, digest, file_path.name)

    def add_path(self, path: str | Path, image_type: ImageType) -> SessionImage:
        if len(self.images) >= self.slot_count:
            raise ValueError("当前图片框已满")
        item = self._from_path(path, image_type)
        self.images.append(item)
        self.dirty = True
        return item

    def replace(self, index: int, path: str | Path, image_type: ImageType) -> SessionImage:
        item = self._from_path(path, image_type)
        if index < len(self.images):
            self.images[index] = item
        elif index == len(self.images) and len(self.images) < self.slot_count:
            self.images.append(item)
        else:
            raise IndexError(index)
        self.dirty = True
        return item

    def add_bytes(self, data: bytes, image_type: ImageType, *, suffix: str = ".png") -> SessionImage:
        if suffix.lower() not in _ALLOWED_EXTENSIONS:
            suffix = ".png"
        temp_dir = Path(tempfile.gettempdir()) / "profit_accounting_26_clipboard"
        temp_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(data).hexdigest()
        path = temp_dir / f"clipboard_{digest[:16]}{suffix}"
        if not path.exists():
            path.write_bytes(data)
        return self.add_path(path, image_type)

    def remove(self, index: int) -> SessionImage:
        item = self.images.pop(index)
        self.dirty = True
        return item

    def clear(self) -> None:
        self.images.clear()
        self.dirty = False
