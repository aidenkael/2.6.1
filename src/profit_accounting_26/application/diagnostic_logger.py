from __future__ import annotations

import hashlib, json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4


class DiagnosticOperation:
    def __init__(self, root: Path, session_id: str, operation_type: str) -> None:
        self.session_id, self.operation_id, self.operation_type = session_id, uuid4().hex, operation_type
        self.started_at = datetime.now(UTC)
        self.root = root / f"{self.started_at:%Y%m%d-%H%M%S}_{operation_type}_{self.operation_id[:8]}"
        try:
            self.root.mkdir(parents=True, exist_ok=False)
            for name in ("events.jsonl", "ai-request.json", "ai-response.json", "diagnostic_summary.json"):
                self._atomic(name, {})
            self.event("operation_created")
        except OSError: pass

    def _atomic(self, name: str, data: dict) -> None:
        try:
            path=self.root/name; tmp=path.with_suffix(path.suffix+".tmp")
            tmp.write_text(json.dumps(_sanitize(data), ensure_ascii=False, indent=2, default=str), encoding="utf-8"); tmp.replace(path)
        except OSError: pass

    def event(self, event: str, **data) -> None:
        try:
            row={"timestamp":datetime.now(UTC).isoformat(),"session_id":self.session_id,"operation_id":self.operation_id,"event":event,**_sanitize(data)}
            with (self.root/"events.jsonl").open("a",encoding="utf-8") as out: out.write(json.dumps(row,ensure_ascii=False,default=str)+"\n")
        except OSError: pass

    def request(self, **data) -> None: self._atomic("ai-request.json", {"session_id":self.session_id,"operation_id":self.operation_id,"operation_type":self.operation_type,**data})
    def response(self, **data) -> None: self._atomic("ai-response.json", {"session_id":self.session_id,"operation_id":self.operation_id,**data})
    def summary(self, **data) -> None: self._atomic("diagnostic_summary.json", {"session_id":self.session_id,"operation_id":self.operation_id,"operation_type":self.operation_type,**data})

def _sanitize(value):
    if isinstance(value, dict): return {str(k):_sanitize(v) for k,v in value.items() if str(k).lower() not in {"authorization","api_key","key","cookie"}}
    if isinstance(value, list): return [_sanitize(v) for v in value]
    if isinstance(value, str) and value.startswith("data:image/"): return "[image base64 omitted]"
    return value

class DiagnosticLogger:
    def __init__(self, data_dir: str|Path, settings: dict) -> None:
        self.root=Path(data_dir)/"logs"; self.session_id=uuid4().hex; self.retention_days=max(1,int(settings.get("log_retention_days",30) or 30)); self._prepare()
    def _prepare(self) -> None:
        try:
            self.root.mkdir(parents=True,exist_ok=True); cutoff=datetime.now(UTC)-timedelta(days=self.retention_days)
            for child in self.root.iterdir():
                if child.is_dir() and datetime.fromtimestamp(child.stat().st_mtime,UTC)<cutoff:
                    for item in child.iterdir(): item.unlink(missing_ok=True)
                    child.rmdir()
        except OSError: pass
    def begin_operation(self, operation_type: str) -> DiagnosticOperation: return DiagnosticOperation(self.root,self.session_id,operation_type)
    def event(self, *_args, **_kwargs) -> None:
        """Compatibility no-op: diagnostics are stored only in operation folders."""
        return None
    @staticmethod
    def image_metadata(path: str|Path) -> dict:
        target=Path(path)
        try:
            data=target.read_bytes(); meta={"path":str(target),"sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data),"mime_type":target.suffix.lower()}
            try:
                from PySide6.QtGui import QImage
                image=QImage(str(target)); meta.update({"width":image.width(),"height":image.height()})
            except Exception: pass
            return meta
        except OSError: return {"path":str(target),"unreadable":True}
