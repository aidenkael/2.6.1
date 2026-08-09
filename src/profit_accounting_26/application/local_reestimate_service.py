from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from profit_accounting_26.application.api_profile_store import ApiProfileStore, LOCAL_REESTIMATE
from profit_accounting_26.application.recognition_service import (
    RecognitionResponseError,
    RecognitionService,
    RecognitionUnavailableError,
    _is_invalid_shipment_state,
)
from profit_accounting_26.domain.models import PackagingProposal, PackagingScenario


@dataclass(frozen=True, slots=True)
class LocalReestimateResult:
    shipment: PackagingScenario | None = None
    note: str = ""
    recognition_summary: str = ""
    observation_patch: dict[str, Any] | None = None
    changed_fields: list[str] | None = None
    product_summary: str = ""
    packaging_summary: str = ""
    packaging_proposal: PackagingProposal | None = None
    elapsed_ms: int = 0
    provider: str = ""
    model: str = ""
    provider_host: str = ""


class LocalReestimateService:
    """Produce one temporary shipment candidate from confirmed facts and user correction."""

    RESPONSE_SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "required": ["shipment", "note"],
        "properties": {
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

    def __init__(self, profile_store: ApiProfileStore) -> None:
        self.profile_store = profile_store

    @staticmethod
    def _endpoint(raw: str) -> str:
        value = raw.strip().rstrip("/")
        if not value:
            return ""
        return value if value.endswith("/chat/completions") else value + "/chat/completions"

    @classmethod
    def _context(cls, *, product_name: str, confirmed_facts: dict[str, Any],
                 current_shipment: dict[str, Any], user_correction: str,
                 include_json_shape: bool = True,
                 **_ignored: Any) -> str:
        payload = {
            "product_name": str(product_name or "").strip(),
            "confirmed_facts": confirmed_facts,
            "current_shipment": current_shipment,
            "user_correction": str(user_correction or "").strip(),
        }
        prompt = (
            "你是跨境电商发货判断助手。你看不到图片。"
            "根据商品名称、当前已确认的裸品事实、当前采用的发货尺寸/重量和用户修正，"
            "重新判断一套最可能的实际发货状态、外部尺寸和发货总重量。"
            "shipment.state 只描述商品交给物流时的物理形态和处理方式，例如折叠、压扁、盘绕、保持原形等。"
            "禁止填写发货时效、现货、包邮、快递方式、48小时发货、商家履约信息或物流速度。"
            "用户已确认的数据不得修改。只完成发货判断，不要计算或推理其余事项。"
            "不要输出商品事实补丁、多候选方案、物流费用、利润、货代、CAL、规则编号或证据链。"
        )
        if include_json_shape:
            prompt += "严格按以下 JSON 结构返回一个对象，不要 Markdown：\n" + json.dumps(
                {
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
        else:
            prompt += "只返回符合给定 JSON Schema 的一个 JSON 对象，不要 Markdown。"
        return prompt + "\n输入：\n" + json.dumps(payload, ensure_ascii=False)

    def reestimate(self, **context: Any) -> LocalReestimateResult:
        if not str(context.get("user_correction") or "").strip():
            raise RecognitionUnavailableError("请先填写用户修正原因，再按修正重估。")
        bound = self.profile_store.bound_profile(LOCAL_REESTIMATE)
        if bound is None:
            raise RecognitionUnavailableError("按修正重估尚未绑定文字API配置。")
        profile, api_key = bound
        endpoint = self._endpoint(profile.api_url)
        if not endpoint or not api_key.strip() or not profile.model_name.strip():
            raise RecognitionUnavailableError("按修正重估API配置不完整。")
        uses_openai_schema = str(getattr(profile, "provider", "") or "").strip().casefold() == "openai"
        body = {
            "model": profile.model_name,
            "temperature": 0,
            "messages": [{"role": "user", "content": self._context(**context, include_json_shape=not uses_openai_schema)}],
        }
        if uses_openai_schema:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "corrected_shipment_v1", "strict": True, "schema": self.RESPONSE_SCHEMA},
            }
        request = Request(
            endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urlopen(request, timeout=60) as response:  # noqa: S310
                response_data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RecognitionUnavailableError(f"按修正重估请求失败（HTTP {exc.code}）。") from exc
        except TimeoutError as exc:
            raise RecognitionUnavailableError("按修正重估超时，当前结果未改变，可稍后重试。") from exc
        except (URLError, OSError) as exc:
            raise RecognitionUnavailableError(f"按修正重估无法连接：{exc}") from exc
        except json.JSONDecodeError as exc:
            raise RecognitionResponseError("按修正重估服务返回了无法解析的响应。") from exc
        try:
            content = response_data["choices"][0]["message"]["content"]
            text = str(content).strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(text)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RecognitionResponseError("按修正重估返回格式无效。") from exc
        if not isinstance(data, dict):
            raise RecognitionResponseError("按修正重估返回格式无效。")
        shipment = data.get("shipment") if isinstance(data.get("shipment"), dict) else {}
        # Sanitize invalid state values (fulfillment/timing info instead of physical form).
        if _is_invalid_shipment_state(str(shipment.get("state") or "")):
            shipment["state"] = ""
        proposal = RecognitionService.proposal_from_shipment(
            shipment, note=str(data.get("note") or ""), source="corrected_reestimate_v1",
        )
        if not proposal.normal.is_complete():
            raise RecognitionResponseError("按修正重估未返回完整有效的发货尺寸和重量，当前结果未改变。")
        return LocalReestimateResult(
            shipment=proposal.normal,
            note=str(data.get("note") or ""),
            observation_patch={},
            changed_fields=[],
            packaging_proposal=proposal,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
            provider=str(getattr(profile, "provider", "") or "").strip(),
            model=str(profile.model_name or "").strip(),
            provider_host=urlparse(profile.api_url).netloc,
        )
