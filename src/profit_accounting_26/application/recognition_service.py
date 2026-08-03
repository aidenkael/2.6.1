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

    PROMPT_VERSION = "2.6.1-vision-semantic-packaging-v8"

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
    def _prompt(cls, image_count: int) -> str:
        return f"""
你是跨境电商商品图片识别助手。本次共有 {image_count} 张图片。

重要规则：
1. 不存在“主图只识别商品、信息图只识别价格”的限制。
2. 必须逐张扫描全部可见信息；字段出现在任何图片中都要识别。
3. 一次请求完成全部识别，不要求后续视觉重试。
4. 清晰文字优先于视觉猜测；无法确认时返回 null，并说明证据不足。
5. 不得输出物流费用、利润、售价建议或货代选择。

必须先根据主图、实拍图和结构图识别商品主体与各部件，再判断整体物理结构、折叠/盘绕/压缩/套叠/拆分能力，最后结合文字证据和 confirmed_facts 推算单件运输包装。
必须识别：商品名称与规范化类型、材质、包装相关摘要、整体形态、包装动作和约束、软硬、折叠/压缩能力、保形和硬结构、商品成本、国内运费、数量、尺寸、重量、尺寸/重量语义，以及正常档和保守档包装候选。

尺寸语义规则：
- 只有明确的单件三维外廓、单件运输包装或原盒三维尺寸才能填写 length_cm、width_cm、height_cm。
- 可调长度范围、不同部件长度、尺码范围、展开长度、周长、拉伸前后长度、多 SKU 规格、批量外箱和件/箱信息都不是单件三维外廓；这些数字必须写入 field_evidence.dimensions.raw_text，并将三维字段设为 null。
- 不得取范围中点、平均值或把多个部件长度拼成三维尺寸。若没有明确外廓但商品可识别，仍应依据视觉结构生成低置信包装候选。
- 包装动作必须与包装外廓一致：声明平折、盘绕、压缩、套叠或拆分时，候选外廓必须体现相应变化；没有单件盒装证据时，不得猜测包装盒、硬质包装盒、纸箱、纸盒或礼盒。
- 对 `has_hard_bottom`、`has_hard_backboard`、`has_frame`、`has_rigid_insert`、`has_rigid_parts`、`retail_box_visible`、`hard_card_visible` 返回 true 时，必须在 field_evidence.structure 中给出对应 source_image_index 和可见文字或区域定位；没有可定位证据时返回 null，不得把推断当作事实。
- 当展示尺寸可能包含把手、肩带、挂环、带子、软突出部、自然撑开厚度或展开状态时，必须在 field_evidence.transport_outline 中说明可见部位及 source_image_index；没有明确刚性/原盒事实，也没有收纳、折叠、盘绕或压缩动作时，不得把展示尺寸直接作为完整运输外廓。

价格与运费要求：
- 区分当前单价、划线价、区间价、优惠券、订单总额；优先返回当前规格可用单价。
- 国内运费为0时返回0，不得因0而返回null。
- 对价格、运费、尺寸、重量返回来源图片序号、原始文字和置信度。

只返回一个JSON对象，不要Markdown：
{{
  "observation": {{
    "product_name": "",
     "product_type": "",
     "product_family": "",
     "product_type_raw": "",
     "product_type_code": "unknown",
     "product_family_code": "unknown",
     "material": "",
     "material_family": "",
     "material_family_code": "unknown",
     "display_product_summary": "",
     "display_packaging_summary": "",
     "overall_form": "soft_flat|soft_bulky|flexible_chain|articulated|hard_flat|hard_long|hard_3d|hollow_crushable|fragile_protruding|mixed|unknown",
     "packing_actions": [],
     "packing_constraints": [],
    "rigidity": "unknown|soft|semi_rigid|hard",
    "foldability": "unknown|none|limited|good",
    "compressibility": "unknown|none|limited|good",
    "packaging_state_hint": "unknown|full_flat_fold|strong_compression|moderate_compression|shape_retained",
    "requires_shape_retention": null,
    "has_hard_bottom": null,
    "has_hard_backboard": null,
    "has_frame": null,
    "has_rigid_insert": null,
    "has_rigid_parts": null,
    "retail_box_visible": null,
    "hard_card_visible": null,
    "protrusion_flattenable": null,
    "product_cost_rmb": null,
    "product_cost_value_type": "exact|estimated|starting_from|range_min|unknown",
    "domestic_shipping_rmb": null,
    "domestic_shipping_value_type": "exact|estimated|starting_from|range_min|unknown",
    "length_cm": null,
    "width_cm": null,
    "height_cm": null,
    "weight_g": null,
    "dimension_value_source": "image_text|ai_visual_estimate|unknown",
    "weight_value_source": "image_text|ai_visual_estimate|unknown",
     "dimension_scope": "unknown|product_size|shipping_package_size|original_box_size|display_size|adjustable_range|component_length|sku_range|circumference|extended_length|bulk_carton",
    "weight_scope": "unknown|net_weight|packaged_weight|original_box_weight",
    "quantity": 1,
    "confidence": "low|medium|high"
  }},
  "field_evidence": {{
    "product_cost_rmb": {{"source_image_index": null, "raw_text": "", "confidence": "low"}},
    "domestic_shipping_rmb": {{"source_image_index": null, "raw_text": "", "confidence": "low"}},
     "dimensions": {{"source_image_index": null, "raw_text": "", "meaning": "", "semantic_note": "", "confidence": "low"}},
     "weight": {{"source_image_index": null, "raw_text": "", "confidence": "low"}},
     "structure": {{
       "has_hard_bottom": {{"source_image_index": null, "raw_text": "", "region_description": "", "confidence": "low"}},
       "has_hard_backboard": {{"source_image_index": null, "raw_text": "", "region_description": "", "confidence": "low"}},
       "has_frame": {{"source_image_index": null, "raw_text": "", "region_description": "", "confidence": "low"}},
       "has_rigid_insert": {{"source_image_index": null, "raw_text": "", "region_description": "", "confidence": "low"}},
       "has_rigid_parts": {{"source_image_index": null, "raw_text": "", "region_description": "", "confidence": "low"}},
       "retail_box_visible": {{"source_image_index": null, "raw_text": "", "region_description": "", "confidence": "low"}},
       "hard_card_visible": {{"source_image_index": null, "raw_text": "", "region_description": "", "confidence": "low"}}
     }},
     "transport_outline": {{"source_image_index": null, "raw_text": "", "visible_features": [], "region_description": "", "confidence": "low"}}
   }},
  "packaging_proposal": {{
    "normal": {{
      "label": "正常档",
      "packaging_state": "unknown|full_flat_fold|strong_compression|moderate_compression|shape_retained",
      "packaging_method": "",
      "length_cm": null, "width_cm": null, "height_cm": null, "weight_g": null,
      "reasoning_summary": "", "confidence": "low|medium|high", "needs_review": true
    }},
    "conservative": {{
      "label": "保守档",
      "packaging_state": "unknown|full_flat_fold|strong_compression|moderate_compression|shape_retained",
      "packaging_method": "",
      "length_cm": null, "width_cm": null, "height_cm": null, "weight_g": null,
      "reasoning_summary": "", "confidence": "low|medium|high", "needs_review": true
    }},
    "proposal_source": "vision_api",
    "needs_review": true,
    "review_reasons": []
  }}
}}
Additional required behavior: scan every image and Merge product, price, dimensions, weight, structure, and packaging evidence before deciding structure or packaging; do not restrict by image slot. The image sequence and image slot have no semantic meaning. confirmed_facts supplied in context are authoritative facts: do not overwrite them, use them as the starting point for packaging inference, and report only a risk if they conflict with images. `product_cost_rmb` and `domestic_shipping_rmb` (domestic shipping) must only come from visible text, but visible approximate, starting-from, or range text still must be extracted. Return `product_cost_value_type` and `domestic_shipping_value_type` as exact, estimated, starting_from, range_min, or unknown. If the product is recognizable but dimensions or weight are not printed, return low-confidence visual estimates and complete non-empty normal and conservative packaging candidates. Only leave dimensions, weight, and packaging empty when the product itself is not recognizable. Return `dimension_value_source` and `weight_value_source` as image_text, ai_visual_estimate, or unknown. Every price, shipping, dimension, and weight field must be a JSON number or null. Never put ranges, multiple values, size labels, or units in numeric fields; preserve those original strings only in `field_evidence.raw_text`. Include product_type_raw, product_type_code, product_family_code and material_family_code if known.
""".strip()

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
                         cancellation: RecognitionCancellation | None) -> dict[str, Any]:
        body = {
            "model": model,
            "temperature": 0,
            "messages": [{"role": "user", "content": content}],
        }
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
        else:
            endpoint = self._endpoint(str(settings.get("vision_api_endpoint") or ""))
            api_key = str(settings.get("vision_api_key") or "").strip()
            model = str(settings.get("vision_api_model") or "").strip()
        if not endpoint or not api_key or not model:
            raise RecognitionUnavailableError("AI识图尚未配置，请先在设置中填写API地址、密钥和模型。")

        paths = self._stable_paths(image_items)
        if not paths:
            raise RecognitionUnavailableError("没有可用于AI识图的图片。")

        content: list[dict[str, Any]] = [{"type": "text", "text": self._prompt(len(paths))}]
        if user_context:
            content.append({"type": "text", "text": "confirmed_facts (authoritative; do not replace): " + json.dumps(user_context, ensure_ascii=False)})
        for path in paths:
            content.append({"type": "text", "text": "证据图：请扫描全部字段；位置不代表字段职责。"})
            content.append({"type": "image_url", "image_url": {"url": self._image_data_url(path), "detail": "high"}})
        timeout = max(10, int(settings.get("vision_api_timeout_seconds", 90) or 90))
        if diagnostic_operation:
            diagnostic_operation.request(
                request_type="ai-recognition", provider_host=urlparse(endpoint).netloc,
                model=model, prompt=self._prompt(len(paths)), schema_version=self.PROMPT_VERSION,
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
