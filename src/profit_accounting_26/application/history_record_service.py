"""HistoryRecord V2 后端：create / update same record / revision / ai_initial 不可变。

职责边界：只处理历史记录的 V2 数据语义，不接 UI、不改 RecordService、
不改利润/包装/AI 生产逻辑。持久化复用现有 SQLite ``records`` 表：
V2 专属字段写入 payload 的 ``_v2`` 附加块，旧字段原样保留，
旧历史记录继续可读（V2 新字段默认 null）。

修改语义（本轮任务第十四节）：
- 新测算（record_id 不存在）→ create，revision=1，origin=new_calculation；
- 历史恢复后保存（record_id 存在）→ update 同一条记录，revision+1，
  origin=history_edit；绝不每次修改都生成新记录；
- ``ai_initial`` 只在首次 create 时写入，之后任何更新都不覆盖。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from profit_accounting_26.application.data_contracts import (
    RECORD_ORIGINS,
    RECORD_SCHEMA_VERSION,
    HistoryRecordV2,
    attach_v2_block,
    record_from_payload,
    v2_block_from_payload,
)
from profit_accounting_26.storage.sqlite_store import SQLiteStore


class HistoryRecordV2Service:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    # ------------------------------------------------------------ create

    def create_record(
        self,
        payload: dict[str, Any],
        *,
        ai_initial: dict[str, Any] | None,
        current_estimate: dict[str, Any] | None = None,
        record_id: str | None = None,
        sku: str | None = None,
        quantity: int | None = None,
    ) -> str:
        """新测算首次保存：写入 ai_initial（AI 第一次判断，此后不可覆盖）。"""
        identifier = str(record_id or payload.get("id") or uuid4())
        if self.store.record_exists(identifier):
            raise ValueError(f"记录已存在，不能重复 create: {identifier}")
        final_payload = dict(payload)
        attach_v2_block(
            final_payload,
            origin="new_calculation",
            revision=1,
            ai_initial=ai_initial or {},
            current_estimate=current_estimate or {},
            sku=sku,
            quantity=quantity,
        )
        self.store.save_new_record({**final_payload, "id": identifier})
        return identifier

    # ------------------------------------------------------------ update

    def update_record(
        self,
        record_id: str,
        payload: dict[str, Any],
        *,
        current_estimate: dict[str, Any] | None = None,
        sku: str | None = None,
        quantity: int | None = None,
    ) -> str:
        """历史修改：update 同一条记录，revision+1，ai_initial 保持不变。"""
        existing = self.store.load_record(record_id)
        existing_block = v2_block_from_payload(existing)
        revision = int(existing_block.get("revision") or 1) + 1
        final_payload = dict(payload)
        # 保留旧记录已有字段（如 created_at、images、旧 layers），避免历史丢失
        for key, value in existing.items():
            final_payload.setdefault(key, value)
        attach_v2_block(
            final_payload,
            origin="history_edit",
            revision=revision,
            ai_initial=None,  # None = 保留已存在的 ai_initial，绝不覆盖
            current_estimate=current_estimate or {},
            sku=sku,
            quantity=quantity,
        )
        # create 时的 origin 语义保留在 snapshots 中；当前记录标记最近一次编辑来源
        self.store.update_record(record_id, {**final_payload, "id": record_id})
        return record_id

    def save(
        self,
        payload: dict[str, Any],
        *,
        ai_initial: dict[str, Any] | None = None,
        current_estimate: dict[str, Any] | None = None,
        record_id: str | None = None,
        sku: str | None = None,
        quantity: int | None = None,
    ) -> str:
        """统一入口：record_id 不存在→create；存在→update same record。"""
        if record_id and self.store.record_exists(record_id):
            return self.update_record(
                record_id, payload, current_estimate=current_estimate, sku=sku, quantity=quantity,
            )
        return self.create_record(
            payload, ai_initial=ai_initial, current_estimate=current_estimate,
            record_id=record_id, sku=sku, quantity=quantity,
        )

    # ------------------------------------------------------------ feedback link

    def link_feedback(self, record_id: str, feedback_id: str) -> None:
        """只挂引用，不复制反馈内容（避免两份数据不一致），不算一次编辑。"""
        payload = self.store.load_record(record_id)
        block = v2_block_from_payload(payload)
        block["calibration_feedback_id"] = feedback_id
        block.setdefault("record_schema_version", RECORD_SCHEMA_VERSION)
        payload["_v2"] = block
        self.store.update_record(record_id, payload, snapshot_kind="feedback_link")

    # ------------------------------------------------------------ calibration

    def update_current_estimate(self, record_id: str, estimate: dict[str, Any]) -> None:
        """校准窄接口：只更新 ``_v2.current_estimate``。

        不递增 revision、不修改 layers、不算一次完整编辑；
        供主页面用户校准与历史页“编辑校准”对话框双向同步同一个当前采用结果。
        """
        payload = self.store.load_record(record_id)
        block = v2_block_from_payload(payload)
        block["current_estimate"] = dict(estimate or {})
        block.setdefault("record_schema_version", RECORD_SCHEMA_VERSION)
        payload["_v2"] = block
        self.store.update_record(record_id, payload, snapshot_kind="calibration_edit")

    # ------------------------------------------------------------ read

    def load_v2(self, record_id: str) -> HistoryRecordV2:
        """兼容读取：新旧记录都能得到 HistoryRecordV2 视图。"""
        return record_from_payload(self.store.load_record(record_id))

    def list_v2(self, *, search: str = "") -> list[HistoryRecordV2]:
        return [record_from_payload(payload) for payload in self.store.list_records(search=search)]

    def record_schema_version(self, record_id: str) -> str:
        block = v2_block_from_payload(self.store.load_record(record_id))
        return str(block.get("record_schema_version") or "2.6.1")

    def validate_origin(self, origin: str) -> None:
        if origin not in RECORD_ORIGINS:
            raise ValueError(f"origin 非法: {origin}")
