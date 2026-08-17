from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import re
import threading
import time
import traceback
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlparse

from profit_accounting_26.application.api_profile_store import ApiProfileStore, VISUAL_AI
from profit_accounting_26.application.qwen_request_params import qwen_extra_body_params
from profit_accounting_26.application.settings_service import SettingsService
from profit_accounting_26.domain.models import AIObservation, PackagingProposal, PackagingScenario, PackagingState
from profit_accounting_26.application.diagnostic_logger import DiagnosticOperation, DiagnosticLogger
from profit_accounting_26.application.category_normalizer import normalize_observation


class RecognitionUnavailableError(RuntimeError):
    pass


class RecognitionResponseError(RuntimeError):
    pass


class RecognitionCancelledError(RuntimeError):
    pass


# Keywords that indicate fulfillment/timing info rather than physical shipping state.
_INVALID_STATE_KEYWORDS: tuple[str, ...] = (
    "小时发货", "天发货", "现货", "包邮", "发货时效", "商家履约",
    "快递速度", "快递时效", "物流速度", "物流时效",
    "顺丰", "中通", "圆通", "申通", "韵达", "邮政", "EMS", "DHL", "FedEx", "UPS",
    "48小时", "24小时", "72小时", "当日", "次日", "当天",
)


def _is_invalid_shipment_state(state: str) -> bool:
    """Reject state values that describe fulfillment timing rather than physical form."""
    if not state:
        return False
    lower = state.lower()
    return any(kw.lower() in lower for kw in _INVALID_STATE_KEYWORDS)


class RecognitionCancellation:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._response = None

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()
        with self._lock:
            response = self._response
        if response is not None:
            try:
                response.close()
            except OSError:
                pass

    def bind_response(self, response) -> None:
        with self._lock:
            self._response = response
        if self.cancelled:
            try:
                response.close()
            except OSError:
                pass

    def clear_response(self) -> None:
        with self._lock:
            self._response = None


