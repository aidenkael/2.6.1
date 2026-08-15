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
import time
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
from profit_accounting_26.product_collector import product_risk_log

logger = logging.getLogger(__name__)

PROMPT_VERSION = "product-collector-image-risk-v3"

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


def _final_status(cancelled: bool, checked_count: int, failed_count: int) -> str:
    """图片检测最终状态：取消 > 完成 > 部分失败 > 失败。"""
    if cancelled:
        return "取消"
    if failed_count == 0:
        return "完成"
    if checked_count > 0:
        return "部分失败"
    return "失败"


def _build_image_prompt() -> str:
    """构建图片风险检测 Prompt。"""
    return (
        "你是商品图片风险识别助手。\n\n"
        "定位：弱视觉模型完成'明显风险快筛'。\n"
        "只能依据图片明确可见内容判断；无法从图片确认的风险一律 none。\n\n"
        "商品标题只作为理解图片的辅助信息。\n"
        "图片风险必须有明确视觉证据；\n"
        "如果标题存在风险词但图片没有对应视觉证据，图片检测不得仅凭标题判风险。\n\n"
        "风险三档（每张图片只返回一个最终 risk）：\n"
        "- infringement：明显品牌 / IP / 商标；\n"
        "- platform：明显平台风险或内部采集排除项；\n"
        "- none：无法明确确认。\n"
        "优先级：infringement > platform > none。\n\n"
        "一、侵权风险（infringement）：\n"
        "- 清晰 Logo；\n"
        "- 品牌文字、商标文字；\n"
        "- 明显 Monogram / 品牌重复纹样；\n"
        "- 品牌经典标志；\n"
        "- 动漫 / 影视 / 游戏 IP；\n"
        "- 明星 / 名人肖像；\n"
        "- 球队、大学、组织 Logo；\n"
        "- 其它明显需授权视觉元素。\n"
        "即使模型不知道品牌具体名称，只要图片中存在明显作为品牌使用的：\n"
        "- 独立包装名称；\n"
        "- 包装 Logo；\n"
        "- 包装商标；\n"
        "- 明确品牌标识；\n"
        "也应提示侵权风险线索。\n"
        "普通装饰文字、说明文字不能因此自动报侵权。\n\n"
        "二、平台风险（platform，需明确图片证据）：\n\n"
        "1. 明显禁售实物：\n"
        "- 枪支、高危刀具、明显攻击性武器、爆炸物；\n"
        "- 毒品、吸毒工具；\n"
        "- 烟草、电子烟；\n"
        "- 赌博；\n"
        "- 明显危险品；\n"
        "- 其它仅凭图片即可明确确认的平台禁售内容。\n\n"
        "2. 成人色情 / 性暗示：\n"
        "- 性器官暴露；\n"
        "- 性行为；\n"
        "- 明显成人色情；\n"
        "- 成人用品明显生殖器仿真造型；\n"
        "- 明显性挑逗姿势；\n"
        "- 敏感部位特写；\n"
        "- 裙底等明显不当拍摄角度；\n"
        "- 裁切突出乳沟、臀部、裆部等；\n"
        "- 明显色情 / 性暗示文字；\n"
        "- 人物 + 床 / 浴缸等场景共同形成明显性暗示；\n"
        "- 儿童成人化、儿童性感化、儿童性暗示。\n"
        "防误杀：普通泳装不等于自动风险；普通人体模特不等于自动风险；床单独出现不等于自动风险；浴缸单独出现不等于自动风险。\n"
        "必须结合人物、姿势、暴露、构图和上下文综合判断。\n"
        "防误杀补充：普通按摩器材、普通健身用品即使标题或图片含'成人'字样也不判；\n"
        "必须图片本身明确呈现性暗示构图才算。\n\n"
        "3. 政治敏感（需明确可识别的具体政治语义）：\n"
        "- 政治人物；\n"
        "- 政党 / 政治组织；\n"
        "- 政治口号、政治宣传文字；\n"
        "- 政治符号、政治徽章；\n"
        "- 敏感旗帜 / 国徽；\n"
        "- 战争宣传、美化侵略；\n"
        "- 煽动政治仇恨；\n"
        "- 政治边界争议地图；\n"
        "- 纳粹等政治极端主义内容。\n"
        "防误杀：普通人物不等于政治人物；普通红蓝配色不等于政治；普通世界地图不等于自动风险。\n"
        "普通颜色组合、抽象旗帜风图案不能自动判政治风险；普通非敏感旗帜的装饰性使用，不因为'看起来像国旗'就报警。\n"
        "但图片中可明确识别为敏感旗帜、国徽、政治组织标识或具有明确政治语义时，仍应判 platform；\n"
        "不得因为印在手机壳、贴纸、衣服或其它商品上就自动豁免。\n"
        "必须能明确识别具体政治语义。\n\n"
        "4. 宗教（明确可识别即可判）：\n"
        "- 明确宗教象征符号；\n"
        "- 宗教人物；\n"
        "- 宗教经文、宗教书籍、宗教文字；\n"
        "- 宗教建筑；\n"
        "- 明确宗教主题商品；\n"
        "- 宗教亵渎、宗教恶搞、宗教侮辱 / 低俗化。\n"
        "防误杀：普通十字形几何结构不能只靠形状猜；普通星形不等于自动宗教符号；普通建筑不等于自动宗教建筑；模糊文字不等于经文；无法确认具体含义 -> none。\n"
        "重点是'明确可识别'。\n"
        "宗教主题商品（如宗教题材装饰画、宗教法器造型摆件、经文复制品）判 platform；\n"
        "普通几何装饰（六边形、圆点、普通花纹）不判。\n\n"
        "5. 仇恨 / 歧视 / 极端主义：\n"
        "- 纳粹 / 新纳粹；\n"
        "- 白人至上主义；\n"
        "- 仇恨组织独有标志；\n"
        "- 仇恨手势、仇恨文字；\n"
        "- 恐怖主义、极端主义宣传；\n"
        "- 对种族、肤色、民族、族裔进行明确丑化或贬低；\n"
        "- 因宗教、年龄、性别、性取向、性别认同、残疾等个人特征宣扬歧视。\n"
        "特殊数字：88、14/88 只在明确仇恨 / 纳粹 / 白人至上语境下判风险。\n"
        "88cm、型号 88、年份 / 编号 88 等普通含义绝不判风险。\n\n"
        "6. 暴力 / 血腥 / 自残：\n"
        "- 明显鲜血；\n"
        "- 开放性伤口；\n"
        "- 断肢、肢解；\n"
        "- 虐杀、严重人身伤害；\n"
        "- 自残、自杀；\n"
        "- 动物虐待；\n"
        "- 明显展示严重伤害结果。\n"
        "普通 Halloween 恐怖风本身不是风险。\n\n"
        "7. 用户内部采集排除项（用户采集策略明确排除，非平台禁售）：\n"
        "- 带电、电池、USB、LED、磁性；\n"
        "- 液体、喷雾、胶水；\n"
        "- 香水 / 精油、粉末等。\n"
        "识别为 platform，reason 前缀'采集规则排除｜'。\n\n"
        "三、美国站 Halloween 防误杀：\n"
        "以下元素本身默认不是风险：\n"
        "- Halloween；\n"
        "- 普通骷髅 / 骨架、普通幽灵、普通南瓜；\n"
        "- 普通女巫、普通僵尸；\n"
        "- 普通恐怖节日装饰、普通卡通恐怖风。\n"
        "不要把沙特 / 中东地区专属禁忌（骷髅、恶魔之眼等）机械套用到美国站。\n"
        "只有 Halloween 商品同时出现明确的：品牌 / IP、政治、宗教、仇恨 / 极端主义、严重血腥伤害、色情 / 性暗示、武器 / 禁售品时，才提示风险。\n"
        "典型：普通 Skeleton decoration -> none；普通 Ghost decoration -> none；普通 Zombie prop -> none；\n"
        "明显带大量血迹、开放伤口、断肢效果 -> platform；明显高危刀具 -> platform；\n"
        "Disney / Marvel / 游戏角色等明确 IP -> infringement。\n\n"
        "儿童内容：普通儿童服装、玩具、卡通形象不判；\n"
        "儿童成人化、儿童性感化、儿童性暗示必须有明确图片证据才判。\n\n"
        "四、reason 规范：\n"
        "reason 保持简短一句话，按风险来源使用固定前缀：\n"
        "- SHEIN 平台风险：SHEIN规则风险｜……\n"
        "- 内部采集策略：采集规则排除｜……\n"
        "- IP / 品牌：侵权风险｜……\n"
        "示例：\n"
        "SHEIN规则风险｜图片出现明显高危刀具\n"
        "SHEIN规则风险｜存在明显开放性伤口和大量血迹\n"
        "采集规则排除｜商品明显为LED带电产品\n"
        "侵权风险｜图片出现明显迪士尼（Disney）角色元素\n"
        "risk=none 时 reason 可以为空。\n\n"
        "严格防误杀：\n"
        "- 普通颜色相似 -> none\n"
        "- 普通商品造型相似 -> none\n"
        "- 普通设计风格相似 -> none\n"
        "- 普通几何纹样 -> none\n"
        "- 模糊 Logo -> none\n"
        "- '有点像某品牌' -> none\n"
        "- 必须靠猜测才能成立 -> none\n"
        "- 无法确认 -> none\n\n"
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

    def clear_cache(self) -> None:
        """清空运行期内存缓存（“清空本次”时调用）。"""
        self._cache.clear()

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

        products: [{"id": "product_id", "title": "可选", "main_image": "url"}, ...]
        title 仅作为理解图片的辅助上下文，缺失或空字符串时图片检测仍正常运行。
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
        failed_count = 0
        for p in products:
            pid = str(p.get("id") or "").strip()
            img = str(p.get("main_image") or "").strip()
            if not pid:
                # 无 id 无法归属到卡片，跳过不计
                continue
            if not img:
                # 缺图：计入失败，不发送 API、不写缓存
                failed_count += 1
                continue
            if not force_refresh:
                cached = self.get_cached(pid, img)
                if cached is not None:
                    cached_count += 1
                    if cached.risk != "none":
                        cached_risky.append(cached)
                    continue
            to_scan.append(p)

        requested_count = cached_count + failed_count + len(to_scan)
        product_risk_log.image_scan_start(requested_count)

        if not to_scan:
            # 无实际 API 批次：仅按失败数决定最终状态
            finish_status = _final_status(cancelled=False, checked_count=0, failed_count=failed_count)
            stats = ImageRiskScanStats(
                requested_count=requested_count,
                cached_count=cached_count,
                checked_count=0,
                risk_count=len(cached_risky),
                failed_count=failed_count,
            )
            product_risk_log.image_scan_finished(
                total=requested_count, batches=0, checked=0, failed=failed_count, status=finish_status
            )
            return cached_risky, stats, []

        # 分批处理
        all_risky: list[ImageRiskItem] = list(cached_risky)
        all_checked: list[ImageRiskItem] = []
        checked_count = 0
        executed_batches = 0
        cancelled = False
        for i in range(0, len(to_scan), BATCH_SIZE):
            # 取消检查：当前批自然完成后不再发送下一批
            if cancel_requested is not None and cancel_requested():
                cancelled = True
                break
            batch = to_scan[i:i + BATCH_SIZE]
            batch_index = i // BATCH_SIZE + 1
            executed_batches += 1
            product_risk_log.image_batch_started(batch_index, len(batch))
            try:
                batch_results, batch_download_failed = self._scan_single_batch(batch, batch_index=batch_index)
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
            # 批次（含最后一批）API 请求期间点击取消也必须记录
            if cancel_requested is not None and cancel_requested():
                cancelled = True

        # 用户取消只记录一次（含单批场景与最后一批请求期间取消）
        if cancelled:
            product_risk_log.image_scan_cancelled()

        stats = ImageRiskScanStats(
            requested_count=requested_count,
            cached_count=cached_count,
            checked_count=checked_count,
            risk_count=len(all_risky),
            failed_count=failed_count,
        )
        product_risk_log.image_scan_finished(
            total=requested_count,
            batches=executed_batches,
            checked=checked_count,
            failed=failed_count,
            status=_final_status(cancelled, checked_count, failed_count),
        )
        return all_risky, stats, all_checked

    def _scan_single_batch(
        self,
        products: list[dict[str, str]],
        *,
        batch_index: int = 1,
    ) -> tuple[list[ImageRiskItem], int]:
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
        title_map: dict[str, str] = {}  # product_id -> title（辅助上下文，可为空）
        download_failed_count = 0
        _download_start = time.monotonic()
        for p in products:
            pid = str(p.get("id") or "").strip()
            img_url = str(p.get("main_image") or "").strip()
            if not pid or not img_url:
                continue
            title_map[pid] = str(p.get("title") or "").strip()
            try:
                img_data = self._download_image(img_url)
                image_items.append((pid, img_url, img_data))
            except Exception as exc:
                logger.warning("下载图片失败 %s: %s", img_url, exc)
                download_failed_count += 1
        download_ms = product_risk_log.elapsed_ms(_download_start)

        if not image_items:
            product_risk_log.image_batch_finished(
                batch_index=batch_index,
                download_ms=download_ms,
                download_failed=download_failed_count,
                payload_bytes=0,
                api_ms=0,
                success=0,
                failed=download_failed_count,
                status="完成",
            )
            return [], download_failed_count

        # 添加图片到 content（每张图前加 id 标记与可选标题辅助上下文）
        for pid, _url, img_data in image_items:
            text = f"商品ID: {pid}"
            title = title_map.get(pid, "")
            if title:
                text += f"\n商品标题: {title}"
            content.append({"type": "text", "text": text})
            b64 = base64.b64encode(img_data).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

        # 构建请求
        body: dict[str, Any] = {
            "model": profile.model_name,
            "temperature": 0,
            "messages": [{"role": "user", "content": content}],
        }
        body.update(qwen_extra_body_params(profile.provider, profile.model_name))

        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = Request(
            endpoint,
            data=payload,
            headers={"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"},
            method="POST",
        )
        _api_start = time.monotonic()
        try:
            with urlopen(request, timeout=180) as response:  # noqa: S310
                response_data = json.loads(response.read().decode("utf-8"))
            api_ms = product_risk_log.elapsed_ms(_api_start)
        except HTTPError as exc:
            product_risk_log.image_batch_finished(
                batch_index=batch_index,
                download_ms=download_ms,
                download_failed=download_failed_count,
                payload_bytes=len(payload),
                api_ms=product_risk_log.elapsed_ms(_api_start),
                success=0,
                failed=len(products),
                status="失败",
                http_error=f"HTTP {exc.code}",
            )
            raise RecognitionUnavailableError(f"图片风险检测请求失败（HTTP {exc.code}）。") from exc
        except TimeoutError as exc:
            product_risk_log.image_batch_finished(
                batch_index=batch_index,
                download_ms=download_ms,
                download_failed=download_failed_count,
                payload_bytes=len(payload),
                api_ms=product_risk_log.elapsed_ms(_api_start),
                success=0,
                failed=len(products),
                status="超时",
                timeout=True,
            )
            raise RecognitionUnavailableError("图片风险检测超时，请稍后重试。") from exc
        except (URLError, OSError) as exc:
            product_risk_log.image_batch_finished(
                batch_index=batch_index,
                download_ms=download_ms,
                download_failed=download_failed_count,
                payload_bytes=len(payload),
                api_ms=product_risk_log.elapsed_ms(_api_start),
                success=0,
                failed=len(products),
                status="失败",
                http_error=str(exc)[:80],
            )
            raise RecognitionUnavailableError(f"图片风险检测无法连接：{exc}") from exc
        except json.JSONDecodeError as exc:
            product_risk_log.image_batch_finished(
                batch_index=batch_index,
                download_ms=download_ms,
                download_failed=download_failed_count,
                payload_bytes=len(payload),
                api_ms=product_risk_log.elapsed_ms(_api_start),
                success=0,
                failed=len(products),
                status="失败",
                http_error="响应解析失败",
            )
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
            product_risk_log.image_batch_finished(
                batch_index=batch_index,
                download_ms=download_ms,
                download_failed=download_failed_count,
                payload_bytes=len(payload),
                api_ms=product_risk_log.elapsed_ms(_api_start),
                success=0,
                failed=len(products),
                status="失败",
                http_error="返回格式无效",
            )
            raise RecognitionResponseError("图片风险检测返回格式无效。") from exc

        results = self._parse_results(data, image_items)
        product_risk_log.image_batch_finished(
            batch_index=batch_index,
            download_ms=download_ms,
            download_failed=download_failed_count,
            payload_bytes=len(payload),
            api_ms=product_risk_log.elapsed_ms(_api_start),
            success=len(results),
            failed=len(products) - len(results),
            status="完成",
        )
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
