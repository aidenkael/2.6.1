"""Sanitization helpers for importing diagnostic records into evaluation data.

Used by ``tools/import_vision_diagnostic_case.py``. Real evaluation data must
never carry API keys, Authorization headers, base64 image payloads or full
local paths (which embed Windows user names) into case files.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

FORBIDDEN_KEY_NAMES = {
    "authorization", "auth", "api_key", "apikey", "api-key", "x-api-key",
    "key", "token", "access_token", "secret", "cookie", "password", "bearer",
}

SECRET_PATTERNS = {
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    "OpenAI key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "Bearer header": re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{16,}"),
}

_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/].+$")
_POSIX_PATH = re.compile(r"^(?:~|/).+$")


def _looks_like_path(value: str) -> bool:
    return bool(_WINDOWS_PATH.fullmatch(value) or _POSIX_PATH.fullmatch(value))


def _basename(value: str) -> str:
    for pure in (PureWindowsPath, PurePosixPath):
        name = pure(value).name
        if name:
            return name
    return value


def sanitize_value(value: Any) -> Any:
    """Recursively strip secrets, data URLs and local-path details."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_KEY_NAMES:
                continue
            cleaned[str(key)] = sanitize_value(item)
        return cleaned
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, str):
        if value.startswith("data:"):
            return "[image base64 omitted]"
        if _looks_like_path(value):
            return _basename(value)
        return value
    return value


def scan_for_secrets(text: str) -> list[str]:
    """Return the names of secret patterns found in already-sanitized text."""
    return [name for name, pattern in SECRET_PATTERNS.items() if pattern.search(text)]


def anonymize_image_metadata(images: Any) -> list[dict[str, Any]]:
    """Keep only basename, sha256, size and mime from DiagnosticLogger metadata."""
    result: list[dict[str, Any]] = []
    if not isinstance(images, list):
        return result
    for item in images:
        if not isinstance(item, dict):
            continue
        entry: dict[str, Any] = {"image_role": "unknown"}
        raw_path = str(item.get("path") or "")
        if raw_path:
            entry["file"] = _basename(raw_path)
        for key in ("sha256", "bytes", "mime_type", "width", "height"):
            if item.get(key) is not None:
                entry[key] = item[key]
        result.append(entry)
    return result
