# -*- coding: utf-8 -*-
"""图片品牌/IP风险检测服务。

使用独立的图片检测 API binding（IMAGE_RISK）。
不修改 RecognitionService。

风险三档：none / platform / infringement。
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

from profit_accounting_26.application.api_profile_store import ApiProfileStore, IMAGE_RISK
from profit_accounting_26.application.qwen_request_params import qwen_extra_body_params
from profit_accounting_26.application.recognition_service import (
    RecognitionResponseError,
    RecognitionService,
    RecognitionUnavailableError,
)

logger = logging.getLogger(__name__)

PROMPT_VERSION = "product-collector-image-risk-v2"

# 内部批处理大小（用户不可见）
BATCH_SIZE = 10

# 合法风险值
_VALID_RISKS = frozenset({"none", "platform", "infringement"})


@dataclass(frozen=True, slots=True)
class ImageRiskItem:
    """单个商品的图片风险检测结果。"""

    product_id: str
    main_image: str        # 检测时的主图 URL
    risk: str              # "none" | "platform" | "infringement"
    reason: str            # 简短中文原因


@dataclass(frozen=True, slots=True)
class ImageRiskScanStats:
    """图片风险检测统计。"""

    requested_count: int     # 用户请求检测的商品总数
    cached_count: int        # 从运行期缓存中获取的数量
    checked_count: int       # 实际通过 API 检测的数量
    risk_count: int          # 检测到风险的数量
    failed_count: int        # 检测失败的数量


def _build_image_prompt() -> str:
    """构建图片风险检测 Prompt。"""
    return (
        "你是商品图片风险识别助手。\n\n"
        "定位：弱视觉模型完成'明显风险快筛'。\n"
        "只能依据图片明确可见内容。\n\n"
        "infringement 风险：\n"
        "- 清晰 Logo；\n"
        "- 品牌文字；\n"
        "- 明显 Monogram / 品牌重复纹样；\n"
        "- 明显经典品牌标志；\n"
        "- 动漫/影视/游戏 IP；\n"
        "- 明星/人物肖像；\n"
        "- 球队、大学、组织 Logo；\n"
        "- 其它明显需授权视觉元素。\n\n"
        "platform 风险：\n"
        "- 明显枪支/武器/高危刀具/爆炸物；\n"
        "- 烟草/电子烟/毒品/吸毒工具；\n"
        "- 明显色情成人内容；\n"
        "- 赌博；\n"
        "- 明显政治敏感；\n"
        "- 极端主义/仇恨/恐怖主义；\n"
        "- 明显宗教敏感元素；\n"
        "- 明显危险品/禁售品；\n"
        "- 其它仅凭图片已能比较明确确认的平台风险。\n\n"
        "严格防误杀：\n"
        "- 普通颜色相似 -> none\n"
        "- 普通商品造型相似 -> none\n"
        "- 普通设计风格相似 -> none\n"
        "- 普通几何纹样 -> none\n"
        "- 模糊 Logo -> none\n"
        "- '有点像某品牌' -> none\n"
        "- 必须靠猜测才能成立 -> none\n\n"
        "输出格式（严格 JSON）：\n"
        '{"results": [{"id": "商品id", "risk": "none | platform | infringement", "reason": "简短中文原因"}]}\n\n'
        "每张实际送检图片必须返回对应 id。\n"
        "当同一个商品同时满足多种风险时，只返回一个最终 risk：infringement > platform > none。\n"
        "不输出置信度、风险分、人工复核等级、Markdown、额外说明。\n"
        "reason 一句话即可，none 可以空 reason。\n"
        "品牌/IP原因：优先常用中文名 + 英文原名。\n"
        "不输出'确定侵权''违法'等法律结论。"
    )


class ImageRiskScanService:
    """图片风险检测服务。

    使用 IMAGE_RISK 绑定的 API Profile。
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
        *,
        force_refresh: bool = False,
        cancel_requested: callable | None = None,
    ) -> tuple[list[ImageRiskItem], ImageRiskScanStats, list[ImageRiskItem]]:
        """批量检测图片风险。

        products: [{"id": "product_id", "main_image": "url"}, ...]
        force_refresh: True 时忽略运行期缓存，强制重新检测；新结果覆盖旧缓存。
        cancel_requested: 可选 callable，返回 True 时停止发送后续批次。
        返回: (risky_items, stats, all_checked_items)
        - risky_items: risk != "none" 的结果列表（含缓存）
        - stats: 检测统计信息
        - all_checked_items: 本次通过 API 成功检测的所有商品（含安全）
        """
        if not products:
            return [], ImageRiskScanStats(0, 0, 0, 0, 0), []

        # 过滤缓存（force_refresh 时全部视为待检）
        to_scan: list[dict[str, str]] = []
        cached_risky: list[ImageRiskItem] = []
        cached_count = 0
        for p in products:
            pid = str(p.get("id") or "").strip()
            img = str(p.get("main_image") or "").strip()
            if not pid or not img:
                continue
            if not force_refresh:
                cached = self.get_cached(pid, img)
                if cached is not None:
                    cached_count += 1
                    if cached.risk != "none":
                        cached_risky.append(cached)
                    continue
            to_scan.append(p)

        requested_count = cached_count + len(to_scan)

        if not to_scan:
            stats = ImageRiskScanStats(
                requested_count=requested_count,
                cached_count=cached_count,
                checked_count=0,
                risk_count=len(cached_risky),
                failed_count=0,
            )
            return cached_risky, stats, []

        # 分批处理
        all_risky: list[ImageRiskItem] = list(cached_risky)
        all_checked: list[ImageRiskItem] = []
        checked_count = 0
        failed_count = 0
        for i in range(0, len(to_scan), BATCH_SIZE):
            # 取消检查：当前批自然完成后不再发送下一批
            if cancel_requested is not None and cancel_requested():
                break
            batch = to_scan[i:i + BATCH_SIZE]
            try:
                batch_results, batch_download_failed = self._scan_single_batch(batch)
                checked_count += len(batch_results)
                batch_failed = batch_download_failed + (len(batch) - batch_download_failed - len(batch_results))
                failed_count += batch_failed
                all_checked.extend(batch_results)
                for item in batch_results:
                    self._set_cached(item.product_id, item.main_image, item)
                    if item.risk != "none":
                        all_risky.append(item)
            except Exception as exc:
                logger.warning("图片风险检测批次失败: %s", exc)
                failed_count += len(batch)

        stats = ImageRiskScanStats(
            requested_count=requested_count,
            cached_count=cached_count,
            checked_count=checked_count,
            risk_count=len(all_risky),
            failed_count=failed_count,
        )
        return all_risky, stats, all_checked

    def _scan_single_batch(self, products: list[dict[str, str]]) -> tuple[list[ImageRiskItem], int]:
        """单批次图片风险检测。

        返回: (results, download_failed_count)
        - results: 成功解析的结果（已去重）
        - download_failed_count: 本批次图片下载失败的商品数量
        """
        bound = self.profile_store.bound_profile(IMAGE_RISK)
        if bound is None:
            raise RecognitionUnavailableError("图片风险检测尚未绑定图片检测API，请先在设置中配置。")
        profile, api_key = bound
        endpoint = self._endpoint(profile.api_url)
        if not endpoint or not api_key.strip() or not profile.model_name.strip():
            raise RecognitionUnavailableError("图片风险检测API配置不完整。")

        # 下载图片并构建 content
        prompt = _build_image_prompt()
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]

        image_items: list[tuple[str, str, bytes]] = []  # (product_id, url, data)
        download_failed_count = 0
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
                download_failed_count += 1

        if not image_items:
            return [], download_failed_count

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
        body.update(qwen_extra_body_params(profile.provider, profile.model_name))

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

        results = self._parse_results(data, image_items)
        return results, download_failed_count

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
        """解析 AI 返回的图片风险结果。

        未知 id 忽略；同一 id 重复返回只取第一个。
        """
        if not isinstance(data, dict):
            return []
        results_raw = data.get("results")
        if not isinstance(results_raw, list):
            return []

        # 构建 id -> url 映射（仅含本次送检的商品）
        id_to_url: dict[str, str] = {pid: url for pid, url, _ in image_items}
        seen_ids: set[str] = set()

        results: list[ImageRiskItem] = []
        for item in results_raw:
            if not isinstance(item, dict):
                continue
            pid = str(item.get("id") or "").strip()
            if not pid or pid not in id_to_url:
                continue
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            risk = str(item.get("risk") or "").strip().lower()
            if risk not in _VALID_RISKS:
                # 非法/未知 risk：跳过该条目，不生成 none，不计入安全缓存
                continue
            reason = str(item.get("reason") or "").strip()
            results.append(ImageRiskItem(
                product_id=pid,
                main_image=id_to_url[pid],
                risk=risk,
                reason=reason,
            ))
        return results
