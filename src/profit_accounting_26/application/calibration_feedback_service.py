"""CalibrationFeedback V1 服务：用户/开发者校准反馈的保存与读取。

职责边界：只处理反馈数据。不修改记录、不触碰 CAL77、不做自动学习。

保存语义（本轮任务要求）：
- 只有一句文字反馈可保存；只有一个 ``can_compress`` 也可保存；
- 没有真实头程费用也可保存（缺失数据不阻止保存）；
- 实际头程为 0 是合法值（区别于 None/缺失）；
- 用户建议包装永远是 ``user_suggested``，绝不升级为 measured。

持久化复用现有 SQLite 连接机制，新增独立 ``calibration_feedback`` 表
（CREATE TABLE IF NOT EXISTS，不改动既有表结构）。
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from profit_accounting_26.application.data_contracts import CalibrationFeedback
from profit_accounting_26.storage.sqlite_store import SQLiteStore

_FEEDBACK_SCHEMA = """
CREATE TABLE IF NOT EXISTS calibration_feedback (
    feedback_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL,
    source TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _utc_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _serialize(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


class CalibrationFeedbackService:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def initialize(self) -> None:
        with self.store.connect() as connection:
            connection.executescript(_FEEDBACK_SCHEMA)

    # ------------------------------------------------------------ save

    def save(self, data: CalibrationFeedback | dict[str, Any], *, record_id: str | None = None) -> str:
        """保存一条反馈；缺失数据不阻止保存，空反馈与非法枚举才拒绝。"""
        if isinstance(data, dict):
            payload = dict(data)
            if record_id:
                payload.setdefault("record_id", record_id)
            payload.setdefault("feedback_id", str(uuid4()))
            feedback = CalibrationFeedback.from_dict(payload)
        else:
            feedback = data
        issues = feedback.validate()
        if issues:
            raise ValueError("反馈保存失败: " + "; ".join(issues))
        now = _utc_now_iso()
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT created_at, payload_json FROM calibration_feedback WHERE feedback_id = ?",
                (feedback.feedback_id,),
            ).fetchone()
            if row is None:
                feedback.created_at = feedback.created_at or now
                feedback.updated_at = now
                connection.execute(
                    """
                    INSERT INTO calibration_feedback(feedback_id, record_id, source,
                                                     payload_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (feedback.feedback_id, feedback.record_id, feedback.source,
                     _serialize(feedback.to_dict()), feedback.created_at, feedback.updated_at),
                )
            else:
                existing_payload = json.loads(row["payload_json"])
                feedback.created_at = row["created_at"]
                feedback.updated_at = now
                # 已导出过的反馈再次修改：只记录状态，不阻止保存/再次导出
                exported_before = bool(existing_payload.get("calibration_exported_at"))
                feedback.calibration_exported_at = existing_payload.get("calibration_exported_at")
                feedback.calibration_export_batch_id = existing_payload.get("calibration_export_batch_id")
                feedback.feedback_updated_after_export = (
                    exported_before
                    or bool(existing_payload.get("feedback_updated_after_export"))
                )
                connection.execute(
                    "UPDATE calibration_feedback SET record_id=?, source=?, payload_json=?, updated_at=? WHERE feedback_id=?",
                    (feedback.record_id, feedback.source, _serialize(feedback.to_dict()),
                     now, feedback.feedback_id),
                )
        return feedback.feedback_id

    # ------------------------------------------------------------ read

    def load(self, feedback_id: str) -> CalibrationFeedback:
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM calibration_feedback WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        if row is None:
            raise KeyError(feedback_id)
        return CalibrationFeedback.from_dict(json.loads(row["payload_json"]))

    def for_record(self, record_id: str) -> list[CalibrationFeedback]:
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM calibration_feedback WHERE record_id = ? ORDER BY updated_at DESC",
                (record_id,),
            ).fetchall()
        return [CalibrationFeedback.from_dict(json.loads(row["payload_json"])) for row in rows]

    def list_all(self) -> list[CalibrationFeedback]:
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM calibration_feedback ORDER BY updated_at DESC"
            ).fetchall()
        return [CalibrationFeedback.from_dict(json.loads(row["payload_json"])) for row in rows]

    # ------------------------------------------------------------ export status

    def mark_exported(self, feedback_ids: list[str], *, batch_id: str) -> None:
        """登记导出状态（只提供状态，不阻止用户再次导出）。"""
        now = _utc_now_iso()
        for feedback_id in feedback_ids:
            feedback = self.load(feedback_id)
            feedback.calibration_exported_at = now
            feedback.calibration_export_batch_id = batch_id
            with self.store.connect() as connection:
                connection.execute(
                    "UPDATE calibration_feedback SET payload_json=?, updated_at=? WHERE feedback_id=?",
                    (_serialize(feedback.to_dict()), now, feedback_id),
                )
