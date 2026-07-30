from __future__ import annotations

import argparse
import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksums(root: Path) -> None:
    excluded = {".git", ".venv", ".venv-311", "__pycache__", ".pytest_cache", ".artifacts"}
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS.txt":
            continue
        if any(part in excluded for part in path.relative_to(root).parts):
            continue
        rows.append(f"{sha256(path)}  {path.relative_to(root).as_posix()}")
    (root / "SHA256SUMS.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pytest-output", type=Path, required=True)
    parser.add_argument("--scan-output", type=Path, required=True)
    parser.add_argument("--clean-clone", choices=["pending", "passed"], required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    pytest_text = args.pytest_output.read_text(encoding="utf-8", errors="replace").strip()
    scan_text = args.scan_output.read_text(encoding="utf-8", errors="replace").strip()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    files = sum(1 for path in root.rglob("*") if path.is_file() and ".git" not in path.parts)
    report = f"""# TEST_REPORT

- generated_at_utc: `{datetime.now(UTC).isoformat()}`
- repository: `aidenkael/Profit-Accounting-2.6`
- branch: `migration/r2-baseline`
- workflow_base_commit: `{commit}`
- R2 source_tag: `profit-legacy-freeze-20260728-r2`
- R2 source_commit: `d0c07d374c9ee61926de9cd3e01b8c35260c8e5c`
- tracked_file_count_before_report_commit: `{files}`
- clean_clone_verification: `{args.clean_clone}`

## Pytest

```text
{pytest_text}
```

目标：`0 failed`、`0 collection errors`。PySide6 已安装时执行离屏窗口烟测；未安装时只允许该环境测试跳过并必须在 pytest 摘要中可见。

## Sensitive scan

```text
{scan_text}
```

## Exclusions

未提交 `.venv`、缓存、构建产物、真实数据库、真实用户图片、Token、Cookie、API Key、浏览器 Profile、旧压缩包和 R2 外三份校准数据。
"""
    (root / "TEST_REPORT.md").write_text(report, encoding="utf-8")
    write_checksums(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
