"""
AliExpress Business 极简搜索采集核心（盲盒式跨页随机采样版）

技术路径（不变）：
  Playwright 打开真实搜索页 → 页面自行发出 mtop JSONP 请求
  → 监听响应 → 解析商品 → 滚动 → 页面自行请求下一页

V1.1 采样规则：
  1. 按目标数量 N 随机决定扫描深度 D（最多 16 页），D 一旦确定必须尽量扫完，
     不因前几页已凑够 N 而提前停止。
  2. 按页面自然流程顺序获取第 1～D 个有效搜索响应，product_id 去重形成候选池。
  3. 扫完后从整个候选池 random.sample 抽 N 个；不足则全部返回并标记 partial。
  4. 最终列表 shuffle 后返回；seed、深度、每页统计写入日志。

不逆向/构造/replay 动态 sign，不引入权重抽样。
"""

import asyncio
import json
import logging
import random
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List
from urllib.parse import quote

from playwright.async_api import async_playwright, Response

from .models import CandidateProduct
from profit_accounting_26.shared import ensure_data_dir_allowed

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────

SEARCH_URL_TPL = "https://inbusiness.aliexpress.com/web/search-products?searchText={}"
SEARCH_API_MARKER = "mtop.one.shop.guide.main.search"
PAGE_SIZE = 20
RESPONSE_TIMEOUT_MS = 15_000      # 等待下一页响应
FIRST_RESPONSE_TIMEOUT_S = 30     # 等待首页响应
SCROLL_PAUSE_S = 2.0              # 滚动后等待
MAX_CONSECUTIVE_MISSES = 2        # 连续无新响应次数上限

STATUS_SUCCESS = "success"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"


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


def planned_pages_for(target_count: int, rng: random.Random) -> int:
    """按目标数量随机决定扫描深度（盲盒式，最多 18 页）。"""
    if target_count <= 10:
        return rng.randint(4, 8)
    if target_count <= 30:
        return rng.randint(6, 10)
    if target_count <= 60:
        return rng.randint(8, 12)
    if target_count <= 80:
        return rng.randint(10, 14)
    if target_count <= 100:
        return rng.randint(12, 16)
    if target_count <= 120:
        return rng.randint(14, 18)
    return rng.randint(16, 18)


def finalize_sample(
    pool: List[CandidateProduct], target_count: int, rng: random.Random
) -> tuple[List[CandidateProduct], bool]:
    """从候选池抽样 N 个并 shuffle，返回 (samples, partial)。

    候选不足 N 时全部返回并标记 partial，不伪装 success。
    """
    if len(pool) >= target_count:
        samples = rng.sample(pool, target_count)
        rng.shuffle(samples)
        return samples, False
    samples = list(pool)
    rng.shuffle(samples)
    return samples, True


def determine_status(
    forced_failed: bool,
    pool_size: int,
    actual_pages: int,
    planned_pages: int,
    product_count: int,
    target_count: int,
) -> str:
    """根据扫描深度和商品数量判定采集状态。

    - 强制失败或 0 商品 → failed
    - 完成计划深度且商品达标 → success
    - 其余有商品情况 → partial
    """
    if forced_failed or pool_size == 0:
        return STATUS_FAILED
    if actual_pages >= planned_pages and product_count >= target_count:
        return STATUS_SUCCESS
    return STATUS_PARTIAL


# ── 结构化结果 ────────────────────────────────────────────────

@dataclass
class PageStat:
    """单次搜索响应（一页）的统计。"""

    page: int
    raw_count: int = 0
    new_valid: int = 0
    skipped: int = 0


@dataclass
class CollectionReport:
    """结构化采集结果：UI 用它区分 success / partial / failed。"""

    products: List[CandidateProduct]
    status: str
    keyword: str
    target_count: int
    planned_pages: int = 0
    actual_pages: int = 0
    candidate_count: int = 0
    elapsed_seconds: float = 0.0
    seed: int = 0
    end_reason: str = ""
    page_stats: List[PageStat] = field(default_factory=list)


def default_log_dir() -> Path:
    """独立运行默认日志目录：product_collector/logs/。宿主可传 log_dir 覆盖。"""
    return Path(__file__).resolve().parent.parent / "logs"


