from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".venv-311",
    ".venv-build",
    "__pycache__",
    ".pytest_cache",
    "build",
    "dist",
    "release",
}
TEXT_SUFFIXES = {".py", ".md", ".json", ".toml", ".txt", ".yml", ".yaml", ".bat"}
PATTERNS = {
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    "OpenAI key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "Cookie header": re.compile(r"(?i)cookie\s*:\s*[^\s]+"),
}
FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pem", ".key", ".zip"}


def _get_gitignored_files() -> set[Path]:
    """返回被 .gitignore 忽略的文件集合（仅检测已知 forbidden 后缀）。"""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--others", "--ignored", "--exclude-standard"],
            capture_output=True, text=True, cwd=ROOT, timeout=10,
        )
        if result.returncode != 0:
            return set()
        return {ROOT / line.strip() for line in result.stdout.splitlines() if line.strip()}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return set()


def main() -> int:
    gitignored = _get_gitignored_files()
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        # 跳过 .gitignore 已排除的文件（不会被 git 跟踪）
        if path in gitignored:
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            findings.append(f"forbidden file: {path.relative_to(ROOT)}")
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{name}: {path.relative_to(ROOT)}")
    if findings:
        print("Sensitive scan failed:")
        print("\n".join(f"- {item}" for item in findings))
        return 1
    print("Sensitive scan passed: 0 findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
