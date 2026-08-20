"""校准资源内容 ↔ 版本号一致性守护测试。

当内置校准关键资源（baseline / registry）的文件内容发生变化时，
对应的版本常量（CURRENT_BASELINE_VERSION）必须同步递增。
如果开发者修改了资源文件但忘记升级版本号，本测试明确失败并提醒。

维护说明：
    当校准资源内容变更且版本已递增后，同步更新下方 _KNOWN_GOOD 中的
    SHA-256 值为错误信息中显示的 new hash。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from profit_accounting_26.application.calibration_baseline import (
    CURRENT_BASELINE_VERSION,
    CURRENT_REGISTRY_RESOURCE,
    CURRENT_BASELINE_RESOURCE,
)
from profit_accounting_26.shared.paths import resource_root

# ── 已知的"版本 ↔ 内容"快照 ──────────────────────────────────────
# 每次 CURRENT_BASELINE_VERSION 递增时，同步更新此处哈希值。
# 格式：{version_string: (baseline_sha256, registry_sha256)}
_KNOWN_GOOD: dict[str, tuple[str, str]] = {
    "runtime-safety-baseline-v1": (
        "27ed55ed526b02dd2962506e7748ac1c11d86eeeae1b8026fdef17701560fe80",
        "8b04e1b2b11888c70f3f88ea3246932f31db98824615fa504d2ab6f5ba9da241",
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_builtin_calibration_content_matches_version() -> None:
    """内置 baseline 内容变化时，CURRENT_BASELINE_VERSION 必须递增。"""
    root = resource_root()
    baseline_hash = _sha256(root / CURRENT_BASELINE_RESOURCE)
    registry_hash = _sha256(root / CURRENT_REGISTRY_RESOURCE)

    known = _KNOWN_GOOD.get(CURRENT_BASELINE_VERSION)

    if known is not None and known == (baseline_hash, registry_hash):
        return  # 内容与版本均无变化 ✓

    if known is not None:
        # 版本未变但内容已改 —— 开发者忘记递增版本号
        pytest.fail(
            f"内置校准资源内容已变化，但 CURRENT_BASELINE_VERSION "
            f"({CURRENT_BASELINE_VERSION!r}) 未递增！\n"
            f"  baseline old={known[0]}\n"
            f"  baseline new={baseline_hash}\n"
            f"  registry old={known[1]}\n"
            f"  registry new={registry_hash}\n"
            f"请递增 CURRENT_BASELINE_VERSION 后，"
            f"将新哈希更新到本测试的 _KNOWN_GOOD 中。"
        )

    # 新版本号不在 _KNOWN_GOOD 中 —— 确认是有效递增（内容确实不同）
    all_hashes = set()
    for b, r in _KNOWN_GOOD.values():
        all_hashes.add(b)
        all_hashes.add(r)
    if baseline_hash in all_hashes or registry_hash in all_hashes:
        pytest.fail(
            f"CURRENT_BASELINE_VERSION 已变更但资源内容未更新，"
            f"请确认版本号与资源文件同步。"
        )
    # 版本递增且内容确实不同 ✓（开发者需要更新 _KNOWN_GOOD）
    pytest.fail(
        f"CURRENT_BASELINE_VERSION 已递增到 {CURRENT_BASELINE_VERSION!r}，"
        f"请将以下新哈希更新到测试文件 _KNOWN_GOOD 中：\n"
        f"  baseline={baseline_hash}\n"
        f"  registry={registry_hash}"
    )
