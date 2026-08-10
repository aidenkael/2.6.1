"""数据目录切换时的用户配置同步（阶段 1）。

切换 data_dir 只同步“用户配置体系”，不复制历史数据库、不混合历史记录、
不复制大量历史图片：

- ``settings.json``：汇率 / 尾程 / 货代 / 利润规则 / 显示名 / 日志等；
- ``api_profiles.json`` + ``api_keys.local.json``：API 配置 / 绑定 / 私钥；
- ``calibration_packages/``：已导入与内置校准包文件；
- 校准版本注册表：仅当目标数据库全新（无历史、无注册表）时重建，
  保留版本列表与当前启用版本；否则跳过，绝不合并。

``location.json`` 仍只保存 data_dir 路径，不保存任何业务设置。
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from profit_accounting_26.storage import SQLiteStore


CONFIG_FILES = ("settings.json", "api_profiles.json", "api_keys.local.json")


@dataclass(slots=True)
class SyncSummary:
    copied_files: list[str] = field(default_factory=list)
    copied_package_files: int = 0
    calibration_registry_migrated: bool = False
    calibration_registry_skipped_reason: str | None = None


def _copy_file_if_exists(source: Path, target: Path, summary: SyncSummary, name: str) -> None:
    if not source.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    summary.copied_files.append(name)


def _copy_tree(source: Path, target: Path) -> int:
    """复制目录中的全部文件（保留相对结构），返回复制文件数。"""
    if not source.is_dir():
        return 0
    count = 0
    target.mkdir(parents=True, exist_ok=True)
    for item in source.rglob("*"):
        if not item.is_file():
            continue
        relative = item.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)
        count += 1
    return count


def _rewrite_package_path(path_value: str, source_data_dir: Path, target_data_dir: Path) -> str:
    """把注册表中的校准包路径改写为新 data_dir 下的相对路径。"""
    old_path = Path(path_value)
    for base in (Path(source_data_dir), Path(source_data_dir).resolve()):
        try:
            relative = old_path.relative_to(base)
            break
        except ValueError:
            continue
    else:
        return path_value
    return str(Path(target_data_dir) / relative)


def _migrate_calibration_registry(
    source_store: SQLiteStore | None,
    target_store: SQLiteStore | None,
    source_data_dir: Path,
    target_data_dir: Path,
    summary: SyncSummary,
) -> None:
    """把旧库的校准版本注册表重建到全新目标库（不复制历史记录）。"""
    if source_store is None or target_store is None:
        return
    packages = source_store.list_calibration_packages()
    if not packages:
        return
    # initialize 幂等：仅补建缺失表，不修改已有数据。
    target_store.initialize()
    if target_store.list_calibration_packages():
        summary.calibration_registry_skipped_reason = "目标数据库已有校准包，不合并"
        return
    if target_store.list_records(limit=1):
        summary.calibration_registry_skipped_reason = "目标数据库已有历史记录，不合并"
        return

    active_old_id = next((item["id"] for item in packages if item["active"]), None)
    migrated: list[tuple[str, str]] = []
    for package in packages:
        package_id = target_store.register_calibration_package(
            version=package["version"],
            path=_rewrite_package_path(package["path"], source_data_dir, target_data_dir),
            metadata=package["metadata"],
            activate=False,
        )
        migrated.append((package_id, package["id"]))
    if active_old_id is not None:
        for package_id, old_id in migrated:
            if old_id == active_old_id:
                target_store.activate_calibration(package_id)
                break
    summary.calibration_registry_migrated = True


def sync_user_config(
    source_data_dir: str | Path,
    target_data_dir: str | Path,
    *,
    source_store: SQLiteStore | None = None,
    target_store: SQLiteStore | None = None,
) -> SyncSummary:
    """把源 data_dir 的用户配置同步到目标 data_dir。

    - 两个目录相同或目标不存在时安全返回；
    - 只同步配置，不复制历史数据库和图片；
    - 校准注册表只在目标库全新时重建。
    """
    source = Path(source_data_dir).expanduser()
    target = Path(target_data_dir).expanduser()
    if source.resolve() == target.resolve():
        return SyncSummary()

    summary = SyncSummary()
    for name in CONFIG_FILES:
        _copy_file_if_exists(source / name, target / name, summary, name)
    summary.copied_package_files = _copy_tree(
        source / "calibration_packages",
        target / "calibration_packages",
    )
    _migrate_calibration_registry(
        source_store,
        target_store,
        source,
        target,
        summary,
    )
    return summary
