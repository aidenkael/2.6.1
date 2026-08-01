from __future__ import annotations

import hashlib
import json
import traceback
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4


class DiagnosticLogger:
    """Best-effort structured diagnostics; logging never interrupts business flow."""

    def __init__(self, data_dir: str | Path, settings: dict) -> None:
        self.root = Path(data_dir) / "logs"
        self.session_id = uuid4().hex
        self.level = str(settings.get("log_level") or "INFO").upper()
        self.retention_days = max(1, int(settings.get("log_retention_days", 30) or 30))
        self._prepare()
        self.event("app_started", data_dir=str(Path(data_dir)), session_id=self.session_id)

    def _prepare(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)
            for path in self.root.glob("*.json*"):
                if datetime.fromtimestamp(path.stat().st_mtime, UTC) < cutoff:
                    path.unlink(missing_ok=True)
        except OSError:
            pass

    @property
    def event_path(self) -> Path:
        return self.root / f"events-{datetime.now():%Y-%m-%d}.jsonl"

    def event(self, event: str, **payload) -> None:
        try:
            row = {"timestamp": datetime.now(UTC).isoformat(), "session_id": self.session_id, "event": event, **payload}
            with self.event_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass

    def exception(self, event: str, exc: BaseException, **payload) -> None:
        self.event(event, error=str(exc), traceback="".join(traceback.format_exception(exc)), **payload)

    @staticmethod
    def image_metadata(path: str | Path) -> dict:
        target = Path(path)
        try:
            data = target.read_bytes()
            return {"path": str(target), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        except OSError:
            return {"path": str(target), "unreadable": True}

    def ai_artifact(self, kind: str, payload: dict) -> None:
        """Write an AI artifact after recursively removing credentials and image base64."""
        def clean(value):
            if isinstance(value, dict):
                return {str(k): clean(v) for k, v in value.items() if str(k).lower() not in {"authorization", "api_key", "key"}}
            if isinstance(value, list):
                return [clean(item) for item in value]
            if isinstance(value, str) and value.startswith("data:image/"):
                return "[image base64 omitted]"
            return value
        try:
            path = self.root / f"ai-{kind}-{datetime.now():%Y%m%d-%H%M%S-%f}.json"
            path.write_text(json.dumps(clean(payload), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        except OSError:
            pass

    def diagnostic_summary(self, **payload) -> None:
        try:
            (self.root / "diagnostic_summary.json").write_text(json.dumps({"session_id": self.session_id, **payload}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        except OSError:
            pass
