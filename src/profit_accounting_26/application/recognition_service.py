from __future__ import annotations

import base64
import json
import mimetypes
import threading
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlparse

from profit_accounting_26.application.api_profile_store import ApiProfileStore, VISUAL_AI
from profit_accounting_26.application.settings_service import SettingsService
from profit_accounting_26.domain.models import AIObservation, PackagingProposal
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

    PROMPT_VERSION = "2.6.1-vision-missing-estimates-v4"

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

    @classmethod
    def _prompt(cls, image_count: int) -> str:
        return f"""You inspect {image_count} ecommerce images in one request. Return JSON only.
Rules: (1) scan every image; do not restrict by image slot. (2) Price and domestic shipping need visible text evidence only. (3) extract selected SKU price before range, coupon, struck-through, or starting price. (4) retain estimated and starting shipping values with their type. (5) if product is recognizable but measurements are absent, estimate bare dimensions, bare weight, and both packaging candidates at low confidence. (6) only leave all packaging values null when the product itself is unrecognizable. (7) do not calculate freight, profit, or select a forwarder. (8) keep foldability, compressibility, state hint and hard-structure fields consistent. (9) output short evidence and no reasoning prose. (10) user-confirmed values supplied in context must not be changed.
Schema: {{"observation":{{"product_name":"","product_type_raw":"","product_family_raw":"","material_raw":"","overall_form":"soft_flat|soft_bulky|flexible_chain|articulated|hard_flat|hard_long|hard_3d|hollow_crushable|fragile_protruding|mixed|unknown","packing_actions":[],"packing_constraints":[],"rigidity":"unknown|soft|semi_rigid|hard","foldability":"unknown|none|limited|good","compressibility":"unknown|none|limited|good","packaging_state_hint":"unknown|full_flat_fold|strong_compression|moderate_compression|shape_retained|bare_item","requires_shape_retention":null,"has_hard_bottom":null,"has_hard_backboard":null,"has_frame":null,"has_rigid_insert":null,"has_rigid_parts":null,"retail_box_visible":null,"hard_card_visible":null,"quantity":1,"product_cost_rmb":null,"product_cost_value_type":"exact|estimated|starting_from|range_min|unknown","domestic_shipping_rmb":null,"domestic_shipping_value_type":"exact|estimated|starting_from|range_min|unknown","length_cm":null,"width_cm":null,"height_cm":null,"weight_g":null,"dimension_value_source":"image_text|ai_visual_estimate|unknown","weight_value_source":"image_text|ai_visual_estimate|unknown","confidence":"low|medium|high"}},"money_candidates":[],"field_evidence":{{}},"packaging_proposal":{{}}}}"""
        return f"""
你是跨境电商商品图片识别助手。本次共有 {image_count} 张图片。

重要规则：
1. 不存在“主图只识别商品、信息图只识别价格”的限制。
2. 必须逐张扫描全部可见信息；字段出现在任何图片中都要识别。
3. 一次请求完成全部识别，不要求后续视觉重试。
4. 清晰文字优先于视觉猜测；无法确认时返回 null，并说明证据不足。
5. 不得输出物流费用、利润、售价建议或货代选择。

必须识别：商品名称与规范化类型、材质、软硬、折叠/压缩能力、保形和硬结构、
商品成本、国内运费、数量、尺寸、重量、尺寸/重量语义，以及正常档和保守档包装候选。

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
    "material": "",
    "material_family": "",
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
    "dimension_scope": "unknown|product_size|shipping_package_size|display_size",
    "weight_scope": "unknown|net_weight|packaged_weight|original_box_weight",
    "quantity": 1,
    "confidence": "low|medium|high"
  }},
  "field_evidence": {{
    "product_cost_rmb": {{"source_image_index": null, "raw_text": "", "confidence": "low"}},
    "domestic_shipping_rmb": {{"source_image_index": null, "raw_text": "", "confidence": "low"}},
    "dimensions": {{"source_image_index": null, "raw_text": "", "confidence": "low"}},
    "weight": {{"source_image_index": null, "raw_text": "", "confidence": "low"}}
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
Additional required behavior: `product_cost_rmb` and `domestic_shipping_rmb` must only come from visible text, but visible approximate, starting-from, or range text still must be extracted. Return `product_cost_value_type` and `domestic_shipping_value_type` as exact, estimated, starting_from, range_min, or unknown. If the product is recognizable but dimensions or weight are not printed, return low-confidence visual estimates and complete non-empty normal and conservative packaging candidates. Only leave dimensions, weight, and packaging empty when the product itself is not recognizable. Return `dimension_value_source` and `weight_value_source` as image_text, ai_visual_estimate, or unknown. Include product_type_raw, product_type_code, product_family_code and material_family_code if known.
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
        observation = normalize_observation(AIObservation.from_dict(raw))
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
        observation.raw_payload = payload
        proposal = None
        proposal_raw = payload.get("packaging_proposal")
        if isinstance(proposal_raw, dict) and proposal_raw.get("normal") and proposal_raw.get("conservative"):
            try:
                proposal = PackagingProposal.from_dict(proposal_raw)
            except (KeyError, TypeError, ValueError):
                proposal = None
        return observation, proposal

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

        paths = [Path(str(item.get("path") or "")) for item in image_items]
        paths = [path for path in paths if path.is_file()]
        if not paths:
            raise RecognitionUnavailableError("没有可用于AI识图的图片。")

        content: list[dict[str, Any]] = [{"type": "text", "text": self._prompt(len(paths))}]
        if user_context:
            content.append({"type": "text", "text": "User-confirmed values (do not replace): " + json.dumps(user_context, ensure_ascii=False)})
        for index, path in enumerate(paths, start=1):
            content.append({"type": "text", "text": f"图片{index}：请扫描全部字段，不设类型限制。"})
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
        try:
            payload = self._request_payload(
                endpoint=endpoint, api_key=api_key, model=model,
                content=content, timeout=timeout, cancellation=cancellation,
            )
            observation, proposal = self.parse_payload(payload, model=model)
        except Exception as exc:
            if diagnostic_operation:
                diagnostic_operation.response(provider_raw_response=None, normalized_result=None, parse_error=str(exc))
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