def _write_task_log(
    log_dir: Path | str | None,
    report: CollectionReport,
    start_wall: datetime,
    traceback_text: str,
) -> None:
    """把单次任务统计写入 logs/collect_<时间戳>.log。

    只记统计信息，不保存整页 HTML、完整响应正文或商品图片。

    数据目录生命周期守卫（与主软件同一规则）：宿主注入的日志目录位于
    数据目录内（<数据目录>/product_collector，见页面 set_log_dir 契约），
    该数据目录已被 location.json 抛弃且被删除时，本函数走下方既有
    “日志失败不影响采集结果”降级路径，绝不重建废弃目录；数据目录
    有效或为独立运行默认目录时照常写日志。
    """
    try:
        directory = Path(log_dir) if log_dir else default_log_dir()
        ensure_data_dir_allowed(directory.parent)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"collect_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.log"
        lines = [
            f"start_time: {start_wall.isoformat(timespec='seconds')}",
            f"end_time: {datetime.now().isoformat(timespec='seconds')}",
            f"keyword: {report.keyword}",
            f"target_count: {report.target_count}",
            f"seed: {report.seed}",
            f"planned_pages: {report.planned_pages}",
            f"actual_pages: {report.actual_pages}",
        ]
        for stat in report.page_stats:
            lines.append(
                f"page {stat.page}: raw={stat.raw_count} "
                f"new_valid={stat.new_valid} skipped={stat.skipped}"
            )
        lines += [
            f"candidate_pool: {report.candidate_count}",
            f"final_sample: {len(report.products)}",
            f"elapsed_seconds: {report.elapsed_seconds:.1f}",
            f"status: {report.status}",
            f"end_reason: {report.end_reason}",
        ]
        if traceback_text:
            lines.append("traceback:")
            lines.append(traceback_text)
        path.write_text("\n".join(lines), encoding="utf-8")
    except Exception as e:  # 日志失败不影响采集结果
        logger.warning("写入任务日志失败: %s", e)


# ── 采集入口 ──────────────────────────────────────────────────

