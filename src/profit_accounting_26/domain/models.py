from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class ImageType(StrEnum):
    MAIN = "主图"
    PRODUCT_INFO = "商品信息"
    DIMENSION_WEIGHT = "尺寸/重量"


class PackagingState(StrEnum):
    FULL_FLAT_FOLD = "full_flat_fold"
    STRONG_COMPRESSION = "strong_compression"
    MODERATE_COMPRESSION = "moderate_compression"
    SHAPE_RETAINED = "shape_retained"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Forwarder:
    id: str
    name: str
    rate_rmb_per_kg: float
    fixed_fee_rmb: float
    volume_divisor: float = 8000.0
    enabled: bool = True
    archived: bool = False

    def validate(self) -> None:
        if not self.id.strip() or not self.name.strip():
            raise ValueError("货代 ID 和名称不能为空")
        if self.rate_rmb_per_kg < 0 or self.fixed_fee_rmb < 0:
            raise ValueError("货代费用不能为负数")
        if self.volume_divisor <= 0:
            raise ValueError("体积重除数必须大于 0")


@dataclass(frozen=True, slots=True)
class PackageSpec:
    length_cm: float
    width_cm: float
    height_cm: float
    weight_g: float

    def validate(self) -> None:
        values = (self.length_cm, self.width_cm, self.height_cm, self.weight_g)
        if any(value <= 0 for value in values):
            raise ValueError("包装尺寸与重量必须大于 0")

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LogisticsQuote:
    forwarder_id: str
    actual_weight_kg: float
    volume_weight_kg: float
    chargeable_weight_kg: float
    weight_fee_rmb: float
    fixed_fee_rmb: float
    tail_fee_rmb: float
    total_logistics_rmb: float


@dataclass(frozen=True, slots=True)
class ProfitResult:
    sale_price_usd: float
    sale_price_rmb: float
    revenue_after_reserve_rmb: float
    total_cost_rmb: float
    income_adjustment_rmb: float
    cost_adjustment_rmb: float
    profit_rmb: float
    profit_rate_on_cost: float | None


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    """单条利润规则在某个场景下的评估明细，用于 UI tooltip。

    不改变原规则数据格式，仅作为非破坏性的评估结果结构。
    """

    rule_id: str
    rule_name: str
    scenario: str  # "no_activity" | "activity"
    condition_field: str
    condition_value: float
    compare_op: str
    matched: bool
    direction: str  # "income" | "cost"
    amount_rmb: float
    amount_original: float
    currency: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ScenarioProfitResult:
    """单场景利润结果（无活动或活动后）。

    每个场景按其真实售价独立执行规则；reserve 已在传入售价中折算，
    因此内部 reserve_rate 恒为 0。
    """

    sale_price_usd: float
    sale_price_rmb: float
    total_cost_rmb: float
    income_adjustment_rmb: float
    cost_adjustment_rmb: float
    profit_rmb: float
    profit_usd: float
    profit_rate_on_cost: float | None
    rule_evaluations: tuple[RuleEvaluation, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "sale_price_usd": self.sale_price_usd,
            "sale_price_rmb": self.sale_price_rmb,
            "total_cost_rmb": self.total_cost_rmb,
            "income_adjustment_rmb": self.income_adjustment_rmb,
            "cost_adjustment_rmb": self.cost_adjustment_rmb,
            "profit_rmb": self.profit_rmb,
            "profit_usd": self.profit_usd,
            "profit_rate_on_cost": self.profit_rate_on_cost,
            "rule_evaluations": [item.to_dict() for item in self.rule_evaluations],
        }


@dataclass(frozen=True, slots=True)
class DualProfitResult:
    """双场景利润结果（无活动 + 活动后）。

    利润率统一为 活动后利润 RMB / 计算总成本 RMB。
    """

    calculation_total_cost_rmb: float
    exchange_rate: float
    reserve_percent: float  # 0-100
    no_activity: ScenarioProfitResult
    activity: ScenarioProfitResult
    profit_rate: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "2.6.1-dual-profit-v1",
            "calculation_total_cost_rmb": self.calculation_total_cost_rmb,
            "exchange_rate": self.exchange_rate,
            "reserve_percent": self.reserve_percent,
            "no_activity": self.no_activity.to_dict(),
            "activity": self.activity.to_dict(),
            "profit_rate": self.profit_rate,
        }


