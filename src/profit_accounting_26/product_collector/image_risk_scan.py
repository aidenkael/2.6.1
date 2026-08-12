# -*- coding: utf-8 -*-
"""图片品牌/IP风险检测服务。

复用主软件视觉识别绑定的视觉 API Profile（VISUAL_AI）。
不新增 API 配置、不新增设置页面、不修改 RecognitionService。
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from profit_accounting_26.application.api_profile_store import ApiProfileStore, VISUAL_AI
from profit_accounting_26.application.recognition_service import (
    RecognitionResponseError,
    RecognitionService,
    RecognitionUnavailableError,
)

logger = logging.getLogger(__name__)

PROMPT_VERSION = "product-collector-image-risk-v1"

# 内部批处理大小（用户不可见）
BATCH_SIZE = 10


@dataclass(frozen=True, slots=True)
class ImageRiskItem:
    """单个商品的图片风险检测结果。"""

    product_id: str
    main_image: str        # 检测时的主图 URL
    has_risk: bool         # 是否检测到需要人工确认的视觉元素
    labels: list[str]      # 内部细分类：品牌Logo/品牌文字/品牌纹样/角色IP/球队组织标志
    display_label: str     # UI 显示标签：品牌/IP复核


def _build_image_prompt() -> str:
    """构建图片品牌/IP检测 Prompt。"""
    return (
        "你是商品图片品牌/IP风险识别助手。\n\n"
        "你的任务是识别图片中值得人工确认的明显视觉元素。\n"
        "注意：目标不是判断'侵权'，因为软件不知道用户是否已取得授权。\n\n"
        "请识别以下类型的视觉元素（如果存在）：\n"
        "- 清晰品牌 Logo\n"
        "- 清晰品牌名称或商标文字\n"
        "- 明显 Monogram / 重复品牌纹样\n"
        "- 明显品牌经典标识性图案\n"
        "- 动漫角色\n"
        "- 影视角色\n"
        "- 游戏角色\n"
        "- 明显人物/IP形象\n"
        "- 球队标志\n"
        "- 大学/组织标志\n"
        "- 其他明显需要授权确认的视觉元素\n\n"
        "严格限制误判：\n"
        "- 普通颜色相似不能判断\n"
        "- 普通商品造型相似不能判断\n"
        "- 普通设计风格相似不能判断\n"
        "- 普通几何纹样不能因为'像某品牌'就标记\n"
        "- 无法确认的模糊图案不要强判\n"
        "- 不输出'已侵权''侵权''违法'等法律结论\n\n"
        "严格 JSON 格式返回，每张图一个结果：\n"
        '{"results": [{"id": "商品id", "has_risk": true, "internal_labels": ["品牌Logo"], "detail": "Nike Swoosh Logo"}]}\n\n'
        "has_risk 为 false 的商品不要输出。\n"
        "internal_labels 可选值：品牌Logo、品牌文字、品牌纹样、角色IP、球队/组织标志\n"
    )


class ImageRiskScanService:
    """图片品牌/IP风险检测服务。

    复用 VISUAL_AI 绑定的视觉 API Profile。
    内存缓存：以 (product_id, main_image_url) 为键，本次运行期间有效。
    """

    PROMPT_VERSION = PROMPT_VERSION
    BATCH_SIZE = BATCH_SIZE

    def __init__(self, profile_store: ApiProfileStore) -> None:
        self.profile_store = profile_store
        # 运行期内存缓存：(product_id, main_image_url) -> ImageRiskItem
        self._cache: dict[tuple[str, str], ImageRiskItem] = {}

    @staticmethod
    def _endpoint(raw: str) -> str:
        return RecognitionService._endpoint(raw)

    def get_cached(self, product_id: str, main_image: str) -> ImageRiskItem | None:
        """查询运行期缓存。"""
        return self._cache.get((product_id, main_image))

    def _set_cached(self, product_id: str, main_image: str, item: ImageRiskItem) -> None:
        """写入运行期缓存。"""
        self._cache[(product_id, main_image)] = item

    def scan_batch(
        self,
        products: list[dict[str, str]],
    ) -> tuple[list[ImageRiskItem], int]:
        """批量检测图片风险。

        products: [{"id": "product_id", "main_image": "url"}, ...]
        返回: (results, failed_count)
        - results: 成功检测到的风险列表
        - failed_count: 检测失败的商品数量
        """
        if not products:
            return [], 0

        # 过滤已有缓存的商品
        to_scan: list[dict[str, str]] = []
        cached_results: list[ImageRiskItem] = []
        for p in products:
            pid = str(p.get("id") or "").strip()
            img = str(p.get("main_image") or "").strip()
            if not pid or not img:
                continue
            cached = self.get_cached(pid, img)
            if cached is not None:
                if cached.has_risk:
                    cached_results.append(cached)
            else:
                to_scan.append(p)

        if not to_scan:
            return cached_results, 0

        # 分批处理
        all_results: list[ImageRiskItem] = list(cached_results)
        failed_count = 0
        for i in range(0, len(to_scan), BATCH_SIZE):
            batch = to_scan[i:i + BATCH_SIZE]
            try:
                batch_results = self._scan_single_batch(batch)
                for item in batch_results:
                    self._set_cached(item.product_id, item.main_image, item)
                    if item.has_risk:
                        all_results.append(item)
            except Exception as exc:
                logger.warning("图片风险检测批次失败: %s", exc)
                failed_count += len(batch)

        return all_results, failed_count

    def _scan_single_batch(self, products: list[dict[str, str]]) -> list[ImageRiskItem]:
        """单批次图片风险检测。"""
        bound = self.profile_store.bound_profile(VISUAL_AI)
        if bound is None:
            raise RecognitionUnavailableError("图片风险检测尚未绑定视觉API配置，请先在设置中配置。")
        profile, api_key = bound
        endpoint = self._endpoint(profile.api_url)
        if not endpoint or not api_key.strip() or not profile.model_name.strip():
            raise RecognitionUnavailableError("图片风险检测API配置不完整。")

        # 下载图片并构建 content
        prompt = _build_image_prompt()
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]

        image_items: list[tuple[str, str, bytes]] = []  # (product_id, url, data)
        for p in products:
            pid = str(p.get("id") or "").strip()
            img_url = str(p.get("main_image") or "").strip()
            if not pid or not img_url:
                continue
            try:
                img_data = self._download_image(img_url)
                image_items.append((pid, img_url, img_data))
            except Exception as exc:
                logger.warning("下载图片失败 %s: %s", img_url, exc)
                continue

        if not image_items:
            return []

        # 添加图片到 content（每张图前加 id 标记）
        for pid, _url, img_data in image_items:
            content.append({"type": "text", "text": f"商品ID: {pid}"})
            b64 = base64.b64encode(img_data).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

        # 构建请求
        body: dict[str, Any] = {
            "model": profile.model_name,
            "temperature": 0,
            "messages": [{"role": "user", "content": content}],
        }
        request = Request(
            endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=180) as response:  # noqa: S310
                response_data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RecognitionUnavailableError(f"图片风险检测请求失败（HTTP {exc.code}）。") from exc
        except TimeoutError as exc:
            raise RecognitionUnavailableError("图片风险检测超时，请稍后重试。") from exc
        except (URLError, OSError) as exc:
            raise RecognitionUnavailableError(f"图片风险检测无法连接：{exc}") from exc
        except json.JSONDecodeError as exc:
            raise RecognitionResponseError("图片风险检测服务返回了无法解析的响应。") from exc

        # 解析响应
        try:
            content_text = response_data["choices"][0]["message"]["content"]
            text = str(content_text).strip()
            if text.startswith("```"):
                text = text.removeprefix("```json").removeprefix("```").strip()
                if text.endswith("```"):
                    text = text[:-3].strip()
            data = json.loads(text)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RecognitionResponseError("图片风险检测返回格式无效。") from exc

        return self._parse_results(data, image_items)

    @staticmethod
    def _download_image(url: str) -> bytes:
        """下载图片到内存（不保存）。"""
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=30) as response:  # noqa: S310
            return response.read()

    @staticmethod
    def _parse_results(
        data: Any,
        image_items: list[tuple[str, str, bytes]],
    ) -> list[ImageRiskItem]:
        """解析 AI 返回的图片风险结果。"""
        if not isinstance(data, dict):
            return []
        results_raw = data.get("results")
        if not isinstance(results_raw, list):
            return []

        # 构建 id -> url 映射
        id_to_url: dict[str, str] = {pid: url for pid, url, _ in image_items}

        results: list[ImageRiskItem] = []
        for item in results_raw:
            if not isinstance(item, dict):
                continue
            pid = str(item.get("id") or "").strip()
            if not pid or pid not in id_to_url:
                continue
            has_risk = bool(item.get("has_risk"))
            internal_labels = [
                str(lb).strip()
                for lb in (item.get("internal_labels") or [])
                if str(lb).strip()
            ]
            results.append(ImageRiskItem(
                product_id=pid,
                main_image=id_to_url[pid],
                has_risk=has_risk,
                labels=internal_labels,
                display_label="品牌/IP复核" if has_risk else "",
            ))
        return results
