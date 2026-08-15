# -*- coding: utf-8 -*-
"""标题风险快筛服务。

复用主软件"按修正重估"绑定的文字 API Profile（LOCAL_REESTIMATE）。
不新增 API 配置、不新增设置页面、不修改 LocalReestimateService。

风险三档：none / platform / infringement。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from profit_accounting_26.application.api_profile_store import ApiProfileStore, LOCAL_REESTIMATE
from profit_accounting_26.product_collector import product_risk_log
from profit_accounting_26.application.qwen_request_params import qwen_extra_body_params
from profit_accounting_26.application.recognition_service import (
    RecognitionResponseError,
    RecognitionService,
    RecognitionUnavailableError,
)

PROMPT_VERSION = "product-collector-title-risk-v3"

# 每批送检的标题数量
BATCH_SIZE = 20

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
        "- 完整上下文 > 单个关键词，禁止简单关键词机械触发。\n"
        "- 以下词语单独出现不能自动报警：Kids、Baby、Children、Halloween、Skeleton、Skull、Cross、Star、88。\n"
        "- 88cm curtain -> none；model 88 -> none；年份 / 编号 88 -> none。\n"
        "- 88、14/88 只有在明确仇恨 / 纳粹 / 白人至上语境中才是风险。\n"
        "- Halloween skeleton decoration -> none；Kids storage bag -> none。\n"
        "- Halloween skull mug -> none；'88cm curtain' -> none；'Nazi flag poster' -> platform。\n"
        "- 只能依据标题明确出现的信息，不根据'这种商品通常……'脑补。\n"
        "- 普通风格词不是侵权证据。\n"
        "- 模糊情况返回 none。\n"
        "- 不联网。\n"
        "- 不判断物流/利润/重量/尺寸。\n"
        "- 不改写标题。\n"
        "- 不做法律定论。\n\n"
        "一、SHEIN 明确禁售品（platform）：\n"
        "- 明确武器、高危刀具、爆炸物；\n"
        "- 烟草、电子烟、毒品、吸毒工具；\n"
        "- 赌博；\n"
        "- 食品饮料；\n"
        "- 明确药品/高风险医疗/治疗产品；\n"
        "- 其它明确禁售商品。\n\n"
        "二、成人色情 / 性暗示（platform）：\n"
        "- 明显色情 / 成人内容、性行为、性暗示描述；\n"
        "- 儿童成人化、儿童性感化、儿童性暗示。\n\n"
        "三、政治（platform，需明确政治语义）：\n"
        "- 政治人物、政党 / 政治组织；\n"
        "- 政治口号、政治宣传文字、政治符号、政治徽章；\n"
        "- 敏感旗帜 / 国徽；\n"
        "- 战争宣传、美化侵略、煽动政治仇恨；\n"
        "- 政治边界争议；\n"
        "- 纳粹等政治极端主义内容。\n"
        "普通国旗风配色、普通国家名不等于政治风险。\n\n"
        "四、宗教（platform，需明确可识别）：\n"
        "- 明确宗教人物、宗教符号、宗教主题商品；\n"
        "- 明确宗教建筑（标题明确表达 mosque / church / temple 等具体宗教建筑商品时，结合完整标题上下文判断）；\n"
        "- 宗教经文、宗教书籍、宗教文字；\n"
        "- 宗教亵渎、宗教恶搞、宗教侮辱 / 低俗化。\n"
        "普通建筑不能靠猜测判断宗教；Cross、Star 等单独词语不自动判宗教；完整上下文 > 单关键词；证据不足 -> none。\n\n"
        "五、仇恨 / 极端主义 / 歧视（platform）：\n"
        "- 纳粹 / 新纳粹、白人至上主义；\n"
        "- 仇恨组织标志 / 手势 / 文字；\n"
        "- 恐怖主义、极端主义宣传；\n"
        "- 对种族、肤色、民族、族裔丑化贬低；\n"
        "- 因宗教、年龄、性别、性取向、性别认同、残疾等个人特征宣扬歧视；\n"
        "- 88、14/88 仅在明确仇恨 / 纳粹 / 白人至上语境判风险。\n\n"
        "六、暴力 / 血腥 / 自残（platform）：\n"
        "- 明显暴力、血腥、开放性伤口描述；\n"
        "- 自残、自杀、虐杀、动物虐待。\n"
        "普通 Halloween 恐怖风格描述（如 skeleton、ghost、zombie、blood splash 道具装）不自动判风险。\n\n"
        "七、用户内部采集排除项（platform，reason 前缀'采集规则排除｜'）：\n"
        "- 带电、电池、USB、LED、磁性；\n"
        "- 液体、喷雾、胶水；\n"
        "- 香水 / 精油、粉末等。\n\n"
        "八、品牌 / IP（infringement）：\n"
        "- 明确品牌名称 / 商标；\n"
        "- 影视、动漫、游戏 IP；\n"
        "- 明星 / 名人周边；\n"
        "- 球队、大学、组织；\n"
        "- Replica / 仿 / 复制 / Inspired by 等直接关联具体品牌 / IP。\n"
        "完整上下文示例：'Halloween costume' 不判；'Disney Halloween costume' 判 infringement。\n\n"
        "儿童防误杀：\n"
        "- Kids / Baby / Children 不等于自动风险。\n"
        "- 普通儿童毛巾、发饰、收纳、生活用品不能因此误杀。\n"
        "- 明确儿童/婴儿玩具、高风险儿童用品才判断。\n"
        "- 捏捏乐、慢回弹、桌面解压、挂件、小摆件等边界商品：没有明确违规证据时不要强判。\n\n"
        "reason 规范：按风险来源使用固定前缀：\n"
        "- SHEIN规则风险｜（平台禁售）\n"
        "- 采集规则排除｜（内部采集策略）\n"
        "- 侵权风险｜（IP / 品牌）\n"
        "示例：\n"
        "SHEIN规则风险｜标题明确为电子烟\n"
        "采集规则排除｜标题明确为USB带电商品\n"
        "侵权风险｜标题包含迪士尼（Disney）\n"
        "risk=none 时 reason 可以为空。\n\n"
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
    BATCH_SIZE = BATCH_SIZE

    def __init__(self, profile_store: ApiProfileStore) -> None:
        self.profile_store = profile_store

    @staticmethod
    def _endpoint(raw: str) -> str:
        return RecognitionService._endpoint(raw)

    def scan(
        self,
        titles: list[dict[str, str]],
        *,
        on_batch: Any | None = None,
        cancel_requested: Any | None = None,
    ) -> list[TitleRiskItem]:
        """批量检测标题风险，按 BATCH_SIZE 分批顺序执行。

        titles: [{"id": "product_id", "title": "English title"}, ...]
        on_batch: 可选回调，每批完成后调用一次：
            on_batch(batch_results, batch_failed, batch_index, total_batches, elapsed_ms)
            其中 batch_failed 为本批明确失败 / 缺失结果的商品数。
        cancel_requested: 可选回调，批次开始前调用；返回 True 时停止后续批次，
            已完成的批次结果仍保留在返回值中。
        返回: 所有批次成功解析结果的合并列表（含 none，含未知 id 条目）。
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

        product_risk_log.title_scan_start(
            profile.display_name, profile.provider, profile.model_name, len(titles)
        )

        uses_openai_schema = str(getattr(profile, "provider", "") or "").strip().casefold() == "openai"

        total_batches = (len(titles) + BATCH_SIZE - 1) // BATCH_SIZE
        all_results: list[TitleRiskItem] = []
        total_failed = 0
        cancelled = False
        executed_batches = 0

        for batch_index, start in enumerate(range(0, len(titles), BATCH_SIZE), start=1):
            batch = titles[start:start + BATCH_SIZE]
            if cancel_requested is not None and cancel_requested():
                cancelled = True
                break
            executed_batches = batch_index
            product_risk_log.title_batch_started(batch_index, len(batch))
            _batch_start = time.monotonic()
            batch_results: list[TitleRiskItem] = []
            batch_failed = 0
            try:
                batch_results = self._request_single_batch(
                    batch, profile, api_key, endpoint, uses_openai_schema
                )
            except (RecognitionUnavailableError, RecognitionResponseError) as exc:
                # 单批失败不拖垮其它批：记录本批失败，继续下一批
                batch_failed = len(batch)
                batch_status = "超时" if "超时" in str(exc) else "失败"
            else:
                batch_status = "完成"
                expected_ids = {
                    str(t.get("id") or "").strip()
                    for t in batch
                    if str(t.get("id") or "").strip()
                }
                valid_ids = {r.product_id for r in batch_results if r.product_id in expected_ids}
                batch_failed = len(expected_ids - valid_ids)
                all_results.extend(batch_results)
            total_failed += batch_failed
            elapsed_ms = product_risk_log.elapsed_ms(_batch_start)
            product_risk_log.title_batch_finished(
                batch_index=batch_index,
                duration_ms=elapsed_ms,
                success=len(batch_results),
                failed=batch_failed,
                status=batch_status,
                timeout=batch_status == "超时",
            )
            if on_batch is not None:
                on_batch(batch_results, batch_failed, batch_index, total_batches, elapsed_ms)

        if cancelled:
            status = "取消"
        elif total_failed:
            status = "部分失败"
        else:
            status = "完成"
        product_risk_log.title_scan_finished(
            total=len(titles),
            batches=executed_batches,
            checked=len(all_results),
            failed=total_failed,
            status=status,
        )
        return all_results

    def _request_single_batch(
        self,
        batch: list[dict[str, str]],
        profile: Any,
        api_key: str,
        endpoint: str,
        uses_openai_schema: bool,
    ) -> list[TitleRiskItem]:
        """请求单个批次并解析返回结果（含该批次请求日志）。

        失败时抛 RecognitionUnavailableError / RecognitionResponseError，
        由 scan() 统一按"单批失败"处理。
        """
        prompt = _build_prompt(batch)
        body: dict[str, Any] = {
            "model": profile.model_name,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }
        if uses_openai_schema:
            body["response_format"] = {"type": "json_object"}
        body.update(qwen_extra_body_params(profile.provider, profile.model_name))

        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = Request(
            endpoint,
            data=payload,
            headers={"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"},
            method="POST",
        )
        _request_start = time.monotonic()
        product_risk_log.title_request_started(len(payload))
        try:
            with urlopen(request, timeout=120) as response:  # noqa: S310
                response_data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            product_risk_log.title_request_finished(
                duration_ms=product_risk_log.elapsed_ms(_request_start),
                success=0,
                missing=len(batch),
                status="失败",
                http_error=f"HTTP {exc.code}",
            )
            raise RecognitionUnavailableError(f"标题风险检测请求失败（HTTP {exc.code}）。") from exc
        except TimeoutError as exc:
            product_risk_log.title_request_finished(
                duration_ms=product_risk_log.elapsed_ms(_request_start),
                success=0,
                missing=len(batch),
                status="超时",
                timeout=True,
            )
            raise RecognitionUnavailableError("标题风险检测超时，请稍后重试。") from exc
        except (URLError, OSError) as exc:
            product_risk_log.title_request_finished(
                duration_ms=product_risk_log.elapsed_ms(_request_start),
                success=0,
                missing=len(batch),
                status="失败",
                http_error=str(exc)[:80],
            )
            raise RecognitionUnavailableError(f"标题风险检测无法连接：{exc}") from exc
        except json.JSONDecodeError as exc:
            product_risk_log.title_request_finished(
                duration_ms=product_risk_log.elapsed_ms(_request_start),
                success=0,
                missing=len(batch),
                status="失败",
                http_error="响应解析失败",
            )
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
            product_risk_log.title_request_finished(
                duration_ms=product_risk_log.elapsed_ms(_request_start),
                success=0,
                missing=len(batch),
                status="失败",
                http_error="返回格式无效",
            )
            raise RecognitionResponseError("标题风险检测返回格式无效。") from exc

        results = self._parse_risks(data)
        # 日志统计按实际送检 id 集合去重：AI 返回重复 id / 未知 id 不夸大 success
        expected_ids = {
            str(t.get("id") or "").strip() for t in batch if str(t.get("id") or "").strip()
        }
        valid_returned_ids = {r.product_id for r in results if r.product_id in expected_ids}
        product_risk_log.title_request_finished(
            duration_ms=product_risk_log.elapsed_ms(_request_start),
            success=len(valid_returned_ids),
            missing=len(expected_ids - valid_returned_ids),
            status="完成",
        )
        return results

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
