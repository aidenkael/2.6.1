"""
AliExpress Business 极简搜索采集核心

Vendored from Electronic-Commerce-Auto commit 796baaa
(product_collector/collector_core/business_source.py) - 仅做包路径适配。

技术路径：
  Playwright 打开真实搜索页 → 页面自行发出 mtop JSONP 请求
  → 监听响应 → 解析商品 → 滚动 → 页面自行请求下一页
  → 循环直到达到 target_count
"""

import asyncio
import json
import logging
import re
from typing import List
from urllib.parse import quote

from playwright.async_api import async_playwright, Response

from .models import CandidateProduct

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────

SEARCH_URL_TPL = "https://inbusiness.aliexpress.com/web/search-products?searchText={}"
SEARCH_API_MARKER = "mtop.one.shop.guide.main.search"
PAGE_SIZE = 20
RESPONSE_TIMEOUT_MS = 15_000      # 等待下一页响应
SCROLL_PAUSE_S = 2.0              # 滚动后等待


# ── 纯函数（可单测） ──────────────────────────────────────────

def parse_jsonp(text: str) -> dict | None:
    """从 JSONP 响应体中提取 JSON 对象。

    格式: callbackName({...})  或  callbackName({...});
    """
    if not text:
        return None
    text = text.strip()
    start = text.find("(")
    if start == -1:
        # 可能已经是纯 JSON
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None
    end = text.rfind(")")
    if end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start + 1 : end])
    except (json.JSONDecodeError, ValueError):
        return None


def extract_products_from_response(parsed: dict) -> list[dict]:
    """从 mtop.one.shop.guide.main.search 解析结果中提取商品列表。

    数据路径: parsed["data"]["data"] → list[dict]
    """
    try:
        return parsed["data"]["data"]
    except (KeyError, TypeError):
        return []


def standardize_url(product_id: str) -> str:
    """生成标准 AliExpress 商品链接（去除跟踪参数）。"""
    return f"https://www.aliexpress.com/item/{product_id}.html"


def is_valid(item: dict) -> bool:
    """商品四字段均非空才有效。"""
    return bool(
        item.get("itemId")
        and item.get("title")
        and item.get("itemMainPic")
        and (item.get("detailUrl") or item.get("itemUrl"))
    )


def add_products_to_results(
    raw_items: list[dict],
    keyword: str,
    results: List[CandidateProduct],
    seen_ids: set[str],
) -> tuple[int, int]:
    """将原始商品加入结果列表，返回 (added, skipped)。

    - 按 product_id 去重（保留首次出现位置）
    - 缺字段跳过
    """
    added = 0
    skipped = 0
    for item in raw_items:
        pid = item.get("itemId", "").strip()
        if not pid:
            skipped += 1
            continue
        if pid in seen_ids:
            skipped += 1
            continue
        if not is_valid(item):
            skipped += 1
            continue
        seen_ids.add(pid)
        results.append(
            CandidateProduct(
                product_id=pid,
                title=item["title"],
                main_image=item["itemMainPic"],
                product_url=standardize_url(pid),
                keyword=keyword,
                position=len(results) + 1,
            )
        )
        added += 1
    return added, skipped


# ── 采集入口 ──────────────────────────────────────────────────

async def collect(keyword: str, target_count: int = 100) -> List[CandidateProduct]:
    """
    在 AliExpress Business 搜索 keyword，采集到 target_count 个唯一有效商品后停止。

    返回按真实搜索顺序排列的 CandidateProduct 列表。
    """
    results: List[CandidateProduct] = []
    seen_ids: set[str] = set()

    search_url = SEARCH_URL_TPL.format(quote(keyword))
    expected_pages = max(3, (target_count // PAGE_SIZE) + 3)

    next_response_event = asyncio.Event()

    async def on_response(response: Response):
        if SEARCH_API_MARKER not in response.url:
            return
        try:
            body = await response.text()
        except Exception:
            return
        parsed = parse_jsonp(body)
        if not parsed:
            return
        raw_items = extract_products_from_response(parsed)
        if raw_items:
            add_products_to_results(raw_items, keyword, results, seen_ids)
            next_response_event.set()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        # 先注册监听，再导航——避免竞态
        page.on("response", on_response)

        logger.info("导航到 %s", search_url)
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=60_000)
        except Exception as e:
            logger.error("页面导航失败: %s", e)
            await browser.close()
            return results

        # 等待首页响应
        try:
            await asyncio.wait_for(next_response_event.wait(), timeout=30)
        except asyncio.TimeoutError:
            logger.warning("首页搜索响应超时")
            await browser.close()
            return results

        logger.info("首页取得 %d 个商品", len(results))

        # 滚动加载后续页
        pages_loaded = 1
        consecutive_misses = 0

        while len(results) < target_count and pages_loaded < expected_pages:
            next_response_event.clear()

            await page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
            await asyncio.sleep(SCROLL_PAUSE_S)

            try:
                await asyncio.wait_for(next_response_event.wait(), timeout=RESPONSE_TIMEOUT_MS / 1000)
                consecutive_misses = 0
                pages_loaded += 1
                logger.info("第 %d 页完成，累计 %d 个商品", pages_loaded, len(results))
            except asyncio.TimeoutError:
                consecutive_misses += 1
                logger.warning("滚动后无响应 (%d/2)", consecutive_misses)
                if consecutive_misses >= 2:
                    logger.warning("连续 2 次无新响应，停止")
                    break

        await browser.close()

    return results
