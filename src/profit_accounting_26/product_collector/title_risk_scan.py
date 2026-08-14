# -*- coding: utf-8 -*-
"""标题风险快筛服务。

复用主软件"按修正重估"绑定的文字 API Profile（LOCAL_REESTIMATE）。
不新增 API 配置、不新增设置页面、不修改 LocalReestimateService。

风险三档：none / platform / infringement。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from profit_accounting_26.application.api_profile_store import ApiProfileStore, LOCAL_REESTIMATE
from profit_accounting_26.application.qwen_request_params import qwen_extra_body_params
from profit_accounting_26.application.recognition_service import (
    RecognitionResponseError,
    RecognitionService,
    RecognitionUnavailableError,
)

logger = logging.getLogger(__name__)

PROMPT_VERSION = "product-collector-title-risk-v2"

# 合法风险值
_VALID_RISKS = frozenset({"none", "platform", "infringement"})


@dataclass(frozen=True, slots=True)
class TitleRiskItem:
    """单个商品的风险检测结果。"""

    product_id: str
    risk: str          # "none" | "platform" | "infringement"
    reason: str        # 简短中文原因


def _build_prompt(titles: list[dict[str, str]]) -> str:
    """构建标题风险批量检测 Prompt。

    titles: [{"id": "...", "title": "..."}, ...]
    """
    items_text = json.dumps(titles, ensure_ascii=False, indent=2)
    return (
        "你是商品标题风险快筛器。使用完整标题上下文判断。\n\n"
        "核心原则：\n"
        "- 禁止简单关键词机械触发。\n"
        "- 只能依据标题明确出现的信息。\n"
        "- 不根据'这种商品通常……'脑补。\n"
        "- Kids/Baby/Children 单独出现不能判断违规。\n"
        "- Magnetic 必须结合整个商品语义。\n"
        "- Medical/Therapy 必须结合完整标题判断。\n"
        "- 普通生活用品不能因面向儿童就误杀。\n"
        "- 普通风格词不是侵权证据。\n"
        "- 不联网。\n"
        "- 不判断物流/利润/重量/尺寸。\n"
        "- 不改写标题。\n"
        "- 不做法律定论。\n"
        "- 模糊情况返回 none。\n\n"
        "重点 platform 风险：\n"
        "- 明确武器、高危刀具、爆炸物；\n"
        "- 烟草、电子烟、毒品；\n"
        "- 食品饮料；\n"
        "- 明确药品/高风险医疗/治疗产品；\n"
        "- 当前业务排除的液体、喷雾、胶水、香水、精油、危险粉末；\n"
        "- 带电、电动、USB、充电、电池、锂电、LED、电热、电机；\n"
        "- 明确磁铁/强磁/磁性核心商品；\n"
        "- 色情成人；\n"
        "- 赌博；\n"
        "- 政治/极端/仇恨/恐怖主义；\n"
        "- 其它明确禁售/当前业务明确排除商品。\n\n"
        "儿童防误杀：\n"
        "- Kids/Baby/Children ≠ 自动风险。\n"
        "- 普通儿童毛巾、发饰、收纳、生活用品不能因此误杀。\n"
        "- 明确儿童/婴儿玩具、高风险儿童用品才判断。\n"
        "- 捏捏乐、慢回弹、桌面解压、挂件、小摆件等边界商品：没有明确违规证据时不要强判。\n\n"
        "重点 infringement 风险：\n"
        "- 明确品牌名称/商标；\n"
        "- 影视、动漫、游戏 IP；\n"
        "- 明星/名人周边；\n"
        "- 球队、大学、组织；\n"
        "- Replica / 仿 / 复制 / Inspired by 等直接关联具体品牌/IP。\n\n"
        "输出格式（严格 JSON）：\n"
        '{"results": [{"id": "商品id", "risk": "none | platform | infringement", "reason": "简短中文原因"}]}\n\n'
        "每个送检商品都必须返回且只能返回一个对应结果，包括 risk=none 的商品，不得省略安全商品。\n"
        "当同一个商品同时满足多种风险时，只返回一个最终 risk：infringement > platform > none。\n"
        "每个送检商品必须保留 id。reason 一句话即可，none 可以空 reason。\n"
        "品牌/IP原因：优先常用中文名 + 英文原名，例如：爱马仕（Hermès）、迪士尼（Disney）。\n"
        "LV、Nike 等常用写法可以直接使用。\n"
        "不输出'确定侵权''违法'等法律结论。\n\n"
        "以下是待检测商品标题列表：\n"
        + items_text
    )


class TitleRiskScanService:
    """标题风险批量检测服务。

    复用 LOCAL_REESTIMATE 绑定的文字 API Profile。
    风险三档：none / platform / infringement。
    """

    PROMPT_VERSION = PROMPT_VERSION

    def __init__(self, profile_store: ApiProfileStore) -> None:
        self.profile_store = profile_store

    @staticmethod
    def _endpoint(raw: str) -> str:
        return RecognitionService._endpoint(raw)

    def scan(self, titles: list[dict[str, str]]) -> list[TitleRiskItem]:
        """批量检测标题风险。

        titles: [{"id": "product_id", "title": "English title"}, ...]
        返回: [TitleRiskItem, ...]（包含所有返回结果，含 none）
        """
        if not titles:
            return []

        bound = self.profile_store.bound_profile(LOCAL_REESTIMATE)
        if bound is None:
            raise RecognitionUnavailableError("标题风险检测尚未绑定文字API配置，请先在设置中配置。")
        profile, api_key = bound
        endpoint = self._endpoint(profile.api_url)
        if not endpoint or not api_key.strip() or not profile.model_name.strip():
            raise RecognitionUnavailableError("标题风险检测API配置不完整。")

        uses_openai_schema = str(getattr(profile, "provider", "") or "").strip().casefold() == "openai"
        prompt = _build_prompt(titles)
        body: dict[str, Any] = {
            "model": profile.model_name,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }
        if uses_openai_schema:
            body["response_format"] = {"type": "json_object"}
        body.update(qwen_extra_body_params(profile.provider, profile.model_name))

        request = Request(
            endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=120) as response:  # noqa: S310
                response_data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RecognitionUnavailableError(f"标题风险检测请求失败（HTTP {exc.code}）。") from exc
        except TimeoutError as exc:
            raise RecognitionUnavailableError("标题风险检测超时，请稍后重试。") from exc
        except (URLError, OSError) as exc:
            raise RecognitionUnavailableError(f"标题风险检测无法连接：{exc}") from exc
        except json.JSONDecodeError as exc:
            raise RecognitionResponseError("标题风险检测服务返回了无法解析的响应。") from exc

        try:
            content = response_data["choices"][0]["message"]["content"]
            text = str(content).strip()
            if text.startswith("```"):
                text = text.removeprefix("```json").removeprefix("```").strip()
                if text.endswith("```"):
                    text = text[:-3].strip()
            data = json.loads(text)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RecognitionResponseError("标题风险检测返回格式无效。") from exc

        return self._parse_risks(data)

    @staticmethod
    def _parse_risks(data: Any) -> list[TitleRiskItem]:
        """解析 AI 返回的风险列表。"""
        if not isinstance(data, dict):
            return []
        results_raw = data.get("results")
        if not isinstance(results_raw, list):
            return []
        results: list[TitleRiskItem] = []
        for item in results_raw:
            if not isinstance(item, dict):
                continue
            pid = str(item.get("id") or "").strip()
            if not pid:
                continue
            risk = str(item.get("risk") or "").strip().lower()
            if risk not in _VALID_RISKS:
                # 非法/未知 risk：跳过该条目，不生成 none，不清除已有风险状态
                continue
            reason = str(item.get("reason") or "").strip()
            results.append(TitleRiskItem(
                product_id=pid,
                risk=risk,
                reason=reason,
            ))
        return results
