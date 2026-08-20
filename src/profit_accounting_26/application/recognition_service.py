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

    PROMPT_VERSION = "2.6.1-visual-v2.3"
    RESPONSE_SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "required": ["product_name", "observed", "bare_estimate", "shipment", "note"],
        "properties": {
            "product_name": {"type": "string"},
            "observed": {
                "type": "object",
                "additionalProperties": False,
                "required": ["product_unit_price_rmb", "product_total_cost_rmb", "product_cost_value_type",
                             "page_shipping_rmb", "page_shipping_value_type", "bare_dimensions_cm", "bare_weight_g"],
                "properties": {
                    # 旧字段 product_price_rmb 只作解析兼容（单价语义），新合同优先 unit/total。
                    "product_price_rmb": {"type": ["number", "null"]},
                    "product_unit_price_rmb": {"type": ["number", "null"]},
                    "product_total_cost_rmb": {"type": ["number", "null"]},
                    "product_cost_value_type": {
                        "type": ["string", "null"],
                        "enum": ["exact", "estimated", "starting_from", "range_min", "unknown"],
                    },
                    "page_shipping_rmb": {"type": ["number", "null"]},
                    "page_shipping_value_type": {
                        "type": ["string", "null"],
                        "enum": ["exact", "estimated", "starting_from", "range_min", "unknown"],
                    },
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
                    "overall_form": {
                        "type": ["string", "null"],
                        "enum": ["unknown", "soft_flat", "soft_bulky", "flexible_chain",
                                 "hard_flat", "hard_long", "hard_3d", "fragile_protruding", "mixed"],
                    },
                    "packaging_state_hint": {
                        "type": ["string", "null"],
                        "enum": ["unknown", "full_flat_fold", "strong_compression",
                                 "moderate_compression", "shape_retained"],
                    },
                    "rigidity": {"type": ["string", "null"], "enum": ["unknown", "soft", "semi_rigid", "hard"]},
                    "foldability": {"type": ["string", "null"], "enum": ["unknown", "none", "limited", "good"]},
                    "compressibility": {"type": ["string", "null"], "enum": ["unknown", "none", "limited", "good"]},
                    "requires_shape_retention": {"type": ["boolean", "null"]},
                    "packing_actions": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "string",
                            "enum": ["flat_fold", "roll", "coil", "compress", "nest", "disassemble", "retain_shape"],
                        },
                    },
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
                    "quantity_unit": {"type": ["string", "null"]},
                    "quantity_summary": {"type": ["string", "null"]}
                }
            },
            "field_evidence": {
                "type": "object",
                "additionalProperties": True,
                "description": ("Located evidence. Keys are field names (e.g. has_hard_bottom, "
                                "product_total_cost_rmb, dimensions). Values follow the canonical shape "
                                "{\"source_image_index\": int, \"region\": str, \"raw_text\": str, "
                                "\"meaning\": str}: raw_text may be empty for pure visual evidence, but "
                                "source_image_index and region (or meaning) are required; never fabricate "
                                "evidence without a locatable source."),
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
   价格必须区分单价与本次购买总价：页面明确显示“已选总价/合计”等 → product_total_cost_rmb；页面只显示明确单价 → product_unit_price_rmb；不要输出旧字段 product_price_rmb（解析器只作旧兼容）。
   value_type（product_cost_value_type / page_shipping_value_type）只允许 exact / estimated / starting_from / range_min / unknown：明确选中SKU或明确合计 → exact；“约/预计/approx” → estimated；“起/起步/from” → starting_from；明确区间 → range_min（只存下限）；看不清 → unknown。不得因为数字非空就标 exact。
   作用域：bare_weight_g 表示当前页面实际购买/选择的全部商品合计净重（不含快递包装材料），不要再用数量相乘；裸品长宽高表示一个销售单位本身的自然未包装裸品尺寸，禁止裸尺寸×购买数量。

3. bare_estimate：observed 缺失时合理估算裸品长宽高/裸重（observed=页面事实，bare_estimate=AI推测，必须区分）。
   作用域：bare_estimate.weight_g 与 bare_weight_g 同一语义——当前购买全部商品合计净重（一个销售单位本身是多件套时，按整套全部组成商品净重合计），不要再乘 purchase_quantity；裸品长宽高表示一个销售单位本身的自然裸品尺寸，禁止裸尺寸×购买数量。若一个销售单位是无法用单一外廓描述的组合套装：裸尺寸允许 null，不要编造，由 shipment 结合全部商品、数量与摆放方式整体判断。

4. quantity：先理解一个销售单位包含什么，再判断购买多少销售单位（purchase_quantity）。quantity_unit 是 purchase_quantity 对应的销售单位中文简称（例如：双、件、套、个、包、盒、组、卷），从页面销售关系判断；看不清返回 null/空；不得根据商品类型猜测单位。quantity_summary 保留完整解释（如“2套，共6件”），不参与物流计算。主图多件不能直接等于套装；库存/销量/MOQ/SKU数量不能当购买数量。无法确认时：shipment 按 1 个销售单位估算，quantity_source 填 assumed/unknown。
   裸重与裸尺寸作用域见第2/3条：重量是当前购买全部商品合计净重、尺寸是一个销售单位的裸品尺寸，均不再按数量相乘。

5. shipment（重点，AI 拥有最终判断权）：基于图片、页面事实、商品材质与结构、裸品、数量，以及正常低成本电商仓库的实际发货行为，直接整体判断真实打包员最可能采取什么正常处理方式，并给出处理后的长宽高、总重量和包装/运输状态。
   先判断商品从展示状态变成真实运输状态时，哪些部分可以合理改变形态：折叠、压平/轻度压缩、卷起、嵌套/套叠、自然收纳、可拆卸部件、可转向/可贴平部件；把手、肩带、线材、软突出部分能否折下/收进主体/贴平；空腔能否自然排气；哪些是真正刚性不可改变的结构；是否易碎/易损必须保护；多件商品如何最可能共同发货。
   多件商品包装判断（硬性要求）：
   当 purchase_quantity > 1 时，必须先判断多件商品之间是否可以自然套叠、嵌套、重合、交错、贴合或部分进入彼此空腔。
   禁止把任意一个裸品尺寸直接乘 purchase_quantity 来得到运输尺寸。
   对相同或相近外形的壳状、罩状、托盘状、碗状、面具状、容器状、曲面薄壳等商品，应优先判断 nest / 自然套叠后的整体运输外廓。
   多件套叠后的厚度通常是：第一件主体厚度 + 后续每件的实际增量厚度，而不是：单件最大厚度 × 数量。
   只有存在明确物理原因证明商品无法套叠、重合或交错时，才允许运输某一轴随数量明显增长。
   输出 shipment 前必须自检：如果某一运输尺寸接近“单件尺寸 × purchase_quantity”，必须重新确认这是否来自真实不可套叠结构；若没有明确依据，重新估算多件共同包装方式。
   在两个极端之间正常判断：不过度保形（不无依据塞满填充物、纸箱完全保形），也不无依据做损伤商品的极端压缩。
   目标是"正常真实仓库最可能怎么发"，不是"最安全怎么发"，也不是"最极限省体积怎么发"。
   shipment.state 直接写最可能行为，同时描述主要物理形态、处理方式与包装方式，例如：自然压平后袋装、轻度压缩袋装、自然折叠后袋装、保持主体形状后袋装、保持形状后箱装。
   禁止：发货时效、包邮、货代、CAL、体积重、利润。禁止裸尺寸×数量、机械放大 L/W/H、固定压缩率。
   shipment.weight_g 不得小于当前全部商品裸重（当前购买总净重）；仍按当前全部购买数量整体判断最终运输尺寸与总重量。

6. structure（辅助观察，有明确证据才记录，无证据 null/unknown）：只输出以下正式值，不要输出其它写法——
   rigidity：soft / semi_rigid / hard；foldability 与 compressibility：none / limited / good；
   packaging_state_hint：full_flat_fold / strong_compression / moderate_compression / shape_retained；
   packing_actions：flat_fold / roll / coil / compress / nest / disassemble / retain_shape（自然叠放/堆叠用 shipment.state 描述，不要输出 stack）。
   requires_shape_retention、protrusion_flattenable（把手/肩带/线材/软突出部分能否折下、收进或贴平而不改变刚性主体）、硬底/硬背板/框架/硬内衬/原盒/硬卡按实际证据判断。
   不得因为"看起来挺括"自动推出 requires_shape_retention=true；不得因为 semi_rigid 自动推出不能压缩。硬结构与保形判断需要真实图片/页面证据，并在 field_evidence 定位。
   field_evidence 统一格式：{{"source_image_index": 图序号, "region": "区域", "raw_text": "页面原文(可空)", "meaning": "含义"}}；纯视觉证据 raw_text 可空，但必须有 source_image_index 与 region/meaning；无明确证据不要伪造 evidence。
   structure 只作辅助记录，不得机械推导 shipment。

7. note：仅必要补充。

通用原则：
- 用户确认事实最高优先，不得修改。
- 页面/图片明确事实高于 AI 推测。
- 展示态≠运输态：图片为展示而撑起、立起、展开的状态，不能自动视为物流运输外轮廓。把手立起、肩带展开、软边缘展开、空腔撑开、可折部件张开、可拆配件外挂、为展示保持立体——都要判断真实仓库发货时是否会折下、收进、贴平、转向、拆下、自然压平。
- 柔软轻薄商品的运输外轮廓：对于明显柔软、轻薄、柔韧、可折叠、可盘绕、可自然堆叠或可装袋收拢的商品，运输尺寸应按正常仓库实际装袋/折叠/盘绕/叠放后的紧凑运输外轮廓估算，而不是直接沿用展示图片中摊开、展开或松散摆放的占地范围。综合材质、厚薄、柔软程度、重量、销售数量、正常包装袋余量与合理折叠/盘绕方式判断最终三维尺寸。若重量与体积物理一致性明显不匹配（重量很轻、材质又明显柔软轻薄，但 shipment 仍给出很大运输体积），应重新检查是否错误沿用了展示态面积或松散状态。真正蓬松、厚实、刚性、易碎、不能过度弯折的商品，不能为了缩小体积强制压缩。
- 存在真正刚性骨架、不可逆损伤、易碎或必须保形的证据时保护；不预设压缩，也不预设保形。
- 已自然折叠/袋装/收纳状态不要无依据重新展开或再次极端处理。
- 不确定的页面事实返回 null。
""".strip()
        if not include_json_shape:
            return prompt + "\n只返回符合给定 JSON Schema 的一个 JSON 对象，不要 Markdown。"
        return prompt + "\n严格按以下 JSON 结构返回一个对象，不要 Markdown：\n" + json.dumps(
            {
              "product_name": "",
              "observed": {
                "product_unit_price_rmb": None,
                "product_total_cost_rmb": None,
                "product_cost_value_type": None,
                "page_shipping_rmb": None,
                "page_shipping_value_type": None,
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
                "protrusion_flattenable": None,
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
                "quantity_unit": None,
                "quantity_summary": None
              },
              "field_evidence": {
                "has_hard_bottom": {
                  "source_image_index": 1,
                  "region": "商品主体底部",
                  "raw_text": "",
                  "meaning": "可见硬质底板"
                }
              },
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

    # ------------------------------------------------------------------
    # v2.2 数据合同：value_type / structure 有限 alias（小型、明确、无歧义）
    # ------------------------------------------------------------------

    COST_VALUE_TYPES: frozenset[str] = frozenset({
        "exact", "estimated", "starting_from", "range_min", "unknown",
    })

    # structure 正式 canonical 值集合（Prompt / JSON 示例 / Schema / Parser / 内部存储统一）。
    STRUCT_CANONICAL: dict[str, frozenset[str]] = {
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
    PACKING_ACTIONS_CANONICAL: frozenset[str] = frozenset({
        "flat_fold", "roll", "coil", "compress", "nest", "disassemble", "retain_shape",
    })

    # 有限 alias：只映射语义明显的常见模型输出；归一后 raw 仍保留在 raw_payload。
    # 不在映射内的值 → normalized 保持 unknown + parse issue（绝不猜）。
    STRUCT_ALIASES: dict[str, dict[str, str]] = {
        "rigidity": {
            "rigid": "hard",
            "flexible": "soft",
            "medium": "semi_rigid",
            "moderate": "semi_rigid",
        },
        "foldability": {
            "highly_foldable": "good",
            "high": "good",
            "foldable": "good",
            "moderate": "limited",
            "medium": "limited",
            "not_foldable": "none",
            "non_foldable": "none",
            "no_fold": "none",
        },
        "compressibility": {
            "highly_compressible": "good",
            "high": "good",
            "compressible": "good",
            "moderate": "limited",
            "medium": "limited",
            "not_compressible": "none",
            "non_compressible": "none",
        },
        "packaging_state_hint": {
            "flat_fold": "full_flat_fold",
            "shape_retention": "shape_retained",
            "retain_shape": "shape_retained",
        },
    }
    PACKING_ACTIONS_ALIASES: dict[str, str] = {
        "rolling": "roll",
        "coiling": "coil",
        "compressing": "compress",
        "nesting": "nest",
    }

    @classmethod
    def _normalize_value_type(cls, value: Any, *, field_name: str,
                              parse_issues: dict[str, dict[str, Any]]) -> str:
        """只接受正式 value_type；非正式值 → unknown + parse issue（不猜测、不默认 exact）。"""
        if isinstance(value, str) and value.strip() in cls.COST_VALUE_TYPES:
            return value.strip()
        if value not in (None, ""):
            parse_issues[field_name] = {"raw_value": value, "reason": "non_canonical_value_type"}
        return "unknown"

    @staticmethod
    def _infer_value_type_from_evidence(evidence: Any) -> str:
        """页面原文推断 value_type；无风险信号返回 unknown（绝不默认 exact）。

        “起/起步/from” → starting_from；“约/预计/approx” → estimated；
        明确区间 → range_min。
        """
        text = ""
        if isinstance(evidence, dict):
            text = " ".join(
                str(evidence.get(key) or "") for key in ("raw_text", "meaning", "semantic_note")
            )
        lowered = text.lower()
        if any(token in lowered for token in ("estimate", "approx", "about", "around")) \
                or "约" in text or "预计" in text or "左右" in text:
            return "estimated"
        if "starting" in lowered or "from" in lowered or "起" in text:
            return "starting_from"
        if "range" in lowered or "区间" in text or bool(re.search(r"\d+\s*[-~/]\s*\d+", text)):
            return "range_min"
        return "unknown"

    @classmethod
    def _resolve_cost_value_type(cls, *, ai_value_type: Any, field_name: str,
                                 evidence: Any, parse_issues: dict[str, dict[str, Any]]) -> str:
        """AI 显式 value_type 优先（含显式 unknown）；AI 未给出时按 evidence 推断；
        再无信号 → unknown（绝不自动 exact）。"""
        if isinstance(ai_value_type, str) and ai_value_type.strip() in cls.COST_VALUE_TYPES:
            return ai_value_type.strip()
        if ai_value_type not in (None, ""):
            parse_issues[field_name] = {"raw_value": ai_value_type, "reason": "non_canonical_value_type"}
        return cls._infer_value_type_from_evidence(evidence)

    @classmethod
    def _normalize_structure_value(cls, field: str, value: Any,
                                   parse_issues: dict[str, dict[str, Any]]) -> str | None:
        """structure 字符串字段归一：canonical 直通 → 有限 alias → 否则 None + parse issue。"""
        if not isinstance(value, str) or not value.strip():
            return None
        raw = value.strip()
        canonical = cls.STRUCT_CANONICAL.get(field)
        if canonical is not None and raw in canonical:
            return raw
        alias = cls.STRUCT_ALIASES.get(field, {}).get(raw.lower())
        if alias is not None:
            return alias
        parse_issues[f"structure.{field}"] = {
            "raw_value": raw, "reason": "non_canonical_structure_value",
        }
        return None

    @classmethod
    def _parse_v1_payload(cls, payload: dict[str, Any], *, model: str) -> tuple[AIObservation, PackagingProposal]:
        observed = payload.get("observed") if isinstance(payload.get("observed"), dict) else {}
        dimensions = (
            observed.get("bare_dimensions_cm")
            if isinstance(observed.get("bare_dimensions_cm"), dict)
            else {}
        )
        parse_issues: dict[str, dict[str, Any]] = {}
        field_evidence = payload.get("field_evidence") if isinstance(payload.get("field_evidence"), dict) else {}
        # --- 商品成本（v2.2 合同）：单价 / 总价分离 ---
        # 旧字段 product_price_rmb 视为单价语义，仅旧兼容。
        unit_price = cls._parse_optional_number(
            observed.get("product_unit_price_rmb", observed.get("product_price_rmb")),
            field_name="observed.product_unit_price_rmb", parse_issues=parse_issues,
        )
        total_cost = cls._parse_optional_number(
            observed.get("product_total_cost_rmb"), field_name="observed.product_total_cost_rmb",
            parse_issues=parse_issues,
        )
        cost_value_type = cls._resolve_cost_value_type(
            ai_value_type=observed.get("product_cost_value_type"),
            field_name="observed.product_cost_value_type",
            evidence=field_evidence.get("product_cost_rmb") or field_evidence.get("product_total_cost_rmb")
            or field_evidence.get("product_unit_price_rmb"),
            parse_issues=parse_issues,
        )
        shipping_value_type = cls._resolve_cost_value_type(
            ai_value_type=observed.get("page_shipping_value_type"),
            field_name="observed.page_shipping_value_type",
            evidence=field_evidence.get("domestic_shipping_rmb") or field_evidence.get("page_shipping_rmb"),
            parse_issues=parse_issues,
        )
        raw_observation: dict[str, Any] = {
            "product_name": str(payload.get("product_name") or "").strip(),
            "display_product_summary": str(payload.get("product_name") or "").strip(),
            # product_cost_rmb 恒为“本次购买总商品成本”；在数量解析完成后统一计算。
            "product_cost_rmb": None,
            "product_cost_value_type": cost_value_type,
            "product_unit_price_rmb": unit_price,
            "product_total_cost_rmb": total_cost,
            "domestic_shipping_rmb": cls._parse_optional_number(
                observed.get("page_shipping_rmb"), field_name="observed.page_shipping_rmb",
                parse_issues=parse_issues,
            ),
            "domestic_shipping_value_type": shipping_value_type,
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
        normalized_payload = dict(payload)
        # --- Structural + quantity + evidence field mapping (v1.5 / v2.2) ---
        structure = payload.get("structure") if isinstance(payload.get("structure"), dict) else {}
        _STRUCT_STR_FIELDS = (
            "overall_form", "packaging_state_hint", "rigidity", "foldability", "compressibility",
        )
        for fld in _STRUCT_STR_FIELDS:
            normalized = cls._normalize_structure_value(fld, structure.get(fld), parse_issues=parse_issues)
            if normalized is not None:
                raw_observation[fld] = normalized
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
        # packing_actions：正式值直通，有限 alias 归一，其余丢弃并记录 parse issue（不静默丢信息）。
        actions = structure.get("packing_actions")
        if isinstance(actions, list):
            cleaned_actions: list[str] = []
            dropped_actions: list[str] = []
            for value in actions:
                if not isinstance(value, str) or not value.strip():
                    continue
                token = value.strip()
                if token in cls.PACKING_ACTIONS_CANONICAL:
                    cleaned_actions.append(token)
                elif token.lower() in cls.PACKING_ACTIONS_ALIASES:
                    cleaned_actions.append(cls.PACKING_ACTIONS_ALIASES[token.lower()])
                else:
                    dropped_actions.append(token)
            if cleaned_actions:
                raw_observation["packing_actions"] = cleaned_actions
            if dropped_actions:
                parse_issues.setdefault("structure.packing_actions", {
                    "raw_values": dropped_actions, "reason": "non_canonical_packing_action",
                })
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
        # quantity_unit：purchase_quantity 对应的销售单位中文简称（AI 判断，本地不猜）。
        qunit = qty_block.get("quantity_unit")
        if isinstance(qunit, str) and qunit.strip():
            raw_observation["quantity_unit"] = qunit.strip()
        qsum = qty_block.get("quantity_summary")
        if isinstance(qsum, str) and qsum.strip():
            raw_observation["quantity_summary"] = qsum.strip()
        # --- 商品成本最终值（规则 A-D）：product_cost_rmb 恒为本次购买总商品成本 ---
        cost_audit: dict[str, Any] = {}
        quantity_for_cost = raw_observation["quantity"] if quantity_confirmed else None
        if total_cost is not None:
            # A. 页面明确“已选总价/合计”→ 直接采用 total（无需数量）。
            raw_observation["product_cost_rmb"] = total_cost
            if unit_price is not None and quantity_for_cost is not None:
                unit_times_quantity = round(unit_price * quantity_for_cost, 2)
                if abs(unit_times_quantity - total_cost) > max(0.5, total_cost * 0.05):
                    # D. unit × quantity 与页面 total 明显数学冲突：记录 warning，不静默选错值。
                    cost_audit["unit_total_conflict"] = {
                        "unit_price": unit_price, "quantity": quantity_for_cost,
                        "unit_times_quantity": unit_times_quantity, "page_total": total_cost,
                        "adopted": "page_total",
                    }
                    parse_issues["cost.unit_total_conflict"] = {
                        "reason": "unit_times_quantity_conflicts_with_page_total",
                        **cost_audit["unit_total_conflict"],
                    }
        elif unit_price is not None and quantity_for_cost is not None:
            # B. 页面只显示明确单价 + 数量已确认：本地做确定性乘法（页面明确数字的乘法，非 AI 包装估算）。
            raw_observation["product_cost_rmb"] = round(unit_price * quantity_for_cost, 2)
        elif unit_price is not None:
            # C. 数量不确定：不得把单价伪装成本次购买总成本。
            cost_audit["unit_price_without_quantity"] = {
                "unit_price": unit_price, "reason": "quantity_unconfirmed_unit_price_not_total",
            }
            parse_issues["cost.unit_price_without_quantity"] = cost_audit["unit_price_without_quantity"]
        if cost_audit:
            normalized_payload["cost_audit"] = cost_audit
        if parse_issues:
            normalized_payload["numeric_parse_issues"] = parse_issues
        # Field evidence for structure booleans / costs
        if field_evidence:
            normalized_payload["field_evidence"] = field_evidence
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
                # v2.2：AI 未显式给 value_type 时按 evidence 推断；无风险信号保持 unknown，
                # 绝不因为数值非空就自动标 exact。
                setattr(observation, type_field, cls._infer_value_type_from_evidence(
                    payload.get("field_evidence", {}).get(field),
                ))
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
