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

    PROMPT_VERSION = "2.6.1-visual-v1.3"
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
        prompt = f"""
你是跨境电商商品图片识别助手。本次共有 {image_count} 张图片。

只完成商品识别、图片事实读取和发货判断。不要计算或推理其余事项。

逐张查看全部图片，但图片顺序和图片框类型不代表字段职责。返回：
1. product_name：简短、规范、可搜索的商品名称，不复制供应商 SEO 长标题。
2. observed：只填写图片中能可靠读到的页面价格、页面运费、裸品尺寸和裸重。看不清就返回 null；价格和运费禁止凭经验猜测；只确认部分裸尺寸时其余维度保持 null。
3. bare_estimate：当图片没有明确标注裸品尺寸或裸重时，可根据商品本身估算 bare_estimate。bare_estimate 是 AI 推测，不是图片事实。最终 shipment 判断应结合用户确认事实、图片事实及必要的 bare_estimate。
4. shipment：独立判断商品真正交给物流时最可能的外部尺寸、总重量和简短发货状态。即使图片没有标注尺寸，也应根据商品本身尽量给出一套完整判断。
shipment.state 是面向用户的一句简短"AI发货判断"，必须同时描述商品交给物流时的主要物理形态/处理状态、处理方式和简单包装方式，例如"可折叠；袋装发货"。不要只返回"折叠""压缩""保持原形"等单一处理词。
shipment.state 禁止填写发货时效、48小时发货、现货、包邮、快递速度、商家履约、物流费用、货代、CAL、体积重或利润。
如果详情页明确显示用户当前实际选择数量，shipment 必须按该数量的销售单位合并发货来判断；数量为 0、未识别、模糊或无法可靠确认时，按 1 个销售单位判断。库存、起订量、销量、规格数量等数字不是用户实际购买数量，不能据此判断 shipment。
袜子、手套等通常按双销售的商品，在页面没有相反证据时可按一双作为一个销售单位；页面明确单只、单件、几双装、几件套或多件包时，以页面事实为准。不确定一套具体包含几件时，不要凭经验猜具体件数，只按可确认的信息判断最终 shipment。
shipment 必须代表当前实际购买数量合并后的最终发货外廓、总重量和发货状态。不得将单个商品的长、宽、高机械全部乘以数量；应按叠放、折叠、套装或组合等实际可能的共同发货方式判断。
如果详情页明确显示或写明袋装、OPP 袋、盒装、吸塑、原包装或纸卡等包装方式，shipment.state 应优先遵守该页面事实。页面明确包装方式不等于页面明确包装尺寸；若包装尺寸或总重量未展示，仍可合理估算，但不得把包装方式错误当作实测包装尺寸。
5. note：仅写必要的简短补充。

confirmed_facts 是用户已经确认的数据，优先级最高，不得修改。observed 是裸品/页面事实，bare_estimate 是 AI 推测的裸品近似值（不是图片事实），shipment 是发货外廓和发货总重量，三者不得混淆。
不得输出或计算体积重、计费重、头程、固定服务费、尾程、总成本、利润、利润率、货代选择、CAL、规则编号、多候选方案或复杂分类字段。
""".strip()
        if not include_json_shape:
            return prompt + "\n只返回符合给定 JSON Schema 的一个 JSON 对象，不要 Markdown。"
        return prompt + "\n严格按以下 JSON 结构返回一个对象，不要 Markdown：\n" + json.dumps(
            {
                "product_name": "",
                "observed": {
                    "product_price_rmb": None,
                    "page_shipping_rmb": None,
                    "bare_dimensions_cm": {"length": None, "width": None, "height": None},
                    "bare_weight_g": None,
                },
                "bare_estimate": {
                    "length_cm": None,
                    "width_cm": None,
                    "height_cm": None,
                    "weight_g": None,
                },
                "shipment": {
                    "length_cm": 0,
                    "width_cm": 0,
                    "height_cm": 0,
                    "weight_g": 0,
                    "state": "",
                },
                "note": "",
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
        normalized_payload["observation"] = dict(raw_observation)
        if parse_issues:
            normalized_payload["numeric_parse_issues"] = parse_issues
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