class RecognitionService:
    """One-click, one-request vision boundary.

    Image slot types are intentionally not sent as recognition restrictions.
    Every image is scanned for every supported field. Field evidence remains in
    observation.raw_payload for audit and automatic UI fill.
    """

    PROMPT_VERSION = "2.6.1-visual-v1.9"
    RESPONSE_SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "required": ["product_name", "observed", "bare_estimate", "shipment", "note"],
        "properties": {
            "product_name": {"type": "string"},
            "observed": {
                "type": "object",
                "additionalProperties": False,
                "required": ["product_price_rmb", "page_shipping_rmb", "bare_dimensions_cm", "bare_weight_g"],
                "properties": {
                    "product_price_rmb": {"type": ["number", "null"]},
                    "page_shipping_rmb": {"type": ["number", "null"]},
                    "bare_dimensions_cm": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["length", "width", "height"],
                        "properties": {
                            "length": {"type": ["number", "null"]},
                            "width": {"type": ["number", "null"]},
                            "height": {"type": ["number", "null"]},
                        },
                    },
                    "bare_weight_g": {"type": ["number", "null"]},
                },
            },
            "bare_estimate": {
                "type": "object",
                "additionalProperties": False,
                "required": ["length_cm", "width_cm", "height_cm", "weight_g"],
                "properties": {
                    "length_cm": {"type": ["number", "null"]},
                    "width_cm": {"type": ["number", "null"]},
                    "height_cm": {"type": ["number", "null"]},
                    "weight_g": {"type": ["number", "null"]},
                },
            },
            "shipment": {
                "type": "object",
                "additionalProperties": False,
                "required": ["length_cm", "width_cm", "height_cm", "weight_g", "state"],
                "properties": {
                    "length_cm": {"type": "number"},
                    "width_cm": {"type": "number"},
                    "height_cm": {"type": "number"},
                    "weight_g": {"type": "number"},
                    "state": {"type": "string"},
                },
            },
            "structure": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "overall_form": {"type": ["string", "null"]},
                    "packaging_state_hint": {"type": ["string", "null"]},
                    "rigidity": {"type": ["string", "null"]},
                    "foldability": {"type": ["string", "null"]},
                    "compressibility": {"type": ["string", "null"]},
                    "requires_shape_retention": {"type": ["boolean", "null"]},
                    "packing_actions": {"type": ["array", "null"], "items": {"type": "string"}},
                    "packing_constraints": {"type": ["array", "null"], "items": {"type": "string"}},
                    "has_hard_bottom": {"type": ["boolean", "null"]},
                    "has_hard_backboard": {"type": ["boolean", "null"]},
                    "has_frame": {"type": ["boolean", "null"]},
                    "has_rigid_insert": {"type": ["boolean", "null"]},
                    "has_rigid_parts": {"type": ["boolean", "null"]},
                    "retail_box_visible": {"type": ["boolean", "null"]},
                    "hard_card_visible": {"type": ["boolean", "null"]},
                    "protrusion_flattenable": {"type": ["boolean", "null"]}
                }
            },
            "quantity": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "purchase_quantity": {"type": ["integer", "null"]},
                    "quantity_source": {"type": ["string", "null"]},
                    "quantity_summary": {"type": ["string", "null"]}
                }
            },
            "field_evidence": {
                "type": "object",
                "additionalProperties": True,
                "description": "Optional located evidence for structure booleans. Keys are field names (e.g. has_hard_bottom). Values are objects with source_image_index, region_description or raw_text, and source.",
                "properties": {}
            },
            "note": {"type": "string"},
        },
    }

    def __init__(self, settings_service: SettingsService, profile_store: ApiProfileStore | None = None) -> None:
        self.settings_service = settings_service
        self.profile_store = profile_store

    @staticmethod
    def _endpoint(raw: str) -> str:
        value = raw.strip().rstrip("/")
        if not value:
            return ""
        return value if value.endswith("/chat/completions") else value + "/chat/completions"

    @staticmethod
    def _image_data_url(path: Path) -> str:
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    @staticmethod
    def _stable_paths(image_items: list[dict[str, str]]) -> list[Path]:
        """Make equivalent multi-image requests independent of UI slot order."""
        paths = [Path(str(item.get("path") or "")) for item in image_items]
        keyed_paths: list[tuple[str, str, Path]] = []
        for path in paths:
            if not path.is_file():
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            keyed_paths.append((digest, str(path.resolve()).lower(), path))
        return [path for _, _, path in sorted(keyed_paths)]

    @classmethod
    def _prompt(cls, image_count: int, *, include_json_shape: bool = True) -> str:
        prompt = f"""跨境电商商品图片识别助手。本次共 {image_count} 张图片。

职责：识别商品、读取页面事实、估算裸品、判断数量、整体判断发货。不计算费用。

1. product_name：简短、规范、可搜索。

2. observed：只读取图片/页面明确事实（商品价格、页面/国内运费、裸尺寸、裸重）；看不清返回 null，禁止猜测。

3. bare_estimate：observed 缺失时合理估算裸品长宽高/裸重（observed=页面事实，bare_estimate=AI推测，必须区分）。

4. quantity：先理解一个销售单位包含什么，再判断购买多少销售单位（purchase_quantity）。主图多件不能直接等于套装；库存/销量/MOQ/SKU数量不能当购买数量。无法确认时：shipment 按 1 个销售单位估算，quantity_source 填 assumed/unknown。

5. shipment（重点）：基于图片、页面事实、商品材质与结构、裸品、数量，以及正常低成本电商仓库的实际发货行为，直接整体判断真实打包员最可能采取什么正常处理方式，并给出处理后的长宽高、总重量和包装/运输状态。
   在两个极端之间正常判断：不过度保形（不无依据塞满填充物、纸箱完全保形），也不无依据做损伤商品的极端压缩。
   目标是"正常真实仓库最可能怎么发"，不是"最安全怎么发"，也不是"最极限省体积怎么发"。
   shipment.state 直接写最可能行为，同时描述主要物理形态、处理方式与包装方式，例如：自然压平后袋装、轻度压缩袋装、自然折叠后袋装、保持主体形状后袋装、保持形状后箱装。
   禁止：发货时效、包邮、货代、CAL、体积重、利润。禁止裸尺寸×数量、机械放大 L/W/H、固定压缩率。

6. structure（辅助观察，有明确证据才记录，无证据 null/unknown）：rigidity（soft/semi_rigid/hard）、foldability、compressibility、packaging_state_hint、requires_shape_retention、packing_actions（flat_fold/roll/coil/compress/nest/disassemble/retain_shape）、硬底/硬背板/框架/硬内衬/原盒/硬卡。
   不得因为"看起来挺括"自动推出 requires_shape_retention=true；不得因为 semi_rigid 自动推出不能压缩。硬结构与保形判断需要真实图片/页面证据，并在 field_evidence 定位（图序号+区域+原文）。structure 只作辅助记录，不得机械推导 shipment。

7. note：仅必要补充。

通用原则：
- 用户确认事实最高优先，不得修改。
- 页面/图片明确事实高于 AI 推测。
- 展示/支撑状态不等于实际运输状态。
- 已自然折叠/袋装/收纳状态不要无依据重新展开或再次极端处理。
- 不确定的页面事实返回 null。
""".strip()
        if not include_json_shape:
            return prompt + "\n只返回符合给定 JSON Schema 的一个 JSON 对象，不要 Markdown。"
        return prompt + "\n严格按以下 JSON 结构返回一个对象，不要 Markdown：\n" + json.dumps(
            {
              "product_name": "",
              "observed": {
                "product_price_rmb": None,
                "page_shipping_rmb": None,
                "bare_dimensions_cm": {
                  "length": None,
                  "width": None,
                  "height": None
                },
                "bare_weight_g": None
              },
              "bare_estimate": {
                "length_cm": None,
                "width_cm": None,
                "height_cm": None,
                "weight_g": None
              },
              "shipment": {
                "length_cm": 0,
                "width_cm": 0,
                "height_cm": 0,
                "weight_g": 0,
                "state": ""
              },
              "structure": {
                "packaging_state_hint": None,
                "rigidity": None,
                "foldability": None,
                "compressibility": None,
                "requires_shape_retention": None,
                "packing_actions": [],
                "has_hard_bottom": None,
                "has_hard_backboard": None,
                "has_frame": None,
                "has_rigid_insert": None,
                "retail_box_visible": None,
                "hard_card_visible": None
              },
              "quantity": {
                "purchase_quantity": None,
                "quantity_source": None,
                "quantity_summary": None
              },
              "field_evidence": {},
              "note": ""
            },
            ensure_ascii=False,
            indent=2,
        )

    @staticmethod
    def _extract_content(response: dict[str, Any]) -> str:
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RecognitionResponseError("视觉API返回格式不符合OpenAI兼容协议。") from exc
        if isinstance(content, list):
            content = "".join(
                str(item.get("text") or "")
                for item in content
                if isinstance(item, dict) and item.get("type") in {"text", "output_text"}
            )
        if not isinstance(content, str):
            raise RecognitionResponseError("视觉API未返回可读取的JSON文本。")
        text = content.strip()
        if text.startswith("```"):
            text = text.removeprefix("```json").removeprefix("```").strip()
            if text.endswith("```"):
                text = text[:-3].strip()
        return text

    @staticmethod
    def _parse_optional_number(value: Any, *, field_name: str,
                               parse_issues: dict[str, dict[str, Any]]) -> float | None:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            parse_issues[field_name] = {"raw_value": value, "reason": "boolean_not_numeric"}
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        match = re.fullmatch(r"(?:约\s*)?([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(cm|mm|g|kg|rmb|cny|usd)?", text, re.I)
        if not match:
            parse_issues[field_name] = {"raw_value": value, "reason": "ambiguous_or_non_numeric"}
            return None
        number, unit = float(match.group(1)), (match.group(2) or "").lower()
        if field_name.endswith(("length_cm", "width_cm", "height_cm")):
            if unit == "mm":
                return number / 10.0
            if unit not in {"", "cm"}:
                parse_issues[field_name] = {"raw_value": value, "reason": "unexpected_unit"}
                return None
        if field_name.endswith("weight_g"):
            if unit == "kg":
                return number * 1000.0
            if unit not in {"", "g"}:
                parse_issues[field_name] = {"raw_value": value, "reason": "unexpected_unit"}
                return None
        if field_name.endswith(("product_cost_rmb", "domestic_shipping_rmb")) and unit not in {"", "rmb", "cny"}:
            parse_issues[field_name] = {"raw_value": value, "reason": "unexpected_unit"}
            return None
        return number

    @classmethod
    def _clean_numeric_fields(cls, raw: dict[str, Any], *, prefix: str,
                              parse_issues: dict[str, dict[str, Any]]) -> dict[str, Any]:
        cleaned = dict(raw)
        for field in ("product_cost_rmb", "domestic_shipping_rmb", "length_cm", "width_cm", "height_cm", "weight_g", "quantity"):
            if field in cleaned:
                cleaned[field] = cls._parse_optional_number(cleaned[field], field_name=f"{prefix}.{field}", parse_issues=parse_issues)
        return cleaned

    @classmethod
    def _positive_shipment_number(cls, value: Any, *, field_name: str,
                                  parse_issues: dict[str, dict[str, Any]]) -> float | None:
        parsed = cls._parse_optional_number(value, field_name=field_name, parse_issues=parse_issues)
        if parsed is not None and parsed <= 0:
            parse_issues[field_name] = {"raw_value": value, "reason": "nonpositive_shipment_value"}
            return None
        return parsed

    @classmethod
    def proposal_from_shipment(cls, shipment: dict[str, Any], *, note: str = "",
                               source: str = "vision_ai_v1") -> PackagingProposal:
        """Adapt the small V1 shipment contract to the stable internal dual-slot model.

        Both legacy slots intentionally contain the same single AI candidate.  No
        local packaging rule or CAL asset is consulted here.
        """
        parse_issues: dict[str, dict[str, Any]] = {}
        values = {
            field: cls._positive_shipment_number(
                shipment.get(field), field_name=f"shipment.{field}", parse_issues=parse_issues,
            )
            for field in ("length_cm", "width_cm", "height_cm", "weight_g")
        }
        state = str(shipment.get("state") or "").strip()
        if _is_invalid_shipment_state(state):
            parse_issues["shipment.state"] = {"raw_value": state, "reason": "fulfillment_or_timing_info"}
            state = ""
        complete = all(value is not None for value in values.values())
        scenario_data = {
            "packaging_state": PackagingState.UNKNOWN,
            "packaging_method": state,
            **values,
            "reasoning_summary": str(note or "").strip(),
            "confidence": "medium" if complete else "low",
            "needs_review": not complete,
        }
        normal = PackagingScenario(label="AI估算", **scenario_data)
        conservative = PackagingScenario(label="当前采用", **scenario_data)
        review_reasons = []
        if not complete:
            review_reasons.append("AI发货尺寸或重量不完整，请人工填写")
        if parse_issues:
            review_reasons.append("AI发货数值未通过基础校验")
        return PackagingProposal(
            normal=normal,
            conservative=conservative,
            proposal_source=source,
            needs_review=not complete,
            review_reasons=review_reasons,
            candidate_records={"runtime_v1_validation": {"parse_issues": parse_issues}},
            engine_version="vision-runtime-v1",
            calibration_version="",
        )

    @classmethod
    def _parse_v1_payload(cls, payload: dict[str, Any], *, model: str) -> tuple[AIObservation, PackagingProposal]:
        observed = payload.get("observed") if isinstance(payload.get("observed"), dict) else {}
        dimensions = (
            observed.get("bare_dimensions_cm")
            if isinstance(observed.get("bare_dimensions_cm"), dict)
            else {}
        )
        parse_issues: dict[str, dict[str, Any]] = {}
        raw_observation = {
            "product_name": str(payload.get("product_name") or "").strip(),
            "display_product_summary": str(payload.get("product_name") or "").strip(),
            "product_cost_rmb": cls._parse_optional_number(
                observed.get("product_price_rmb"), field_name="observed.product_price_rmb",
                parse_issues=parse_issues,
            ),
            "domestic_shipping_rmb": cls._parse_optional_number(
                observed.get("page_shipping_rmb"), field_name="observed.page_shipping_rmb",
                parse_issues=parse_issues,
            ),
            "length_cm": cls._parse_optional_number(
                dimensions.get("length"), field_name="observed.bare_dimensions_cm.length",
                parse_issues=parse_issues,
            ),
            "width_cm": cls._parse_optional_number(
                dimensions.get("width"), field_name="observed.bare_dimensions_cm.width",
                parse_issues=parse_issues,
            ),
            "height_cm": cls._parse_optional_number(
                dimensions.get("height"), field_name="observed.bare_dimensions_cm.height",
                parse_issues=parse_issues,
            ),
            "weight_g": cls._parse_optional_number(
                observed.get("bare_weight_g"), field_name="observed.bare_weight_g",
                parse_issues=parse_issues,
            ),
        }
        if any(raw_observation[key] is not None for key in ("length_cm", "width_cm", "height_cm")):
            raw_observation.update(dimension_scope="product_size", dimension_value_source="image_text")
        if raw_observation["weight_g"] is not None:
            raw_observation.update(weight_scope="net_weight", weight_value_source="image_text")
        # bare_estimate: AI 推测的裸品近似值，仅在 observed 无值时作为回退
        bare_est = payload.get("bare_estimate") if isinstance(payload.get("bare_estimate"), dict) else {}
        raw_observation["bare_estimate"] = {
            "length_cm": cls._parse_optional_number(
                bare_est.get("length_cm"), field_name="bare_estimate.length_cm",
                parse_issues=parse_issues,
            ),
            "width_cm": cls._parse_optional_number(
                bare_est.get("width_cm"), field_name="bare_estimate.width_cm",
                parse_issues=parse_issues,
            ),
            "height_cm": cls._parse_optional_number(
                bare_est.get("height_cm"), field_name="bare_estimate.height_cm",
                parse_issues=parse_issues,
            ),
            "weight_g": cls._parse_optional_number(
                bare_est.get("weight_g"), field_name="bare_estimate.weight_g",
                parse_issues=parse_issues,
            ),
        }
        if raw_observation["product_cost_rmb"] is not None:
            raw_observation["product_cost_value_type"] = "exact"
        if raw_observation["domestic_shipping_rmb"] is not None:
            raw_observation["domestic_shipping_value_type"] = "exact"
        normalized_payload = dict(payload)
        if parse_issues:
            normalized_payload["numeric_parse_issues"] = parse_issues
        # --- Structural + quantity + evidence field mapping (v1.5) ---
        structure = payload.get("structure") if isinstance(payload.get("structure"), dict) else {}
        # 合法 canonical 值集合；不在此集合内的字符串 → None，不做近义词映射。
        _STRUCT_CANONICAL: dict[str, frozenset[str]] = {
            "overall_form": frozenset({
                "unknown", "soft_flat", "soft_bulky", "flexible_chain",
                "hard_flat", "hard_long", "hard_3d", "fragile_protruding", "mixed",
            }),
            "packaging_state_hint": frozenset({
                "unknown", "full_flat_fold", "strong_compression",
                "moderate_compression", "shape_retained",
            }),
            "rigidity": frozenset({"unknown", "soft", "semi_rigid", "hard"}),
            "foldability": frozenset({"unknown", "none", "limited", "good"}),
            "compressibility": frozenset({"unknown", "none", "limited", "good"}),
        }
        # packing_actions 只接受正式允许值；非法值不进入规则控制层。
        _PACKING_ACTIONS_CANONICAL = frozenset({
            "flat_fold", "roll", "coil", "compress", "nest", "disassemble", "retain_shape",
        })
        _STRUCT_STR_FIELDS = (
            "overall_form", "packaging_state_hint", "rigidity", "foldability", "compressibility",
        )
        for fld in _STRUCT_STR_FIELDS:
            val = structure.get(fld)
            if isinstance(val, str) and val.strip():
                canonical = val.strip()
                allowed = _STRUCT_CANONICAL.get(fld)
                if allowed is not None and canonical not in allowed:
                    # 非法值 → 不写入，保持默认 unknown/None
                    pass
                else:
                    raw_observation[fld] = canonical
        _STRUCT_BOOL_FIELDS = (
            "requires_shape_retention", "has_hard_bottom", "has_hard_backboard",
            "has_frame", "has_rigid_insert", "has_rigid_parts",
            "retail_box_visible", "hard_card_visible", "protrusion_flattenable",
        )
        for fld in _STRUCT_BOOL_FIELDS:
            val = structure.get(fld)
            if isinstance(val, bool):
                raw_observation[fld] = val
        _STRUCT_LIST_FIELDS = ("packing_constraints",)
        for fld in _STRUCT_LIST_FIELDS:
            val = structure.get(fld)
            if isinstance(val, list):
                cleaned = [str(v).strip() for v in val if isinstance(v, str) and str(v).strip()]
                if cleaned:
                    raw_observation[fld] = cleaned
        # packing_actions 仅接受正式允许值；非法值不进入规则控制层。
        actions = structure.get("packing_actions")
        if isinstance(actions, list):
            cleaned_actions = [
                str(v).strip() for v in actions
                if isinstance(v, str) and str(v).strip() in _PACKING_ACTIONS_CANONICAL
            ]
            if cleaned_actions:
                raw_observation["packing_actions"] = cleaned_actions
        # Quantity block：先判断一个销售单位包含什么，再判断购买数量。
        qty_block = payload.get("quantity") if isinstance(payload.get("quantity"), dict) else {}
        pq = qty_block.get("purchase_quantity")
        quantity_confirmed = isinstance(pq, int) and pq > 0
        if not quantity_confirmed and isinstance(pq, float) and pq > 0 and pq == int(pq):
            pq = int(pq)
            quantity_confirmed = True
        if quantity_confirmed:
            raw_observation["quantity"] = pq
            qs = qty_block.get("quantity_source")
            if isinstance(qs, str) and qs.strip():
                raw_observation["quantity_source"] = qs.strip()
        else:
            # 数量无法确认：shipment 按 1 个销售单位估算，但必须明确标记 assumed/unknown，
            # 不得在历史和校准数据中伪装成"真实购买数量=1"。
            raw_observation["quantity"] = 1
            raw_observation["quantity_source"] = "assumed/unknown"
        qsum = qty_block.get("quantity_summary")
        if isinstance(qsum, str) and qsum.strip():
            raw_observation["quantity_summary"] = qsum.strip()
        # Field evidence for structure booleans
        fe = payload.get("field_evidence") if isinstance(payload.get("field_evidence"), dict) else {}
        if fe:
            normalized_payload["field_evidence"] = fe
        # Snapshot observation AFTER all structural/quantity/evidence fields are mapped
        normalized_payload["observation"] = dict(raw_observation)
        observation = AIObservation.from_dict(raw_observation)
        observation.source = "vision_api"
        observation.model = model
        observation.prompt_version = cls.PROMPT_VERSION
        observation.raw_payload = normalized_payload
        shipment = payload.get("shipment") if isinstance(payload.get("shipment"), dict) else {}
        proposal = cls.proposal_from_shipment(
            shipment,
            note=str(payload.get("note") or ""),
            source="vision_ai_v1",
        )
        return observation, proposal

    @staticmethod
    def _dimension_evidence_is_not_outer_dimensions(payload: dict[str, Any], observation: AIObservation) -> bool:
        """Keep range and component measurements as evidence, never transport input."""
        invalid_scopes = {
            "adjustable_range", "component_length", "sku_range", "circumference",
            "extended_length", "bulk_carton", "display_size",
        }
        if observation.dimension_scope in invalid_scopes:
            return True
        evidence = payload.get("field_evidence", {}).get("dimensions", {})
        if not isinstance(evidence, dict):
            return False
        text = " ".join(str(evidence.get(key) or "") for key in ("raw_text", "meaning", "semantic_note")).lower()
        semantic_markers = (
            "adjustable", "range", "component", "sku", "circumference", "extended", "stretched", "bulk carton",
            "可调", "范围", "区间", "部件", "尺码", "周长", "展开", "拉伸", "外箱", "件/箱",
        )
        return any(marker in text for marker in semantic_markers) or bool(re.search(r"\d+\s*[-/~]\s*\d+", text))

    @classmethod
    def parse_payload(cls, response: dict[str, Any], *, model: str) -> tuple[AIObservation, PackagingProposal | None]:
        try:
            payload = json.loads(cls._extract_content(response))
        except json.JSONDecodeError as exc:
            raise RecognitionResponseError("视觉API返回内容不是有效JSON。") from exc
        if not isinstance(payload, dict):
            raise RecognitionResponseError("视觉API返回根节点必须是JSON对象。")
        if "observed" in payload or "shipment" in payload:
            return cls._parse_v1_payload(payload, model=model)
        raw = payload.get("observation")
        if not isinstance(raw, dict):
            raw = payload
        parse_issues: dict[str, dict[str, Any]] = {}
        observation = normalize_observation(AIObservation.from_dict(
            cls._clean_numeric_fields(raw, prefix="observation", parse_issues=parse_issues)
        ))
        if cls._dimension_evidence_is_not_outer_dimensions(payload, observation):
            observation.length_cm = observation.width_cm = observation.height_cm = None
            observation.dimension_scope = "unknown"
            payload["dimension_semantic_issue"] = "dimension_evidence_not_outer_dimensions"
        for field, type_field in (("product_cost_rmb", "product_cost_value_type"), ("domestic_shipping_rmb", "domestic_shipping_value_type")):
            if getattr(observation, field) is not None and getattr(observation, type_field) == "unknown":
                evidence = payload.get("field_evidence", {}).get(field, {})
                text = str(evidence.get("raw_text") or "").lower()
                if any(token in text for token in ("\u9884\u4f30", "estimate", "approx", "about", "\u7ea6")):
                    value_type = "estimated"
                elif any(token in text for token in ("\u8d77", "starting", "from")):
                    value_type = "starting_from"
                elif any(token in text for token in ("range", "\u533a\u95f4")):
                    value_type = "range_min"
                else:
                    value_type = "exact"
                setattr(observation, type_field, value_type)
        observation.source = "vision_api"
        observation.model = model
        observation.prompt_version = cls.PROMPT_VERSION
        proposal_raw = payload.get("packaging_proposal")
        if isinstance(proposal_raw, dict):
            proposal_raw = dict(proposal_raw)
            for scenario_name in ("normal", "conservative"):
                scenario = proposal_raw.get(scenario_name)
                if isinstance(scenario, dict):
                    proposal_raw[scenario_name] = cls._clean_numeric_fields(
                        scenario, prefix=f"packaging_proposal.{scenario_name}", parse_issues=parse_issues,
                    )
        if parse_issues:
            payload["numeric_parse_issues"] = parse_issues
        observation.raw_payload = payload
        proposal = None
        if isinstance(proposal_raw, dict) and proposal_raw.get("normal") and proposal_raw.get("conservative"):
            try:
                proposal = PackagingProposal.from_dict(proposal_raw)
            except (KeyError, TypeError, ValueError):
                proposal = None
        proposal = cls._complete_missing_visual_packaging(observation, proposal)
        return observation, proposal

    @staticmethod
    def _complete_missing_visual_packaging(observation: AIObservation,
                                           proposal: PackagingProposal | None) -> PackagingProposal | None:
        """Provide a low-confidence, outline-related candidate only after a visual omission.

        This is not a second model request and does not change arbitration.  It
        only prevents a recognizable item with measured outer dimensions from
        being treated as an unrelated fixed generic package.
        """
        if proposal and proposal.normal.is_complete() and proposal.conservative.is_complete():
            return proposal
        recognizable = bool(observation.product_name or observation.product_type or observation.product_family)
        dimensions = (observation.length_cm, observation.width_cm, observation.height_cm)
        if not recognizable or not all(value is not None and float(value) > 0 for value in dimensions):
            return proposal
        base_dims = tuple(float(value) for value in dimensions)
        form_density = {
            "soft_flat": 0.025, "soft_bulky": 0.04, "flexible_chain": 0.08,
            "hard_flat": 0.10, "hard_long": 0.10, "hard_3d": 0.12,
            "fragile_protruding": 0.09, "mixed": 0.08,
        }.get(observation.overall_form, 0.06)
        bare_weight = float(observation.weight_g) if observation.weight_g and observation.weight_g > 0 else max(20.0, base_dims[0] * base_dims[1] * base_dims[2] * form_density)
        normal_weight = bare_weight + max(20.0, min(300.0, bare_weight * 0.08))
        state = PackagingState.MODERATE_COMPRESSION
        if observation.packaging_state_hint in {item.value for item in PackagingState if item is not PackagingState.UNKNOWN}:
            state = PackagingState(observation.packaging_state_hint)
        elif "flat_fold" in (observation.packing_actions or []) or observation.overall_form in {"soft_flat", "hard_flat"}:
            state = PackagingState.FULL_FLAT_FOLD
        elif observation.requires_shape_retention is True or "retain_shape" in (observation.packing_actions or []):
            state = PackagingState.SHAPE_RETAINED
        normal_dims = tuple(round(value * 1.02, 1) for value in base_dims)
        conservative_dims = tuple(round(value * 1.08, 1) for value in base_dims)
        normal = PackagingScenario("正常档", state, "包装未展示；按结构估算", *normal_dims, normal_weight,
                                   "视觉AI包装候选缺失，按已识别外廓补全", "low", True)
        conservative = PackagingScenario("保守档", state, "包装未展示；按结构估算", *conservative_dims,
                                         max(normal_weight, normal_weight * 1.12), "视觉AI包装候选缺失，保守补全", "low", True)
        observation.raw_payload["vision_packaging_completion"] = "generated_from_recognized_outline"
        return PackagingProposal(normal, conservative, proposal_source="vision_completion", needs_review=True,
                                 review_reasons=["vision_packaging_estimate_missing"],
                                 original_scenarios=proposal.to_dict() if proposal else {})

    def _request_payload(self, *, endpoint: str, api_key: str, model: str,
                          content: list[dict[str, Any]], timeout: int,
                          cancellation: RecognitionCancellation | None,
                          response_format: dict[str, Any] | None = None,
                          provider: str = "") -> dict[str, Any]:
        body = {
            "model": model,
            "temperature": 0,
            "messages": [{"role": "user", "content": content}],
        }
        if response_format:
            body["response_format"] = response_format
        body.update(qwen_extra_body_params(provider, model))
        request = Request(
            endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                if cancellation:
                    cancellation.bind_response(response)
                if cancellation and cancellation.cancelled:
                    raise RecognitionCancelledError("AI识图已终止。")
                result = json.loads(response.read().decode("utf-8"))
                if cancellation and cancellation.cancelled:
                    raise RecognitionCancelledError("AI识图已终止。")
                return result
        except RecognitionCancelledError:
            raise
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:300]
            raise RecognitionUnavailableError(f"AI识图请求失败（HTTP {exc.code}）：{detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            if cancellation and cancellation.cancelled:
                raise RecognitionCancelledError("AI识图已终止。") from exc
            raise RecognitionUnavailableError(f"AI识图无法连接：{exc}") from exc
        except json.JSONDecodeError as exc:
            raise RecognitionResponseError("AI服务返回了无法解析的响应。") from exc
        finally:
            if cancellation:
                cancellation.clear_response()

    def recognize(self, image_items: list[dict[str, str]], *,
                  cancellation: RecognitionCancellation | None = None,
                  diagnostic_operation: DiagnosticOperation | None = None,
                  user_context: dict[str, Any] | None = None) -> tuple[AIObservation, PackagingProposal | None]:
        if cancellation and cancellation.cancelled:
            raise RecognitionCancelledError("AI识图已终止。")
        settings = self.settings_service.load()
        binding = self.profile_store.bound_profile(VISUAL_AI) if self.profile_store else None
        if binding is not None:
            profile, api_key = binding
            endpoint = self._endpoint(profile.api_url)
            model = profile.model_name
            provider = profile.provider
        else:
            endpoint = self._endpoint(str(settings.get("vision_api_endpoint") or ""))
            api_key = str(settings.get("vision_api_key") or "").strip()
            model = str(settings.get("vision_api_model") or "").strip()
            provider = "OpenAI" if urlparse(endpoint).netloc.lower() == "api.openai.com" else ""
        if not endpoint or not api_key or not model:
            raise RecognitionUnavailableError("AI识图尚未配置，请先在设置中填写API地址、密钥和模型。")

        paths = self._stable_paths(image_items)
        if not paths:
            raise RecognitionUnavailableError("没有可用于AI识图的图片。")

        uses_openai_schema = str(provider or "").strip().casefold() == "openai"
        prompt = self._prompt(len(paths), include_json_shape=not uses_openai_schema)
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        confirmed_facts = dict(user_context or {})
        # Accept the previous wrapper for callers still on the old contract, but
        # always send exactly one confirmed_facts level to the model.
        if set(confirmed_facts) == {"confirmed_facts"} and isinstance(confirmed_facts["confirmed_facts"], dict):
            confirmed_facts = dict(confirmed_facts["confirmed_facts"])
        if confirmed_facts:
            content.append({"type": "text", "text": "confirmed_facts (authoritative; do not replace): " + json.dumps(confirmed_facts, ensure_ascii=False)})
        for path in paths:
            content.append({"type": "text", "text": "证据图：请扫描全部字段；位置不代表字段职责。"})
            content.append({"type": "image_url", "image_url": {"url": self._image_data_url(path), "detail": "high"}})
        timeout = max(10, int(settings.get("vision_api_timeout_seconds", 90) or 90))
        if diagnostic_operation:
            diagnostic_operation.request(
                request_type="ai-recognition", provider_host=urlparse(endpoint).netloc,
                model=model, prompt=prompt, schema_version=self.PROMPT_VERSION,
                temperature=0, timeout_seconds=timeout,
                request_started_at=diagnostic_operation.started_at.isoformat(),
                images=[DiagnosticLogger.image_metadata(path) for path in paths],
            )
        started = time.perf_counter()
        payload: dict[str, Any] | None = None
        try:
            payload = self._request_payload(
                endpoint=endpoint, api_key=api_key, model=model,
                content=content, timeout=timeout, cancellation=cancellation,
                response_format=(
                    {"type": "json_schema", "json_schema": {
                        "name": "vision_runtime_v1", "strict": True, "schema": self.RESPONSE_SCHEMA,
                    }}
                    if uses_openai_schema else None
                ),
                provider=provider,
            )
            if diagnostic_operation:
                # Persist the sanitized provider payload before parsing so parser
                # failures retain the actual API response for diagnosis.
                diagnostic_operation.response(
                    provider_raw_response=payload,
                    normalized_result=None,
                    parse_error=None,
                    elapsed_ms=round((time.perf_counter() - started) * 1000),
                    usage=payload.get("usage", {}),
                )
            observation, proposal = self.parse_payload(payload, model=model)
        except Exception as exc:
            if diagnostic_operation:
                diagnostic_operation.response(
                    provider_raw_response=payload,
                    normalized_result=None,
                    parse_error=str(exc),
                    traceback=traceback.format_exc(),
                    elapsed_ms=round((time.perf_counter() - started) * 1000),
                    usage=payload.get("usage", {}) if payload else {},
                )
            raise
        if diagnostic_operation:
            diagnostic_operation.response(
                provider_raw_response=payload,
                normalized_result={"observation": observation.to_dict(), "external_proposal": proposal.to_dict() if proposal else None},
                parse_error=None,
                elapsed_ms=round((time.perf_counter() - started) * 1000),
                usage=payload.get("usage", {}),
            )
        return observation, proposal
