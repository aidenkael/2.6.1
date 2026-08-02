from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from profit_accounting_26.application.api_profile_store import ApiProfileStore, LOCAL_REESTIMATE
from profit_accounting_26.application.recognition_service import RecognitionResponseError, RecognitionUnavailableError
from profit_accounting_26.domain.models import PackagingProposal


@dataclass(frozen=True, slots=True)
class LocalReestimateResult:
    recognition_summary: str
    observation_patch: dict[str, Any]
    changed_fields: list[str]
    product_summary: str = ""
    packaging_summary: str = ""
    packaging_proposal: PackagingProposal | None = None
    elapsed_ms: int = 0


class LocalReestimateService:
    """Convert user text into a structured observation patch.

    It does not produce final package dimensions, calculate money, or read images.
    The local calibration engine remains the only packaging result outlet.
    """

    ALLOWED_PATCH_FIELDS = {
        "product_name", "product_type", "product_family", "material", "material_family",
        "rigidity", "foldability", "compressibility", "packaging_state_hint",
        "overall_form", "packing_actions", "packing_constraints",
        "requires_shape_retention", "has_hard_bottom", "has_hard_backboard",
        "has_frame", "has_rigid_insert", "has_rigid_parts", "retail_box_visible",
        "hard_card_visible", "protrusion_flattenable", "length_cm", "width_cm",
        "height_cm", "weight_g", "dimension_scope", "weight_scope", "quantity",
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
    def _context(cls, *, original_summary: str, current_summary: str,
                 original_observation: dict[str, Any], user_overrides: dict[str, Any],
                 adopted_normal: dict[str, Any] | None = None,
                 original_product_summary: str = "", current_product_summary: str = "",
                 original_packaging_summary: str = "", current_packaging_summary: str = "",
                 cal_summary: list[str] | None = None, rejected_candidates: dict[str, list[str]] | None = None,
                 visual_evidence: dict[str, Any] | None = None) -> str:
        payload = {
            "original_summary": original_summary,
            "edited_summary": current_summary,
            "original_observation": original_observation,
            "user_confirmed_overrides": user_overrides,
            "adopted_normal_packaging": adopted_normal or {},
            "original_product_summary": original_product_summary,
            "current_product_summary": current_product_summary,
            "original_packaging_summary": original_packaging_summary,
            "current_packaging_summary": current_packaging_summary,
            "cal_summary": cal_summary or [],
            "rejected_candidates": rejected_candidates or {},
            "first_vision_evidence": visual_evidence or {},
        }
        fields = sorted(cls.ALLOWED_PATCH_FIELDS)
        return (
            "你是商品结构字段标准化助手。你看不到图片。根据用户修改后的摘要，"
            "只返回发生变化的结构化字段补丁。用户已确认值不得修改。"
            "不要重复用户原话充当结果；不要输出包装尺寸、包装重量、费用、利润或货代。"
            "将‘深度折叠/压得很扁/完全压平’优先标准化为 foldability=good、"
            "compressibility=good、packaging_state_hint=strong_compression 或 full_flat_fold；"
            "存在硬底、框架、保形时不得同时标记完全压平。"
            f"允许字段：{fields}。"
            "根据修改后的两条摘要重新判断整体结构、包装容器/动作/保护和缺失估算；不得照抄用户文字。"
            "Treat quantity-per-carton/bag and total-carton text as bulk information, never individual packaging evidence unless it explicitly says one piece or each item."
            "Return packaging_summary as Chinese handling；final individual package type, without dimensions, weight, source, confidence, CAL IDs, risks, or internal codes."
            "返回的包装候选会经过本地校验和CAL仲裁，已确认数字不得覆盖。"
            "packaging_proposal must contain normal and conservative scenarios with packaging_method, length_cm, width_cm, height_cm, weight_g, confidence and needs_review."
            "只返回JSON：{\"recognition_summary\":\"\",\"product_summary\":\"\",\"packaging_summary\":\"\","
            "\"observation_patch\":{},\"changed_fields\":[],\"packaging_proposal\":{}}。输入：\n"
            + json.dumps(payload, ensure_ascii=False)
        )

    def reestimate(self, **context: Any) -> LocalReestimateResult:
        bound = self.profile_store.bound_profile(LOCAL_REESTIMATE)
        if bound is None:
            raise RecognitionUnavailableError("局部重估尚未绑定文字API配置。")
        profile, api_key = bound
        endpoint = self._endpoint(profile.api_url)
        if not endpoint or not api_key.strip() or not profile.model_name.strip():
            raise RecognitionUnavailableError("局部重估API配置不完整。")
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
        started = time.perf_counter()
        try:
            with urlopen(request, timeout=60) as response:  # noqa: S310
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
        raw_patch = data.get("observation_patch") if isinstance(data.get("observation_patch"), dict) else {}
        patch = {key: value for key, value in raw_patch.items() if key in self.ALLOWED_PATCH_FIELDS}
        changed = [key for key in data.get("changed_fields", []) if key in patch]
        if not changed:
            changed = list(patch)
        proposal = None
        proposal_raw = data.get("packaging_proposal")
        if isinstance(proposal_raw, dict) and proposal_raw.get("normal") and proposal_raw.get("conservative"):
            try:
                proposal = PackagingProposal.from_dict(proposal_raw)
            except (KeyError, TypeError, ValueError):
                proposal = None
        return LocalReestimateResult(
            recognition_summary=str(data.get("recognition_summary") or ""),
            observation_patch=patch,
            changed_fields=changed,
            product_summary=str(data.get("product_summary") or ""),
            packaging_summary=str(data.get("packaging_summary") or ""),
            packaging_proposal=proposal,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
        )
