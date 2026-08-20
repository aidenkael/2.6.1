from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from profit_accounting_26._version import __version__

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "ProfitAccounting26"
RELEASE_ROOT = ROOT / "release"
VERSION = __version__


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        delivery_manifest = ROOT / "DELIVERY_MANIFEST.md"
        if delivery_manifest.is_file():
            match = re.search(
                r"^- delivery_commit:\s*`?([0-9a-f]{40})`?\s*$",
                delivery_manifest.read_text(encoding="utf-8"),
                flags=re.MULTILINE,
            )
            if match:
                return match.group(1)
        return "UNKNOWN_SOURCE_COMMIT"


def main() -> int:
    if not DIST.is_dir():
        raise SystemExit(f"Missing PyInstaller output: {DIST}")
    RELEASE_ROOT.mkdir(exist_ok=True)
    target = RELEASE_ROOT / f"Profit-Accounting-{VERSION}"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(DIST, target)
    for name in (
        "README.md",
        "RELEASE_NOTES_2.6.1.md",
        "Development rules-2.6.1.md",
        "SOURCE_PROVENANCE.md",
    ):
        source = ROOT / name
        if source.is_file():
            shutil.copy2(source, target / name)
    manifest = {
        "version": VERSION,
        "built_at": datetime.now(UTC).isoformat(),
        "source_commit": source_commit(),
        "logistics_source_commit": "ddad3b7486c2afc7de0b266defb3f5dd22028d00",
        "packaging_calibration": "runtime-safety-baseline-v1",
        "packaging_registry": "runtime-safety-empty-v1",
        "entry": "ProfitAccounting26.exe",
    }
    (target / "RELEASE_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    archive_base = RELEASE_ROOT / f"Profit-Accounting-{VERSION}_windows"
    zip_path = Path(shutil.make_archive(str(archive_base), "zip", target.parent, target.name))
    (RELEASE_ROOT / f"{zip_path.name}.sha256.txt").write_text(
        f"{sha256(zip_path)}  {zip_path.name}\n", encoding="utf-8"
    )
    print(zip_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
