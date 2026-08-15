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
    def from_data_dir(cls, base: str | Path) -> "ApplicationPaths":
        """由数据目录构造全部子路径（settings / sqlite / images / exports / calibration）。"""
        base = Path(base)
        return cls(
            data_dir=base,
            database_path=base / "profit_accounting_26.sqlite3",
            settings_path=base / "settings.json",
            images_dir=base / "images",
            exports_dir=base / "exports",
            calibration_packages_dir=base / "calibration_packages",
        )

    @classmethod
    def default(cls) -> "ApplicationPaths":
        """开发/测试/工具注入通道：PROFIT_ACCOUNTING_DATA_DIR > location.json > 默认目录。

        正式桌面 UI 启动必须走 :meth:`ui_default`，避免环境变量悄悄覆盖用户
        在 location.json 中明确选择的数据目录。
        """
        override = os.environ.get("PROFIT_ACCOUNTING_DATA_DIR")
        configured = cls.configured_data_dir()
        base = (
            Path(override).expanduser()
            if override
            else configured or Path.home() / "ProfitAccounting26Data"
        )
        return cls.from_data_dir(base)

    @classmethod
    def ui_default(cls) -> "ApplicationPaths | None":
        """正式桌面 UI 启动目录：location.json 已存在时它是唯一权威（忽略环境变量）。

        返回 ``None`` 表示首次运行——调用方必须在创建 AppContext 之前
        引导用户选择数据目录并调用 :meth:`save_data_dir`。
        """
        configured = cls.configured_data_dir()
        if configured is None:
            return None
        return cls.from_data_dir(configured)

    def ensure(self) -> None:
        for path in (
            self.data_dir,
            self.images_dir,
            self.exports_dir,
            self.calibration_packages_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
