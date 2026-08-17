"""HistoryRecord V2 / CalibrationFeedback V1 数据合同。

职责边界：只做序列化 / 校验 / 兼容读取，不做 UI、不改生产算法。

设计原则（本轮任务约束）：
- 复用现有 SQLite ``records`` 表：V2 以附加字段 ``_v2`` 形式落在记录 payload 内，
  旧记录继续可读，V2 新字段默认 null，不做不可逆迁移。
- ``ai_initial`` 一旦写入绝不覆盖：历史编辑只更新 ``current_estimate``。
- ``legacy_packaging_output``（normal/conservative 双档）是当前引擎的历史遗留
  输出，不是 V2 长期数据标准；V2 主结果为单一 ``estimated_package`` /
  ``current_estimate``。
- 数据库不存图片二进制，只存 ImageStore 引用（hash + 相对 storage key）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

RECORD_SCHEMA_VERSION = "history-record-v2"
FEEDBACK_SCHEMA_VERSION = "calibration-feedback-v1"
LEGACY_RECORD_SCHEMA_VERSION = "2.6.1"

RECORD_ORIGINS = ("new_calculation", "history_edit")
FEEDBACK_SOURCES = ("user", "developer")

# 结构反馈三态字段：true / false / unknown（None 归一为 unknown）
STRUCTURE_TRI_STATE_KEYS = (
    "can_fold", "can_compress", "can_coil", "can_disassemble", "requires_shape_retention",
)
STRUCTURE_PARTS_KEYS = (
    "foldable_parts", "compressible_parts", "coilable_parts", "detachable_parts", "rigid_parts",
)
AXIS_KEYS = ("length", "width", "height")
AXIS_BEHAVIORS = ("preserve", "fold", "compress", "coil", "unknown")
EVIDENCE_LEVELS = (
    "actual_measured", "actual_logistics", "user_observation", "user_estimate", "unknown",
)
SUGGESTED_EVIDENCE_LEVEL = "user_suggested"

# V2 附加字段在记录 payload 中的键（旧记录没有该键）
V2_PAYLOAD_KEY = "_v2"


def _coerce_tri_state(value: Any) -> bool | str:
    if value is True or value is False:
        return value
    return "unknown"


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _coerce_optional_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _coerce_optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


# ---------------------------------------------------------------------------
# Structure / suggested package / actual logistics（反馈内容块）
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class StructureFeedback:
    """有限、清晰的结构反馈；所有字段允许 unknown / 空。"""

    can_fold: bool | str = "unknown"
    can_compress: bool | str = "unknown"
    can_coil: bool | str = "unknown"
    can_disassemble: bool | str = "unknown"
    requires_shape_retention: bool | str = "unknown"
    foldable_parts: list[str] = field(default_factory=list)
    compressible_parts: list[str] = field(default_factory=list)
    coilable_parts: list[str] = field(default_factory=list)
    detachable_parts: list[str] = field(default_factory=list)
    rigid_parts: list[str] = field(default_factory=list)
    axis_behavior: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "StructureFeedback":
        data = data if isinstance(data, dict) else {}
        axis_raw = data.get("axis_behavior")
        axis_raw = axis_raw if isinstance(axis_raw, dict) else {}
        axis_behavior = {}
        for axis in AXIS_KEYS:
            behavior = str(axis_raw.get(axis) or "unknown").strip().lower()
            axis_behavior[axis] = behavior if behavior in AXIS_BEHAVIORS else "unknown"
        return cls(
            **{key: _coerce_tri_state(data.get(key)) for key in STRUCTURE_TRI_STATE_KEYS},
            **{key: _coerce_string_list(data.get(key)) for key in STRUCTURE_PARTS_KEYS},
            axis_behavior=axis_behavior,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **{key: getattr(self, key) for key in STRUCTURE_TRI_STATE_KEYS},
            **{key: list(getattr(self, key)) for key in STRUCTURE_PARTS_KEYS},
            "axis_behavior": dict(self.axis_behavior),
        }

    def has_content(self) -> bool:
        return (
            any(getattr(self, key) != "unknown" for key in STRUCTURE_TRI_STATE_KEYS)
            or any(getattr(self, key) for key in STRUCTURE_PARTS_KEYS)
            or any(behavior != "unknown" for behavior in self.axis_behavior.values())
        )


@dataclass(slots=True)
class SuggestedPackage:
    """用户建议包装：永远标记 user_suggested，不得当成实测数据。"""

    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None
    weight_g: float | None = None
    packaging_method: str | None = None
    evidence_level: str = SUGGESTED_EVIDENCE_LEVEL

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SuggestedPackage":
        data = data if isinstance(data, dict) else {}
        return cls(
            length_cm=_coerce_optional_number(data.get("length_cm")),
            width_cm=_coerce_optional_number(data.get("width_cm")),
            height_cm=_coerce_optional_number(data.get("height_cm")),
            weight_g=_coerce_optional_number(data.get("weight_g")),
            packaging_method=_coerce_optional_text(data.get("packaging_method")),
            # 建议值不是实测值：evidence_level 恒为 user_suggested
            evidence_level=SUGGESTED_EVIDENCE_LEVEL,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "length_cm": self.length_cm,
            "width_cm": self.width_cm,
            "height_cm": self.height_cm,
            "weight_g": self.weight_g,
            "packaging_method": self.packaging_method,
            "evidence_level": self.evidence_level,
        }

    def has_content(self) -> bool:
        return any(
            value is not None
            for value in (self.length_cm, self.width_cm, self.height_cm, self.weight_g, self.packaging_method)
        )


@dataclass(slots=True)
class ActualLogistics:
    """真实物流反馈：全部可选。实际费用不等于真实包装尺寸，不得互相推导。"""

    actual_first_mile_fee_rmb: float | None = None
    actual_forwarder: str | None = None
    actual_chargeable_weight_kg: float | None = None
    actual_package_dimensions: dict[str, Any] | None = None
    actual_package_weight_g: float | None = None
    actual_packaging_method: str | None = None
    evidence_level: str = "unknown"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ActualLogistics":
        data = data if isinstance(data, dict) else {}
        evidence = str(data.get("evidence_level") or "unknown").strip().lower()
        dimensions = data.get("actual_package_dimensions")
        return cls(
            actual_first_mile_fee_rmb=_coerce_optional_number(data.get("actual_first_mile_fee_rmb")),
            actual_forwarder=_coerce_optional_text(data.get("actual_forwarder")),
            actual_chargeable_weight_kg=_coerce_optional_number(data.get("actual_chargeable_weight_kg")),
            actual_package_dimensions=dimensions if isinstance(dimensions, dict) else None,
            actual_package_weight_g=_coerce_optional_number(data.get("actual_package_weight_g")),
            actual_packaging_method=_coerce_optional_text(data.get("actual_packaging_method")),
            evidence_level=evidence if evidence in EVIDENCE_LEVELS else "unknown",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "actual_first_mile_fee_rmb": self.actual_first_mile_fee_rmb,
            "actual_forwarder": self.actual_forwarder,
            "actual_chargeable_weight_kg": self.actual_chargeable_weight_kg,
            "actual_package_dimensions": self.actual_package_dimensions,
            "actual_package_weight_g": self.actual_package_weight_g,
            "actual_packaging_method": self.actual_packaging_method,
            "evidence_level": self.evidence_level,
        }

    def has_content(self) -> bool:
        return any(
            value is not None
            for value in (
                self.actual_first_mile_fee_rmb, self.actual_forwarder,
                self.actual_chargeable_weight_kg, self.actual_package_dimensions,
                self.actual_package_weight_g, self.actual_packaging_method,
            )
        )


# ---------------------------------------------------------------------------
# CalibrationFeedback V1
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CalibrationFeedback:
    """用户/开发者统一校准反馈事件。只有一句文字反馈也允许保存。"""

    feedback_id: str
    record_id: str
    source: str = "user"
    feedback_schema_version: str = FEEDBACK_SCHEMA_VERSION
    created_at: str | None = None
    updated_at: str | None = None
    structure: StructureFeedback = field(default_factory=StructureFeedback)
    suggested_package: SuggestedPackage | None = None
    actual_logistics: ActualLogistics | None = None
    user_note: str | None = None
    # 防重复导出状态（只提供状态，不阻止再次导出）
    calibration_exported_at: str | None = None
    calibration_export_batch_id: str | None = None
    feedback_updated_after_export: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CalibrationFeedback":
        if not isinstance(data, dict):
            raise ValueError("feedback 必须是 JSON 对象")
        feedback_id = str(data.get("feedback_id") or "").strip()
        record_id = str(data.get("record_id") or "").strip()
        if not feedback_id:
            raise ValueError("缺少 feedback_id")
        if not record_id:
            raise ValueError("缺少 record_id")
        source = str(data.get("source") or "user").strip().lower()
        if source not in FEEDBACK_SOURCES:
            raise ValueError(f"source 非法: {source}（允许: {', '.join(FEEDBACK_SOURCES)}）")
        suggested_raw = data.get("suggested_package")
        actual_raw = data.get("actual_logistics")
        return cls(
            feedback_id=feedback_id,
            record_id=record_id,
            source=source,
            feedback_schema_version=str(data.get("feedback_schema_version") or FEEDBACK_SCHEMA_VERSION),
            created_at=_coerce_optional_text(data.get("created_at")),
            updated_at=_coerce_optional_text(data.get("updated_at")),
            structure=StructureFeedback.from_dict(data.get("structure")),
            suggested_package=SuggestedPackage.from_dict(suggested_raw) if isinstance(suggested_raw, dict) else None,
            actual_logistics=ActualLogistics.from_dict(actual_raw) if isinstance(actual_raw, dict) else None,
            user_note=_coerce_optional_text(data.get("user_note")),
            calibration_exported_at=_coerce_optional_text(data.get("calibration_exported_at")),
            calibration_export_batch_id=_coerce_optional_text(data.get("calibration_export_batch_id")),
            feedback_updated_after_export=bool(data.get("feedback_updated_after_export", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "feedback_id": self.feedback_id,
            "feedback_schema_version": self.feedback_schema_version,
            "record_id": self.record_id,
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "structure": self.structure.to_dict(),
            "suggested_package": self.suggested_package.to_dict() if self.suggested_package else None,
            "actual_logistics": self.actual_logistics.to_dict() if self.actual_logistics else None,
            "user_note": self.user_note,
            "calibration_exported_at": self.calibration_exported_at,
            "calibration_export_batch_id": self.calibration_export_batch_id,
            "feedback_updated_after_export": self.feedback_updated_after_export,
        }

    def validate(self) -> list[str]:
        """返回问题列表；空列表表示合法。宽松：缺失数据不阻止保存。"""
        issues: list[str] = []
        if not self.feedback_id:
            issues.append("缺少 feedback_id")
        if not self.record_id:
            issues.append("缺少 record_id")
        if self.source not in FEEDBACK_SOURCES:
            issues.append(f"source 非法: {self.source}")
        if self.suggested_package and self.suggested_package.evidence_level != SUGGESTED_EVIDENCE_LEVEL:
            issues.append("用户建议包装不得标记为实测数据（evidence_level 必须是 user_suggested）")
        if (
            self.actual_logistics
            and self.actual_logistics.evidence_level not in EVIDENCE_LEVELS
        ):
            issues.append(f"evidence_level 非法: {self.actual_logistics.evidence_level}")
        if not self.has_content():
            issues.append("反馈内容为空（至少需要结构反馈、建议包装、真实物流或文字备注之一）")
        return issues

    def has_content(self) -> bool:
        return (
            self.structure.has_content()
            or bool(self.suggested_package and self.suggested_package.has_content())
            or bool(self.actual_logistics and self.actual_logistics.has_content())
            or bool(self.user_note)
        )


# ---------------------------------------------------------------------------
# HistoryRecord V2
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class HistoryRecordV2:
    """一条历史记录：当时输入 → AI 第一次判断 → 用户采用 → 利润快照 → 校准反馈。

    这是记录 payload 的类型化视图；持久化仍然走现有 SQLite ``records`` 表，
    V2 专属字段放在 payload 的 ``_v2`` 附加键中，旧记录无该键时全部默认 null。
    """

    record_id: str
    record_schema_version: str = RECORD_SCHEMA_VERSION
    created_at: str | None = None
    updated_at: str | None = None
    revision: int = 1
    origin: str = "new_calculation"
    # Product
    product_name: str | None = None
    product_link: str | None = None
    sku: str | None = None
    quantity: int | None = None
    # Images：只存 ImageStore 引用，不存二进制
    images: list[dict[str, Any]] = field(default_factory=list)
    # Bare Product Facts（裸品事实，不混入包装后尺寸）
    bare_product: dict[str, Any] = field(default_factory=dict)
    # Initial AI Result（第一次 AI 判断，永不被编辑覆盖）
    ai_initial: dict[str, Any] | None = None
    # Current Adopted Result（用户当前采用的单一主包装结果）
    current_estimate: dict[str, Any] = field(default_factory=dict)
    # Local re-estimate full trace（后台校准证据：每次局部重估的完整轨迹）
    reestimate_history: list[dict[str, Any]] = field(default_factory=list)
    # Calculation Snapshot（复用现有 profit_scenarios / layers.calculated）
    calculation_snapshot: dict[str, Any] = field(default_factory=dict)
    # Calibration Feedback 引用（避免重复保存两份可能不一致的数据）
    calibration_feedback_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "record_schema_version": self.record_schema_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "revision": self.revision,
            "origin": self.origin,
            "product_name": self.product_name,
            "product_link": self.product_link,
            "sku": self.sku,
            "quantity": self.quantity,
            "images": list(self.images),
            "bare_product": dict(self.bare_product),
            "ai_initial": self.ai_initial,
            "current_estimate": dict(self.current_estimate),
            "reestimate_history": [dict(entry) for entry in self.reestimate_history],
            "calculation_snapshot": dict(self.calculation_snapshot),
            "calibration_feedback_id": self.calibration_feedback_id,
        }


def v2_block_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """从记录 payload 读取 ``_v2`` 块；旧记录返回空对象（V2 字段默认 null）。"""
    block = payload.get(V2_PAYLOAD_KEY) if isinstance(payload, dict) else None
    return dict(block) if isinstance(block, dict) else {}


def is_legacy_payload(payload: dict[str, Any]) -> bool:
    """旧记录：无 ``_v2`` 键，schema 停留在 2.6.1 layers 结构。"""
    return isinstance(payload, dict) and V2_PAYLOAD_KEY not in payload


def record_from_payload(payload: dict[str, Any]) -> HistoryRecordV2:
    """兼容读取：旧记录与新记录都能转成 HistoryRecordV2 视图。

    旧记录的 AI 第一次判断只能近似取 ``layers.ai_raw``（legacy_layers_ai_raw），
    因为旧生产代码每次保存都会重建该层；V2 记录保存后由后端保证不再覆盖。
    """
    if not isinstance(payload, dict):
        raise ValueError("记录 payload 必须是 JSON 对象")
    record_id = str(payload.get("id") or "").strip()
    if not record_id:
        raise ValueError("记录缺少 id")
    layers = payload.get("layers")
    layers = layers if isinstance(layers, dict) else {}
    adopted = layers.get("adopted")
    adopted = adopted if isinstance(adopted, dict) else {}
    selected = adopted.get("selected_packaging") or "normal"
    selected_scenario = adopted.get("conservative") if selected == "保守档" else adopted.get("normal")
    selected_scenario = selected_scenario if isinstance(selected_scenario, dict) else {}
    v2 = v2_block_from_payload(payload)
    ai_initial = v2.get("ai_initial")
    if ai_initial is None and isinstance(layers.get("ai_raw"), dict):
        ai_initial = {
            "legacy_layers_ai_raw": layers["ai_raw"],
            "note": "旧记录近似：2.6.1 每次保存重建 layers.ai_raw，无法保证是第一次 AI 判断",
        }
    return HistoryRecordV2(
        record_id=record_id,
        record_schema_version=str(v2.get("record_schema_version") or LEGACY_RECORD_SCHEMA_VERSION),
        created_at=_coerce_optional_text(payload.get("created_at")),
        updated_at=_coerce_optional_text(payload.get("updated_at") or payload.get("_updated_at")),
        revision=int(v2.get("revision") or 1),
        origin=str(v2.get("origin") or "new_calculation"),
        product_name=_coerce_optional_text(payload.get("product_name")),
        product_link=_coerce_optional_text(payload.get("product_link")),
        sku=_coerce_optional_text(v2.get("sku")),
        quantity=v2.get("quantity") if isinstance(v2.get("quantity"), int) else None,
        images=list(payload.get("images") or []) if isinstance(payload.get("images"), list) else [],
        bare_product=dict(adopted.get("bare") or {}) if isinstance(adopted.get("bare"), dict) else {},
        ai_initial=ai_initial if isinstance(ai_initial, dict) else None,
        current_estimate=v2.get("current_estimate") if isinstance(v2.get("current_estimate"), dict) else {
            "packaging_method": selected_scenario.get("packaging_method"),
            "length_cm": selected_scenario.get("length_cm"),
            "width_cm": selected_scenario.get("width_cm"),
            "height_cm": selected_scenario.get("height_cm"),
            "weight_g": selected_scenario.get("weight_g"),
            "selected_packaging": selected,
        },
        reestimate_history=[
            dict(entry)
            for entry in (v2.get("reestimate_history") or [])
            if isinstance(entry, dict)
        ],
        calculation_snapshot={
            "calculated": layers.get("calculated") if isinstance(layers.get("calculated"), dict) else {},
            "profit_scenarios": payload.get("profit_scenarios") if isinstance(payload.get("profit_scenarios"), dict) else {},
        },
        calibration_feedback_id=_coerce_optional_text(v2.get("calibration_feedback_id")),
    )


def attach_v2_block(payload: dict[str, Any], *, origin: str, revision: int,
                    ai_initial: dict[str, Any] | None, current_estimate: dict[str, Any],
                    sku: str | None = None, quantity: int | None = None,
                    calibration_feedback_id: str | None = None) -> dict[str, Any]:
    """在记录 payload 上写/更新 ``_v2`` 附加块（不删除任何旧字段）。

    ``ai_initial`` 传 None 表示保留已存在的值——这是“编辑不覆盖 AI 第一次结果”
    的实现入口：更新路径只传 current_estimate，绝不重建 ai_initial。
    """
    if origin not in RECORD_ORIGINS:
        raise ValueError(f"origin 非法: {origin}（允许: {', '.join(RECORD_ORIGINS)}）")
    block = v2_block_from_payload(payload)
    block["record_schema_version"] = RECORD_SCHEMA_VERSION
    block["origin"] = origin
    block["revision"] = max(1, int(revision))
    if ai_initial is not None:
        block["ai_initial"] = ai_initial
    if sku is not None:
        block["sku"] = sku
    if quantity is not None:
        block["quantity"] = quantity
    if current_estimate:
        block["current_estimate"] = current_estimate
    if calibration_feedback_id is not None:
        block["calibration_feedback_id"] = calibration_feedback_id
    payload[V2_PAYLOAD_KEY] = block
    return payload
