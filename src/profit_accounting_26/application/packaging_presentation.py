from __future__ import annotations

import re

from profit_accounting_26.domain.models import AIObservation, PackagingProposal, PackagingState


_PACKAGING_METHOD_ZH = {
    "polybag": "塑料袋包装",
    "poly mailer": "快递袋包装",
    "bubble mailer": "气泡袋包装",
    "bubble bag": "气泡袋包装",
    "vacuum bag": "真空袋包装",
    "self-sealing bag": "自封袋包装",
    "opp bag": "OPP袋包装",
    "cardboard box": "纸箱包装",
    "carton": "纸箱包装",
    "box": "纸箱包装",
    "mailer": "邮寄袋包装",
    "envelope": "信封包装",
    "bag": "袋装",
    "pallet": "托盘包装",
    "stretch wrap": "缠绕膜包装",
}


def packaging_method_zh(method: str | None) -> str:
    """仅显示层中文化：把 AI 返回的英文包装方式映射为中文，不修改原始数据。"""
    text = str(method or "").strip()
    if not text:
        return ""
    # 已含中文（如 AI 直接返回中文）时原样保留
    if any("\u4e00" <= char <= "\u9fff" for char in text):
        return text
    lowered = text.lower()
    if lowered in _PACKAGING_METHOD_ZH:
        return _PACKAGING_METHOD_ZH[lowered]
    # 常见附加描述（如 "polybag 30*40cm"）按最长 token 命中
    for token, label in sorted(_PACKAGING_METHOD_ZH.items(), key=lambda item: len(item[0]), reverse=True):
        if token in lowered:
            return label
    return "其他包装"


def _compact(text: str, limit: int) -> str:
    text = re.sub(r"\s+", "", str(text or "")).strip("；;，,、|｜")
    return text if len(text) <= limit else ""


def _main_name(observation: AIObservation) -> str:
    """Keep a recognisable product subject, without copying an ecommerce title."""
    raw = str(observation.product_name or observation.product_type or "商品")
    raw = re.split(r"[；;，,、|｜【\[]", raw, maxsplit=1)[0]
    raw = re.sub(r"^(新品|爆款|热卖|包邮|厂家直销|同款|现货|批发|特价)+", "", raw)
    raw = re.sub(r"(适用人群|颜色列表|多色可选|销量\S*|已售\S*)", "", raw)
    raw = re.sub(r"(新品|爆款|热卖|包邮|厂家直销|同款|现货|批发|特价|\d+件)$", "", raw).strip()
    return _compact(raw, 14) or "商品"


def _quantity_display(observation: AIObservation) -> str:
    """稳定数量显示：优先结构化 purchase_quantity + quantity_unit，不受 summary 长度影响。

    - quantity_source == "assumed/unknown"：AI 未返回确认的 purchase_quantity
      （quantity=1 只是占位）→ 回退短 quantity_summary 文本（仍受 _compact 截断保护）；
    - quantity 已确认且有 quantity_unit → “数量 2双/3套”（销售单位中文简称，AI 判断）；
    - quantity 已确认但无 unit → “数量 ×2”；
    - quantity == 1 且无来源证据（source 为 unknown / assumed/unknown / 空）：
      视为未设置，走 summary 回退，保持旧记录/默认构造商品摘要显示不变。

    quantity_summary 原始内容仍完整保留在 observation / history / manifest，
    不改数据合同；本函数只负责主界面显示。
    """
    purchase_quantity = getattr(observation, "quantity", None)
    source = str(getattr(observation, "quantity_source", "") or "")
    if isinstance(purchase_quantity, int) and not isinstance(purchase_quantity, bool) and purchase_quantity > 0:
        if purchase_quantity > 1 or source not in ("unknown", "assumed/unknown", ""):
            unit = str(getattr(observation, "quantity_unit", "") or "").strip()
            if unit:
                return f"数量 {purchase_quantity}{unit}"
            return f"数量 ×{purchase_quantity}"
    return _compact(getattr(observation, "quantity_summary", ""), 20)


def cost_review_warnings(observation: AIObservation | None) -> list[str]:
    """非精确商品成本/国内运费 → 明确的复核原因（纯函数，供页面 badge 合并）。

    - starting_from / range_min：影响利润的非精确成本 → 明确 warning（允许计算，不阻止保存）；
    - estimated：轻量提示为估算值。
    返回空列表表示没有成本风险信号。
    """
    if observation is None:
        return []
    warnings: list[str] = []
    cost = getattr(observation, "product_cost_rmb", None)
    cost_type = str(getattr(observation, "product_cost_value_type", "") or "")
    if cost is not None and float(cost) > 0:
        if cost_type in ("starting_from", "range_min"):
            warnings.append("商品成本为起价/区间下限，实际成本可能更高")
        elif cost_type == "estimated":
            warnings.append("商品成本为估算值")
    shipping = getattr(observation, "domestic_shipping_rmb", None)
    shipping_type = str(getattr(observation, "domestic_shipping_value_type", "") or "")
    if shipping is not None and float(shipping) > 0:
        if shipping_type in ("starting_from", "range_min"):
            warnings.append("国内运费为起价/区间下限，实际成本可能更高")
        elif shipping_type == "estimated":
            warnings.append("国内运费为估算值")
    return warnings


def product_summary(observation: AIObservation) -> str:
    """Concise summary: AI title | quantity（数量稳定显示，不受 quantity_summary 长度影响）。"""
    title = _compact(observation.display_product_summary or observation.product_name, 30)
    if not title:
        title = _main_name(observation)
    quantity = _quantity_display(observation)
    if quantity:
        return f"{title}｜{quantity}"
    return title

