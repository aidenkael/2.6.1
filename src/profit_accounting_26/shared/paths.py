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


# ---------------------------------------------------------------------------
# 数据目录生命周期（唯一权威：location.json）
#
# 规则：生产 UI 生命周期内，绑定数据目录的服务只有在目录仍是 location.json
# 指向的权威目录（或目录仍然存在，会话延续契约）时才允许创建目录/落盘。
# 用户切换数据目录并删除旧目录后，陈旧 AppContext/SettingsService 等
# 不得复活废弃目录。
# ---------------------------------------------------------------------------


class StaleDataDirectoryError(RuntimeError):
    """数据目录已被 location.json 抛弃且已不存在；拒绝重建以防止复活废弃目录。"""


_lifecycle_active = False


def activate_data_dir_lifecycle() -> None:
    """激活数据目录生命周期守卫（仅正式 UI 启动路径调用；测试/工具注入不激活）。"""
    global _lifecycle_active
    _lifecycle_active = True


def deactivate_data_dir_lifecycle() -> None:
    """关闭生命周期守卫（测试复位用；生产流程不调用）。"""
    global _lifecycle_active
    _lifecycle_active = False


def is_authoritative_data_dir(data_dir: str | Path) -> bool:
    """目录是否仍是 location.json 指向的权威数据目录。

    - 生命周期未激活（测试/工具显式注入）：不设限，返回 True；
    - location.json 不存在（首次运行）：不设限，返回 True；
    - 否则与 location.json 的 data_dir 做 resolved 比较。
    """
    if not _lifecycle_active:
        return True
    configured = ApplicationPaths.configured_data_dir()
    if configured is None:
        return True
    try:
        return (
            Path(data_dir).expanduser().resolve()
            == configured.expanduser().resolve()
        )
    except OSError:
        return False


def ensure_data_dir_allowed(data_dir: str | Path) -> None:
    """数据目录写入/建目录前的统一生命周期守卫。

    - 目录已存在 → 放行（“当前会话继续使用旧目录直到重启”的既有契约）；
    - 目录不存在且仍是权威数据目录（或未激活守卫）→ 放行（正常首次初始化）；
    - 目录不存在且已被 location.json 抛弃 → 抛 :class:`StaleDataDirectoryError`。
    """
    path = Path(data_dir)
    if path.is_dir() or is_authoritative_data_dir(path):
        return
    raise StaleDataDirectoryError(
        f"数据目录 {path} 已被 location.json 抛弃且不存在，拒绝重建；"
        "请重启软件以使用新的数据目录。"
    )


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
        ensure_data_dir_allowed(self.data_dir)
        for path in (
            self.data_dir,
            self.images_dir,
            self.exports_dir,
            self.calibration_packages_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
