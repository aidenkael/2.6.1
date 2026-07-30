from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from profit_accounting_26.application.api_profile_store import ApiProfileStore, LOCAL_REESTIMATE
from profit_accounting_26.application.recognition_service import RecognitionResponseError, RecognitionUnavailableError


@dataclass(frozen=True, slots=True)
class LocalReestimateResult:
    recognition_summary: str
    bare_spec: dict[str, float | None]
    normal_packaging: dict[str, Any]


class LocalReestimateService:
    """Text-only packaging reasoning; it never reads images or calculates money."""

    def __init__(self, profile_store: ApiProfileStore) -> None:
        self.profile_store = profile_store

    @staticmethod
    def _endpoint(raw: str) -> str:
        value = raw.strip().rstrip("/")
        if not value:
            return ""
        return value if value.endswith("/chat/completions") else value + "/chat/completions"

    @staticmethod
    def _context(
        *,
        original_summary: str,
        current_summary: str,
        original_bare_spec: dict[str, Any],
        adopted_bare_spec: dict[str, Any],
        original_normal_packaging: dict[str, Any],
        adopted_normal_packaging: dict[str, Any],
    ) -> str:
        payload = {
            "original_ai_result": {
                "recognition_summary": original_summary,
                "bare_spec": original_bare_spec,
                "normal_packaging": original_normal_packaging,
            },
            "current_user_data": {
                "edited_recognition_summary": current_summary,
                "adopted_bare_spec": adopted_bare_spec,
                "adopted_normal_packaging": adopted_normal_packaging,
            },
        }
        instruction = (
            "执行商品局部重估。你看不到图片。用户当前修改摘要优先于原始摘要；"
            "未涉及内容可参考原始摘要。已采纳裸规格和正常档中的非空字段是强制事实，不得修改。"
            "只返回修订摘要、裸规格和正常档；保守档由本地规则生成。"
            "不得计算物流、计费重、成本、售价、利润或选择货代。无法可靠判断的值填 null。"
            "只返回 JSON：{\"recognition_summary\":\"\",\"bare_spec\":{\"length_cm\":null,\"width_cm\":null,\"height_cm\":null,\"weight_g\":null},"
            "\"normal_packaging\":{\"packaging_method\":null,\"length_cm\":null,\"width_cm\":null,\"height_cm\":null,\"weight_g\":null,\"reason\":\"\",\"needs_review\":true}}\n"
            "输入：\n"
        )
        return instruction + json.dumps(payload, ensure_ascii=False)

    def reestimate(self, **context: Any) -> LocalReestimateResult:
        bound = self.profile_store.bound_profile(LOCAL_REESTIMATE)
        if bound is None:
            raise RecognitionUnavailableError("局部重估尚未绑定文字 API 配置。")
        profile, api_key = bound
        endpoint = self._endpoint(profile.api_url)
        if not endpoint or not api_key.strip() or not profile.model_name.strip():
            raise RecognitionUnavailableError("局部重估 API 配置不完整。")
        body = {
            "model": profile.model_name,
            "temperature": 0,
            "messages": [{"role": "user", "content": self._context(**context)}],
        }
        request = Request(
            endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:  # noqa: S310 - user-configured endpoint
                response_data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RecognitionUnavailableError(f"局部重估请求失败（HTTP {exc.code}）。") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise RecognitionUnavailableError(f"局部重估无法连接：{exc}") from exc
        except json.JSONDecodeError as exc:
            raise RecognitionResponseError("局部重估服务返回了无法解析的响应。") from exc
        try:
            content = response_data["choices"][0]["message"]["content"]
            text = str(content).strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(text)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RecognitionResponseError("局部重估返回格式无效。") from exc
        if not isinstance(data, dict):
            raise RecognitionResponseError("局部重估返回格式无效。")
        bare = data.get("bare_spec") if isinstance(data.get("bare_spec"), dict) else {}
        normal = data.get("normal_packaging") if isinstance(data.get("normal_packaging"), dict) else {}
        return LocalReestimateResult(
            recognition_summary=str(data.get("recognition_summary") or ""),
            bare_spec={key: bare.get(key) for key in ("length_cm", "width_cm", "height_cm", "weight_g")},
            normal_packaging=normal,
        )