def _bulk_only(text: str) -> bool:
    value = str(text or "")
    bulk_markers = ("每箱", "每袋", "装箱数", "整箱规格", "整箱", "件/箱", "个/箱", "只/箱", "套/箱", "件/袋", "个/袋")
    return any(marker in value for marker in bulk_markers) or bool(re.search(r"\b(?:pcs?|pieces?)\s*/\s*(?:carton|box|bag)\b|\bper\s+(?:carton|bag)\b", value, re.I))


def _single_package_type(observation: AIObservation, proposal: PackagingProposal) -> str:
    method = str(proposal.normal.packaging_method or "")
    if _bulk_only(method):
        return "单件包装待确认"
    if proposal.proposal_source == "merchant_candidate" and observation.retail_box_visible is True:
        return "原包装发货"
    for token, label in (("OPP", "预计OPP袋装"), ("自封", "预计自封袋装"), ("气泡", "预计气泡袋装"),
                         ("泡沫", "预计泡沫盒装"), ("礼盒", "商家礼盒装"), ("纸盒", "单件纸盒装"),
                         ("纸箱", "单件纸箱装"), ("盒", "单件纸盒装"), ("carton", "单件纸箱装"), ("box", "单件纸盒装")):
        if token.lower() in method.lower():
            return label
    if observation.retail_box_visible is True:
        return "原包装发货"
    return "单件包装待确认"


def _valid_packaging_summary(text: str) -> bool:
    """Accept only a user-facing handling plus individual-package statement."""
    value = str(text or "").strip()
    if _bulk_only(value) or any(token in value.lower() for token in ("ai_candidate", "generic_candidate", "cal-", "confidence", "source")):
        return False
    if re.search(r"\d+(?:\.\d+)?\s*(?:cm|mm|g|kg)\b", value, re.I):
        return False
    parts = [part.strip() for part in value.split("；")]
    if len(parts) != 2 or not all(parts):
        return False
    handling, package_type = parts
    if handling in {"预计", "待确认", "袋装", "裸品", "无包装"}:
        return False
    if package_type in {"预计", "待确认", "袋装", "裸品", "无包装"}:
        return False
    allowed_type_markers = ("opp", "自封", "气泡", "泡沫", "纸盒", "纸箱", "礼盒", "原包装", "单件包装待确认")
    return any(marker in package_type.lower() for marker in allowed_type_markers)


def packaging_summary(observation: AIObservation, proposal: PackagingProposal) -> str:
    supplied = _compact(observation.display_packaging_summary, 30)
    if supplied and _valid_packaging_summary(supplied):
        return supplied
    actions = set(observation.packing_actions or [])
    constraints = set(observation.packing_constraints or [])
    if proposal.normal.packaging_state == PackagingState.SHAPE_RETAINED:
        action = "保持形状"
    elif "coil" in actions or observation.overall_form == "flexible_chain":
        action = "盘绕收纳"
    elif "flat_fold" in actions or proposal.normal.packaging_state == PackagingState.FULL_FLAT_FOLD:
        action = "平折收纳"
    elif "do_not_compress" in constraints:
        action = "不可压缩"
    else:
        action = "保护包装"
    if "fragile_protrusion" in constraints or observation.overall_form == "fragile_protruding":
        protection = "保护突出部"
    elif proposal.normal.packaging_state == PackagingState.SHAPE_RETAINED:
        protection = "四周缓冲"
    elif "scratch_protect" in actions:
        protection = "仅防刮"
    else:
        protection = "轻度防护"
    handling = action if action != "保护包装" else protection
    return _compact(f"{handling}；{_single_package_type(observation, proposal)}", 26) or "轻度防护；单件包装待确认"


def normal_reminder(observation: AIObservation, proposal: PackagingProposal, *, user_modified: bool = False) -> str:
    """Two concise Chinese lines for the normal-plan frozen reminder."""
    source = {
        "merchant_candidate": "图片明确规格",
        "ai_candidate": "AI估算",
        "cal_candidate": "历史校准",
        "generic_candidate": "本地估算",
    }.get(proposal.proposal_source, "待补充")
    display = packaging_summary(observation, proposal)
    if display.startswith("预计包装；"):
        display = display.removeprefix("预计包装；")
    first = _compact(f"{display}｜{'用户修改' if user_modified else source}", 22)
    if not first:
        first = _compact(f"{proposal.normal.packaging_method or '包装方案'}｜{'用户修改' if user_modified else source}", 22) or "包装方案待补充"
    if user_modified:
        second = "已按用户输入重新计算"
    else:
        rejected = proposal.rejected_candidates
        constraints = set(observation.packing_constraints or [])
        merchant_conflict = any("merchant" in reason for reasons in rejected.values() for reason in reasons)
        if merchant_conflict:
            second = "商家规格冲突，建议复核"
        elif not all(value is not None and float(value) > 0 for value in (proposal.normal.length_cm, proposal.normal.width_cm, proposal.normal.height_cm)):
            second = "包装尺寸缺失，建议复核"
        elif proposal.normal.weight_g is None or proposal.normal.weight_g <= 0:
            second = "包装重量缺失，建议复核"
        elif "do_not_compress" in constraints and proposal.normal.packaging_state in {PackagingState.FULL_FLAT_FOLD, PackagingState.STRONG_COMPRESSION}:
            second = "结构判断冲突，建议复核"
        elif proposal.proposal_source == "generic_candidate":
            second = "使用通用估算，建议复核"
        elif rejected:
            second = "候选存在冲突，建议复核"
        elif proposal.normal.confidence == "low":
            second = "数据为预估，建议复核"
        else:
            second = "信息完整，无需人工复核"
    return f"{first}\n{_compact(second, 18) or '建议人工复核'}"
