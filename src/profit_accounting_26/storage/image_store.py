"""ImageStore V1：内容寻址图片存储（SHA256 去重 + 原图/缩略图分离）。

职责边界：只处理图片存储。不处理历史记录、反馈或导出。

设计约束（本轮任务）：
- 相同字节内容只保存一份 original（按 SHA256 去重）。
- 缩略图用于未来历史列表，原图用于预览/重新分析/校准，互不覆盖。
- 数据库只存引用（hash + 相对 storage key + metadata），绝不存二进制。
- storage key 一律使用相对路径（相对 data_dir），防止绝对路径泄露。
- 删除历史记录 ≠ 删除图片文件：第一版只做 ``is_referenced`` 查询，
  孤儿图片清理由未来的 orphan cleanup 单独处理。
- 缩略图生成失败（损坏图片等）安全降级：原图仍保存，thumbnail_key 为 None。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from profit_accounting_26.storage.sqlite_store import SQLiteStore

ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
THUMBNAIL_WIDTH = 240
THUMBNAIL_QUALITY = 80

_IMAGES_SCHEMA = """
CREATE TABLE IF NOT EXISTS images (
    image_id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE,
    original_filename TEXT,
    storage_key TEXT NOT NULL,
    thumbnail_key TEXT,
    bytes INTEGER,
    suffix TEXT,
    created_at TEXT NOT NULL
);
"""


@dataclass(frozen=True, slots=True)
class ImageReference:
    """历史记录里保存的图片引用（数据库不落二进制）。"""

    image_id: str
    image_hash: str
    original_filename: str
    storage_key: str
    thumbnail_key: str | None
    bytes: int
    suffix: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_id": self.image_id,
            "image_hash": self.image_hash,
            "original_filename": self.original_filename,
            "storage_key": self.storage_key,
            "thumbnail_key": self.thumbnail_key,
            "bytes": self.bytes,
            "suffix": self.suffix,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ImageReference":
        return cls(
            image_id=str(row["image_id"]),
            image_hash=str(row["sha256"]),
            original_filename=str(row["original_filename"] or ""),
            storage_key=str(row["storage_key"]),
            thumbnail_key=row["thumbnail_key"],
            bytes=int(row["bytes"] or 0),
            suffix=str(row["suffix"] or ""),
            created_at=str(row["created_at"]),
        )


class ImageStore:
    def __init__(self, store: SQLiteStore, data_dir: str | Path) -> None:
        self.store = store
        self.data_dir = Path(data_dir)
        self.originals_dir = self.data_dir / "images" / "originals"
        self.thumbnails_dir = self.data_dir / "images" / "thumbnails"

    # ------------------------------------------------------------ schema

    def initialize(self) -> None:
        with self.store.connect() as connection:
            connection.executescript(_IMAGES_SCHEMA)

    # ------------------------------------------------------------ add

    def add_file(self, path: str | Path, *, original_filename: str | None = None) -> ImageReference:
        file_path = Path(path)
        if not file_path.is_file():
            raise FileNotFoundError(file_path)
        suffix = file_path.suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise ValueError("不支持的图片格式")
        return self.add_bytes(
            file_path.read_bytes(),
            suffix=suffix,
            original_filename=original_filename or file_path.name,
        )

    def add_bytes(self, data: bytes, *, suffix: str = ".png",
                  original_filename: str | None = None) -> ImageReference:
        suffix = suffix.lower() if suffix.lower() in ALLOWED_SUFFIXES else ".png"
        digest = hashlib.sha256(data).hexdigest()
        existing = self.by_hash(digest)
        if existing is not None:
            return existing  # 相同字节内容只保存一份
        self.originals_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)
        original_key = self._write_original(data, digest, suffix)
        thumbnail_key = self._write_thumbnail(original_key, digest)
        reference = ImageReference(
            image_id=str(uuid4()),
            image_hash=digest,
            original_filename=str(original_filename or ""),
            storage_key=original_key,
            thumbnail_key=thumbnail_key,
            bytes=len(data),
            suffix=suffix,
            created_at=_utc_now_iso(),
        )
        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT INTO images(image_id, sha256, original_filename, storage_key,
                                   thumbnail_key, bytes, suffix, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (reference.image_id, reference.image_hash, reference.original_filename,
                 reference.storage_key, reference.thumbnail_key, reference.bytes,
                 reference.suffix, reference.created_at),
            )
        return reference

    def _write_original(self, data: bytes, digest: str, suffix: str) -> str:
        relative = Path("images") / "originals" / digest[:2] / f"{digest}{suffix}"
        target = self.data_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
        return relative.as_posix()

    def _write_thumbnail(self, original_key: str, digest: str) -> str | None:
        """生成缩略图；失败时安全返回 None，绝不影响原图保存。"""
        try:
            from PySide6.QtCore import QSize
            from PySide6.QtGui import QImage
            from PySide6.QtCore import Qt
        except ImportError:
            return None
        try:
            source = QImage(str(self.data_dir / original_key))
            if source.isNull():
                return None
            scaled = source.scaled(
                QSize(THUMBNAIL_WIDTH, THUMBNAIL_WIDTH),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            relative = Path("images") / "thumbnails" / digest[:2] / f"{digest}.jpg"
            target = self.data_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if not scaled.save(str(target), "JPG", THUMBNAIL_QUALITY):
                return None
            return relative.as_posix()
        except Exception:  # noqa: BLE001 - 缩略图失败不得阻断原图入库
            return None

    # ------------------------------------------------------------ query

    def by_hash(self, digest: str) -> ImageReference | None:
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT * FROM images WHERE sha256 = ?", (digest,)
            ).fetchone()
        return ImageReference.from_row(dict(row)) if row is not None else None

    def get(self, image_id: str) -> ImageReference | None:
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT * FROM images WHERE image_id = ?", (image_id,)
            ).fetchone()
        return ImageReference.from_row(dict(row)) if row is not None else None

    def list_all(self) -> list[ImageReference]:
        with self.store.connect() as connection:
            rows = connection.execute("SELECT * FROM images ORDER BY created_at").fetchall()
        return [ImageReference.from_row(dict(row)) for row in rows]

    def original_path(self, reference: ImageReference) -> Path:
        return self.data_dir / reference.storage_key

    def thumbnail_path(self, reference: ImageReference) -> Path | None:
        if not reference.thumbnail_key:
            return None
        return self.data_dir / reference.thumbnail_key

    # ------------------------------------------------------------ safety

    def is_referenced(self, image_id: str) -> bool:
        """任何历史记录的 images 引用了该图片（按 image_id 或 sha256 匹配）。

        第一版仅查询，不物理删除：删除历史记录 ≠ 删除图片文件。
        """
        reference = self.get(image_id)
        if reference is None:
            return False
        markers = {reference.image_id, reference.image_hash, reference.storage_key}
        for record in self.store.export_records():
            images = record.get("images")
            if not isinstance(images, list):
                continue
            for item in images:
                if not isinstance(item, dict):
                    continue
                values = {item.get("image_id"), item.get("sha256"),
                          item.get("storage_key"), item.get("relative_path")}
                if markers & {value for value in values if value}:
                    return True
        return False


def _utc_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
