from __future__ import annotations

import base64
import json
import mimetypes
import threading
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from profit_accounting_26.application.settings_service import SettingsService
from profit_accounting_26.domain.models import AIObservation, PackagingProposal


class RecognitionUnavailableError(RuntimeError):
    pass


class RecognitionResponseError(RuntimeError):
    pass


class RecognitionCancelledError(RuntimeError):
    pass


class RecognitionCancellation:
    """Thread-safe cancellation handle for a single vision request."""

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
    """OpenAI-compatible vision API boundary.

    The provider is configured in local settings. The application receives only
    the stable internal observation/proposal schema.
    """

    PROMPT_VERSION = "2.6.1-vision-slots-v2"

    def __init__(self, settings_service: SettingsService) -> None:
        self.settings_service = settings_service

    @staticmethod
    def _endpoint(raw: str) -> str:
        value = raw.strip().rstrip("/")
        if not value:
            return ""
        if value.endswith("/chat/completions"):
            return value
        return value + "/chat/completions"

    @staticmethod
    def _image_data_url(path: Path) -> str:
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    @classmethod
    def _prompt(cls, image_items: list[dict[str, str]]) -> str:
        slot_summary = "\n".join(
            f"- 图片{index + 1}：{item['type']}"
            for index, item in enumerate(image_items)
        )
        return f"""
你是跨境电商商品图片识别助手。请严格依据图片框类型识别，不要臆造看不清的数据。

图片框用途：
- 主图：识别商品类型、主要材质、软硬、折叠/压缩能力、保形需求及硬结构；即使只有一张主图，也要在商品形态足够明确时给出低置信度的裸件尺寸、裸重与两档包装候选估算。
- 商品信息：优先读取标题、商品成本、国内运费、数量等明确文字。
- 尺寸/重量：优先读取长宽高、重量，并判断是裸件还是运输包装数据。

当前图片顺序：
{slot_summary}

只返回一个JSON对象，不要Markdown。格式：
{{
  "observation": {{
    "product_name": "",
    "product_type": "",
    "material": "",
    "rigidity": "unknown|soft|semi_rigid|hard",
    "foldability": "unknown|none|limited|good",
    "compressibility": "unknown|none|limited|good",
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
    "domestic_shipping_rmb": null,
    "length_cm": null,
    "width_cm": null,
    "height_cm": null,
    "weight_g": null,
    "dimension_scope": "unknown|product_size|shipping_package_size|display_size",
    "weight_scope": "unknown|net_weight|packaged_weight",
    "quantity": 1,
    "confidence": "low|medium|high"
  }},
  "packaging_proposal": null
}}

包装候选规则：
- 只要图片能辨认出具体商品形态，`packaging_proposal` 必须返回正常档与保守档，填写 `length_cm`、`width_cm`、`height_cm`、`weight_g`、`packaging_method`、`confidence` 和 `needs_review`。
- 单主图且没有尺寸、重量文字时，可作保守视觉估算，但必须使用 `confidence: "low"`、`needs_review: true`，并在 `reasoning_summary` 明确写“主图视觉估算，需复核”。
- 无法辨认商品形态时才使用null或unknown，并将 `packaging_proposal` 设为null。
- 不得输出物流费用、利润、售价或货代选择。
""".strip()

    @staticmethod
    def _extract_content(response: dict[str, Any]) -> str:
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RecognitionResponseError("视觉API返回格式不符合OpenAI兼容协议。") from exc
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") in {"text", "output_text"}:
                    parts.append(str(item.get("text") or ""))
            content = "".join(parts)
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
        text = cls._extract_content(response)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RecognitionResponseError("视觉API返回内容不是有效JSON。") from exc
        observation_raw = payload.get("observation") if isinstance(payload, dict) else None
        if not isinstance(observation_raw, dict):
            observation_raw = payload if isinstance(payload, dict) else {}
        observation = AIObservation.from_dict(observation_raw)
        observation.source = "vision_api"
        observation.model = model
        observation.prompt_version = cls.PROMPT_VERSION
        observation.raw_payload = payload
        proposal = None
        proposal_raw = payload.get("packaging_proposal") if isinstance(payload, dict) else None
        if isinstance(proposal_raw, dict) and proposal_raw.get("normal") and proposal_raw.get("conservative"):
            try:
                proposal = PackagingProposal.from_dict(proposal_raw)
            except Exception:
                proposal = None
        return observation, proposal

    @staticmethod
    def _has_complete_estimate(
        observation: AIObservation,
        proposal: PackagingProposal | None,
    ) -> bool:
        observation_complete = all(
            value is not None and float(value) > 0
            for value in (
                observation.length_cm,
                observation.width_cm,
                observation.height_cm,
                observation.weight_g,
            )
        )
        return observation_complete and proposal is not None and proposal.normal.is_complete() and proposal.conservative.is_complete()

    @staticmethod
    def _merge_observation(primary: AIObservation, supplement: AIObservation) -> AIObservation:
        """Keep first-pass facts and fill only values omitted by the model."""
        merged = AIObservation.from_dict(primary.to_dict())
        for field_name in (
            "product_name", "product_type", "material", "rigidity", "foldability", "compressibility",
            "requires_shape_retention", "has_hard_bottom", "has_hard_backboard", "has_frame",
            "has_rigid_insert", "has_rigid_parts", "retail_box_visible", "hard_card_visible",
            "protrusion_flattenable", "product_cost_rmb", "domestic_shipping_rmb", "length_cm",
            "width_cm", "height_cm", "weight_g", "dimension_scope", "weight_scope", "quantity",
        ):
            original = getattr(merged, field_name)
            replacement = getattr(supplement, field_name)
            missing = original is None or original == "" or original == "unknown" or (field_name == "quantity" and original <= 0)
            if missing and replacement not in (None, "", "unknown"):
                setattr(merged, field_name, replacement)
        merged.confidence = "low" if supplement.confidence == "low" or primary.confidence == "low" else supplement.confidence
        merged.raw_payload = {
            "initial": primary.raw_payload,
            "measurement_supplement": supplement.raw_payload,
        }
        return merged

    @staticmethod
    def _measurement_retry_prompt(observation: AIObservation) -> str:
        return f"""
上一轮已从同一商品图片识别出：商品名称={observation.product_name or observation.product_type or "未知"}；材质={observation.material or "未知"}。

现在必须补全这件商品的视觉估算，不要重复解释，也不要返回null：
- 裸件 length_cm、width_cm、height_cm、weight_g；
- packaging_proposal.normal 和 packaging_proposal.conservative 的长宽高、重量、包装方式。

这是一张可辨认的商品主图时，必须依据商品形态给出保守估算；所有估算均标记 confidence="low"、needs_review=true，reasoning_summary 写“主图视觉估算，需复核”。
只返回与首次相同 schema 的一个 JSON 对象。不得输出物流费用、利润、售价或货代选择。
""".strip()

    def _request_payload(
        self,
        *,
        endpoint: str,
        api_key: str,
        model: str,
        content: list[dict[str, Any]],
        timeout: int,
        cancellation: RecognitionCancellation | None,
    ) -> dict[str, Any]:
        body = {
            "model": model,
            "temperature": 0,
            "messages": [{"role": "user", "content": content}],
        }
        request = Request(
            endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310 - user-configured endpoint
                if cancellation:
                    cancellation.bind_response(response)
                if cancellation and cancellation.cancelled:
                    raise RecognitionCancelledError("AI识图已终止。")
                response_payload = json.loads(response.read().decode("utf-8"))
                if cancellation and cancellation.cancelled:
                    raise RecognitionCancelledError("AI识图已终止。")
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
        return response_payload

    def recognize(
        self,
        image_items: list[dict[str, str]],
        *,
        cancellation: RecognitionCancellation | None = None,
    ) -> tuple[AIObservation, PackagingProposal | None]:
        if cancellation and cancellation.cancelled:
            raise RecognitionCancelledError("AI识图已终止。")
        settings = self.settings_service.load()
        endpoint = self._endpoint(str(settings.get("vision_api_endpoint") or ""))
        api_key = str(settings.get("vision_api_key") or "").strip()
        model = str(settings.get("vision_api_model") or "").strip()
        if not endpoint or not api_key or not model:
            raise RecognitionUnavailableError("AI识图尚未配置，请先在“设置”中填写API地址、密钥和模型。")
        valid_items: list[dict[str, str]] = []
        for item in image_items:
            path = Path(str(item.get("path") or ""))
            if path.is_file():
                valid_items.append({"path": str(path), "type": str(item.get("type") or "主图")})
        if not valid_items:
            raise RecognitionUnavailableError("没有可用于AI识图的图片。")

        content: list[dict[str, Any]] = [{"type": "text", "text": self._prompt(valid_items)}]
        for item in valid_items:
            path = Path(item["path"])
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self._image_data_url(path), "detail": "high"},
                }
            )
        timeout = max(10, int(settings.get("vision_api_timeout_seconds", 90) or 90))
        response_payload = self._request_payload(
            endpoint=endpoint,
            api_key=api_key,
            model=model,
            content=content,
            timeout=timeout,
            cancellation=cancellation,
        )
        observation, proposal = self.parse_payload(response_payload, model=model)
        main_image_only = len(valid_items) == 1 and valid_items[0]["type"] == "主图"
        if main_image_only and not self._has_complete_estimate(observation, proposal):
            retry_content = [{"type": "text", "text": self._measurement_retry_prompt(observation)}]
            retry_content.extend(content[1:])
            supplement_payload = self._request_payload(
                endpoint=endpoint,
                api_key=api_key,
                model=model,
                content=retry_content,
                timeout=timeout,
                cancellation=cancellation,
            )
            supplement, supplement_proposal = self.parse_payload(supplement_payload, model=model)
            observation = self._merge_observation(observation, supplement)
            if supplement_proposal is not None:
                proposal = supplement_proposal
        return observation, proposal