@dataclass(slots=True)
class ValueLayers:
    ai_raw: dict[str, Any] = field(default_factory=dict)
    adopted: dict[str, Any] = field(default_factory=dict)
    calculated: dict[str, Any] = field(default_factory=dict)
    actual: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AIObservation:
    """Facts observed from images or entered manually.

    Structural booleans intentionally default to ``None``.  Unknown evidence is
    not equivalent to a negative observation.
    """

    product_name: str = ""
    product_type: str = ""
    product_family: str = ""
    product_type_raw: str = ""
    product_type_code: str = "unknown"
    product_family_code: str = "unknown"
    material: str = ""
    material_family: str = ""
    material_family_code: str = "unknown"
    packaging_state_hint: str = "unknown"
    display_product_summary: str = ""
    display_packaging_summary: str = ""
    # Overall transport form is intentionally independent from material rigidity.
    overall_form: str = "unknown"
    packing_actions: list[str] = field(default_factory=list)
    packing_constraints: list[str] = field(default_factory=list)
    rigidity: str = "unknown"
    foldability: str = "unknown"
    compressibility: str = "unknown"
    requires_shape_retention: bool | None = None
    has_hard_bottom: bool | None = None
    has_hard_backboard: bool | None = None
    has_frame: bool | None = None
    has_rigid_insert: bool | None = None
    has_rigid_parts: bool | None = None
    retail_box_visible: bool | None = None
    hard_card_visible: bool | None = None
    protrusion_flattenable: bool | None = None
    product_cost_rmb: float | None = None
    product_cost_value_type: str = "unknown"
    domestic_shipping_rmb: float | None = None
    domestic_shipping_value_type: str = "unknown"
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None
    weight_g: float | None = None
    dimension_value_source: str = "unknown"
    weight_value_source: str = "unknown"
    dimension_scope: str = "unknown"
    weight_scope: str = "unknown"
    quantity: int = 1
    quantity_source: str = "unknown"
    quantity_unit: str = ""
    quantity_summary: str = ""
    # 商品成本三字段语义（v2.2 数据合同）：
    # - product_cost_rmb 恒为「本次购买/当前选择数量对应的商品货值总额」；
    # - product_unit_price_rmb / product_total_cost_rmb 是 AI 从页面读到的原始
    #   单价 / 总价（审计用），历史 raw 保留，本地不修改。
    product_unit_price_rmb: float | None = None
    product_total_cost_rmb: float | None = None
    source: str = "manual"
    model: str = ""
    prompt_version: str = ""
    confidence: str = "low"
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AIObservation":
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: value for key, value in data.items() if key in allowed})


@dataclass(slots=True)
class PackagingScenario:
    label: str
    packaging_state: PackagingState = PackagingState.UNKNOWN
    packaging_method: str = ""
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None
    weight_g: float | None = None
    reasoning_summary: str = ""
    confidence: str = "low"
    needs_review: bool = True
    default_fields_used: list[str] = field(default_factory=list)

    def is_complete(self) -> bool:
        values = (self.length_cm, self.width_cm, self.height_cm, self.weight_g)
        return all(value is not None and float(value) > 0 for value in values)

    def to_package_spec(self) -> PackageSpec:
        if not self.is_complete():
            raise ValueError(f"{self.label}包装方案信息不完整")
        return PackageSpec(
            length_cm=float(self.length_cm),
            width_cm=float(self.width_cm),
            height_cm=float(self.height_cm),
            weight_g=float(self.weight_g),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["packaging_state"] = self.packaging_state.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PackagingScenario":
        payload = dict(data)
        payload["packaging_state"] = PackagingState(
            payload.get("packaging_state", PackagingState.UNKNOWN.value)
        )
        return cls(**payload)


@dataclass(slots=True)
class PackagingProposal:
    normal: PackagingScenario
    conservative: PackagingScenario
    proposal_source: str = "local_calibration"
    needs_review: bool = True
    review_reasons: list[str] = field(default_factory=list)
    original_scenarios: dict[str, Any] = field(default_factory=dict)
    local_proposed_scenarios: dict[str, Any] = field(default_factory=dict)
    adjusted_scenarios: dict[str, Any] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)
    applied_profile_ids: list[str] = field(default_factory=list)
    candidate_records: dict[str, dict[str, Any]] = field(default_factory=dict)
    rejected_candidates: dict[str, list[str]] = field(default_factory=dict)
    adjustments: list[str] = field(default_factory=list)
    engine_version: str = "packaging-estimation-v1"
    calibration_version: str = "local-calibration-v3"
    schema_version: str = "2.6.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "normal": self.normal.to_dict(),
            "conservative": self.conservative.to_dict(),
            "proposal_source": self.proposal_source,
            "needs_review": self.needs_review,
            "review_reasons": list(self.review_reasons),
            "original_scenarios": self.original_scenarios,
            "local_proposed_scenarios": self.local_proposed_scenarios,
            "adjusted_scenarios": self.adjusted_scenarios,
            "conflicts": list(self.conflicts),
            "applied_profile_ids": list(self.applied_profile_ids),
            "candidate_records": self.candidate_records,
            "rejected_candidates": self.rejected_candidates,
            "adjustments": list(self.adjustments),
            "engine_version": self.engine_version,
            "calibration_version": self.calibration_version,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PackagingProposal":
        return cls(
            normal=PackagingScenario.from_dict(data["normal"]),
            conservative=PackagingScenario.from_dict(data["conservative"]),
            proposal_source=str(data.get("proposal_source") or "unknown"),
            needs_review=bool(data.get("needs_review", True)),
            review_reasons=list(data.get("review_reasons") or []),
            original_scenarios=dict(data.get("original_scenarios") or {}),
            local_proposed_scenarios=dict(data.get("local_proposed_scenarios") or {}),
            adjusted_scenarios=dict(data.get("adjusted_scenarios") or {}),
            conflicts=list(data.get("conflicts") or []),
            applied_profile_ids=list(data.get("applied_profile_ids") or []),
            candidate_records=dict(data.get("candidate_records") or {}),
            rejected_candidates={str(key): list(value or []) for key, value in dict(data.get("rejected_candidates") or {}).items()},
            adjustments=list(data.get("adjustments") or []),
            engine_version=str(data.get("engine_version") or "packaging-estimation-v1"),
            calibration_version=str(data.get("calibration_version") or "local-calibration-v3"),
            schema_version=str(data.get("schema_version") or "2.6.1"),
        )