async def collect_with_report(
    keyword: str,
    target_count: int = 100,
    seed: int | None = None,
    log_dir: Path | str | None = None,
) -> CollectionReport:
    """盲盒式跨页随机采样采集，返回结构化报告。

    - seed 为 None 时随机生成；固定 seed 可复现扫描深度与抽样。
    - 技术失败（导航失败/首响应超时/异常/0 候选）返回 status=failed，
      而不是伪装成 0 件成功。
    """
    start_mono = time.monotonic()
    start_wall = datetime.now()
    actual_seed = seed if seed is not None else random.randrange(1, 2**31 - 1)
    rng = random.Random(actual_seed)
    planned = planned_pages_for(target_count, rng)

    pool: List[CandidateProduct] = []
    seen_ids: set[str] = set()
    page_stats: List[PageStat] = []
    end_reason = ""
    traceback_text = ""
    forced_failed = False

    def build_report() -> CollectionReport:
        elapsed = time.monotonic() - start_mono
        samples, _ = finalize_sample(pool, target_count, rng)
        status = determine_status(
            forced_failed, len(pool), len(page_stats), planned,
            len(samples), target_count,
        )
        return CollectionReport(
            products=samples,
            status=status,
            keyword=keyword,
            target_count=target_count,
            planned_pages=planned,
            actual_pages=len(page_stats),
            candidate_count=len(pool),
            elapsed_seconds=elapsed,
            seed=actual_seed,
            end_reason=end_reason,
            page_stats=page_stats,
        )

    def finish(reason: str) -> CollectionReport:
        nonlocal end_reason
        end_reason = reason
        report = build_report()
        _write_task_log(log_dir, report, start_wall, traceback_text)
        return report

    response_event = asyncio.Event()
    search_url = SEARCH_URL_TPL.format(quote(keyword))

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
        if not raw_items:
            return
        stat = PageStat(page=len(page_stats) + 1, raw_count=len(raw_items))
        added, skipped = add_products_to_results(raw_items, keyword, pool, seen_ids)
        stat.new_valid = added
        stat.skipped = skipped
        page_stats.append(stat)
        response_event.set()

    browser = None
    try:
        async with async_playwright() as pw:
            # 浏览器启动层：使用系统安装的 Microsoft Edge Stable（channel="msedge"），
            # 不写死路径/版本号、不下载浏览器、不连接用户 Profile；
            # 每次采集独立启动、独立会话，采集完成后只关闭本次启动的浏览器。
            launch_mono = time.monotonic()
            try:
                browser = await pw.chromium.launch(channel="msedge", headless=True)
            except Exception:
                logger.error("浏览器启动失败：未检测到 Microsoft Edge")
                return finish("未检测到 Microsoft Edge，无法启动商品采集。")
            launch_elapsed = time.monotonic() - launch_mono
            logger.info("Edge 启动完成 (%.1fs)", launch_elapsed)

            page = await browser.new_page()

            # 先注册监听，再导航——避免竞态
            page.on("response", on_response)

            logger.info("导航到 %s (seed=%s, 计划深度=%d)", search_url, actual_seed, planned)
            goto_mono = time.monotonic()
            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=60_000)
            except Exception as e:
                logger.error("页面导航失败: %s", e)
                return finish(f"页面导航失败: {type(e).__name__}")
            goto_elapsed = time.monotonic() - goto_mono

            # 诊断：确认导航后实际 URL 和 title（排查 about:blank / 首次启动异常）
            try:
                actual_url = page.url
                page_title = await page.title()
            except Exception:
                actual_url = "<无法获取>"
                page_title = "<无法获取>"
            logger.info(
                "goto 完成 (%.1fs): url=%s, title=%s",
                goto_elapsed, actual_url[:120], page_title[:80],
            )

            # 等待首页响应
            try:
                await asyncio.wait_for(response_event.wait(), timeout=FIRST_RESPONSE_TIMEOUT_S)
            except asyncio.TimeoutError:
                # 超时前记录最终页面状态（诊断首次失败根因）
                try:
                    final_url = page.url
                    final_title = await page.title()
                except Exception:
                    final_url = "<无法获取>"
                    final_title = "<无法获取>"
                logger.warning(
                    "首页搜索响应超时 (final_url=%s, title=%s, page_stats=%d)，"
                    "尝试同一浏览器内轻量重试",
                    final_url[:120], final_title[:80], len(page_stats),
                )
                # 同一浏览器内轻量重试：关闭旧 page，新建 page 重新导航。
                # 浏览器已"预热"（TLS/进程已初始化），第二次通常能正常响应。
                # 不复用旧 page 是因为其内部状态可能已损坏。
                try:
                    await page.close()
                except Exception:
                    pass
                response_event.clear()
                retry_page = await browser.new_page()
                retry_page.on("response", on_response)
                try:
                    await retry_page.goto(
                        search_url, wait_until="domcontentloaded", timeout=60_000
                    )
                    await asyncio.wait_for(
                        response_event.wait(), timeout=FIRST_RESPONSE_TIMEOUT_S
                    )
                    # 重试成功：替换 page 引用以继续后续滚动
                    page = retry_page
                    logger.info("同浏览器重试成功，继续采集")
                except Exception as retry_err:
                    logger.warning("同浏览器重试也失败: %s", retry_err)
                    return finish("首个有效搜索响应超时（重试未解决）")

            logger.info("首页取得 %d 个新商品", page_stats[-1].new_valid)

            # 滚动加载后续页：深度先确定，必须尽量扫完，不提前因凑够 N 停止
            consecutive_misses = 0
            while len(page_stats) < planned:
                response_event.clear()
                await page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                await asyncio.sleep(SCROLL_PAUSE_S)
                try:
                    await asyncio.wait_for(
                        response_event.wait(), timeout=RESPONSE_TIMEOUT_MS / 1000
                    )
                    consecutive_misses = 0
                    logger.info(
                        "第 %d/%d 页完成，候选池 %d", len(page_stats), planned, len(pool)
                    )
                except asyncio.TimeoutError:
                    consecutive_misses += 1
                    logger.warning(
                        "滚动后无响应 (%d/%d)", consecutive_misses, MAX_CONSECUTIVE_MISSES
                    )
                    if consecutive_misses >= MAX_CONSECUTIVE_MISSES:
                        return finish("连续无新响应，提前结束扫描")

            return finish("完成计划扫描深度")
    except Exception:
        traceback_text = traceback.format_exc()
        logger.error("采集异常:\n%s", traceback_text)
        forced_failed = True
        report = build_report()
        report.end_reason = "采集过程发生异常"
        _write_task_log(log_dir, report, start_wall, traceback_text)
        return report
    finally:
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass


async def collect(keyword: str, target_count: int = 100) -> List[CandidateProduct]:
    """兼容旧接口：返回商品列表。

    注意：技术失败同样返回空列表；需要区分失败与 0 结果请使用
    ``collect_with_report``。
    """
    report = await collect_with_report(keyword, target_count)
    return report.products
