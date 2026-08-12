# -*- coding: utf-8 -*-
"""标题风险快筛服务。

复用主软件"按修正重估"绑定的文字 API Profile（LOCAL_REESTIMATE）。
不新增 API 配置、不新增设置页面、不修改 LocalReestimateService。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from profit_accounting_26.application.api_profile_store import ApiProfileStore, LOCAL_REESTIMATE
from profit_accounting_26.application.recognition_service import (
    RecognitionResponseError,
    RecognitionService,
    RecognitionUnavailableError,
)

logger = logging.getLogger(__name__)

PROMPT_VERSION = "product-collector-title-risk-v1"


@dataclass(frozen=True, slots=True)
class TitleRiskItem:
    """单个商品的风险检测结果。"""

    product_id: str
    result: str          # "禁止" | "人工复核"
    labels: list[str]    # 中文风险标签，如 ["带电", "电池充电"]
    evidence: list[str]  # 标题中的证据文字


def _build_prompt(titles: list[dict[str, str]]) -> str:
    """构建标题风险批量检测 Prompt。

    titles: [{"id": "...", "title": "..."}, ...]
    """
    items_text = json.dumps(titles, ensure_ascii=False, indent=2)
    return (
        "你是商品标题风险快筛器。\n\n"
        "只能依据标题明确文字判断。\n"
        "禁止根据品类常识、市场经验、商品通常具有的属性或可能性进行脑补。\n"
        "证据不足时不要报风险。\n\n"
        "这不是完整选品审核：\n"
        "- 不判断市场、利润、尺寸、重量；\n"
        "- 不改写标题；\n"
        "- 不判断图片侵权；\n"
        "- 不做联网查询。\n\n"
        "重点识别：\n"
        "1. 带电 / 电动 / USB供电 / 插电 / LED / 电热 / 电机\n"
        "2. 电池 / 充电 / 锂电\n"
        "3. 带磁 / 磁铁 / 磁吸 / 强磁\n"
        "4. 食品 / 饮料 / 零食 / 可食用 / 入口类\n"
        "5. 明确儿童或婴幼儿玩具\n"
        "6. 液体 / 喷雾 / 胶水 / 香水 / 精油 / 粉末等高风险形态\n"
        "7. 标题本身明确提示可能涉及认证要求的商品\n"
        "8. 其他标题中明确出现的明显禁止或高风险因素\n\n"
        "儿童规则：\n"
        "- Kids / Baby / Children 单独出现不能直接判风险。\n"
        "- 儿童毛巾、收纳、发饰等普通通用生活用品不能因为使用人群文字被误杀。\n"
        "- 明确儿童玩具、婴儿玩具、电动儿童玩具等才进入风险。\n"
        "- 解压、捏捏乐、慢回弹、桌面解压等边界商品优先'人工复核'，不要直接判禁止。\n\n"
        "判断等级：\n"
        "- 禁止\n"
        "- 人工复核\n\n"
        "通过商品不要输出。\n\n"
        "严格 JSON，格式如下：\n"
        '{"risks": [{"id": "商品id", "result": "人工复核", "labels": ["带电"], "evidence": ["USB Rechargeable"]}]}\n\n'
        "以下是待检测商品标题列表：\n"
        + items_text
    )


class TitleRiskScanService:
    """标题风险批量检测服务。

    复用 LOCAL_REESTIMATE 绑定的文字 API Profile。
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
        返回: [TitleRiskItem, ...]（只包含有风险的商品）
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
        risks_raw = data.get("risks")
        if not isinstance(risks_raw, list):
            return []
        results: list[TitleRiskItem] = []
        for item in risks_raw:
            if not isinstance(item, dict):
                continue
            pid = str(item.get("id") or "").strip()
            if not pid:
                continue
            result = str(item.get("result") or "").strip()
            if result not in ("禁止", "人工复核"):
                continue
            labels = [str(lb).strip() for lb in (item.get("labels") or []) if str(lb).strip()]
            evidence = [str(ev).strip() for ev in (item.get("evidence") or []) if str(ev).strip()]
            results.append(TitleRiskItem(
                product_id=pid,
                result=result,
                labels=labels,
                evidence=evidence,
            ))
        return results
