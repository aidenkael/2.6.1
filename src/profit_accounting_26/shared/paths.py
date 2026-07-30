from __future__ import annotations

import os
import json
import sys
from dataclasses import dataclass
from pathlib import Path


def resource_root() -> Path:
    """Return the project/resource root for source and PyInstaller builds."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[3]


def resource_path(relative: str | Path) -> Path:
    return resource_root() / Path(relative)


@dataclass(frozen=True, slots=True)
class ApplicationPaths:
    data_dir: Path
    database_path: Path
    settings_path: Path
    images_dir: Path
    exports_dir: Path
    calibration_packages_dir: Path

    @classmethod
    def location_config_path(cls) -> Path:
        return Path.home() / ".profit_accounting_26" / "location.json"

    @classmethod
    def configured_data_dir(cls) -> Path | None:
        config = cls.location_config_path()
        if not config.is_file():
            return None
        try:
            payload = json.loads(config.read_text(encoding="utf-8"))
            value = str(payload.get("data_dir") or "").strip()
            return Path(value).expanduser() if value else None
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
            return None

    @classmethod
    def save_data_dir(cls, path: str | Path) -> Path:
        target = Path(path).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        config = cls.location_config_path()
        config.parent.mkdir(parents=True, exist_ok=True)
        temp = config.with_suffix(".tmp")
        temp.write_text(
            json.dumps({"data_dir": str(target)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp.replace(config)
        return target

    @classmethod
    def default(cls) -> "ApplicationPaths":
        override = os.environ.get("PROFIT_ACCOUNTING_DATA_DIR")
        configured = cls.configured_data_dir()
        base = (
            Path(override).expanduser()
            if override
            else configured or Path.home() / "ProfitAccounting26Data"
        )
        return cls(
            data_dir=base,
            database_path=base / "profit_accounting_26.sqlite3",
            settings_path=base / "settings.json",
            images_dir=base / "images",
            exports_dir=base / "exports",
            calibration_packages_dir=base / "calibration_packages",
        )

    def ensure(self) -> None:
        for path in (
            self.data_dir,
            self.images_dir,
            self.exports_dir,
            self.calibration_packages_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
