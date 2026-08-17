"""PR #40 最后一轮：小型数据合同收口 targeted tests（任务书第十八节 28 项）。

覆盖：
A 数量：quantity_unit 合同 + 显示（1-5）
B 商品成本：单价/总价分离 + 确定性乘法（6-9）
C value_type：exact / estimated / starting_from / range_min（10-13）
D schema/parser：canonical 统一 + 有限 alias + 非法值不猜（14-17）
E evidence：可定位证据才当硬事实（18-19）
F needs_review：真实风险才复核，普通结果不提示（20-24）
G raw 洁净：ai_raw 不可变 + product_name 分离（25-28）

禁止真实 API / 浏览器 / 外部链接。
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from profit_accounting_26.application import AppContext, SettingsService  # noqa: E402
from profit_accounting_26.application.calibration_export_service import _machine_ai_initial  # noqa: E402
from profit_accounting_26.application.local_reestimate_service import LocalReestimateService  # noqa: E402
from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService  # noqa: E402
from profit_accounting_26.application.packaging_presentation import cost_review_warnings, product_summary  # noqa: E402
from profit_accounting_26.application.recognition_service import RecognitionService  # noqa: E402
from profit_accounting_26.application.runtime_ai_services import RecognitionOutcome  # noqa: E402
from profit_accounting_26.domain.models import (  # noqa: E402
    AIObservation,
    PackagingProposal,
    PackagingScenario,
    PackagingState,
)
from profit_accounting_26.ui.pages import CalculationPage  # noqa: E402


# ------------------------------------------------------------------ helpers


def _v1_payload(**overrides) -> dict:
    base = {
        "product_name": "测试商品",
        "observed": {
            "product_unit_price_rmb": None,
            "product_total_cost_rmb": None,
            "product_cost_value_type": None,
            "page_shipping_rmb": None,
            "page_shipping_value_type": None,
            "bare_dimensions_cm": {"length": None, "width": None, "height": None},
            "bare_weight_g": None,
        },
        "bare_estimate": {"length_cm": None, "width_cm": None, "height_cm": None, "weight_g": None},
        "shipment": {"length_cm": 30, "width_cm": 20, "height_cm": 9, "weight_g": 680, "state": "袋装"},
        "quantity": {"purchase_quantity": None, "quantity_source": None,
                     "quantity_unit": None, "quantity_summary": None},
        "note": "",
    }
    base.update(overrides)
    return base


def _parse(payload: dict) -> AIObservation:
    return RecognitionService._parse_v1_payload(payload, model="test")[0]


def _proposal(source: str = "vision_ai_v1", *, length: float = 30.0, width: float = 20.0,
              height: float = 9.0, weight: float = 680.0) -> PackagingProposal:
    normal = PackagingScenario(
        label="AI估算", packaging_method="袋装", packaging_state=PackagingState.MODERATE_COMPRESSION,
        length_cm=length, width_cm=width, height_cm=height, weight_g=weight,
        confidence="medium", needs_review=False,
    )
    conservative = PackagingScenario(
        label="当前采用", packaging_method="袋装", packaging_state=PackagingState.MODERATE_COMPRESSION,
        length_cm=length, width_cm=width, height_cm=height, weight_g=weight,
        confidence="medium", needs_review=False,
    )
    return PackagingProposal(normal=normal, conservative=conservative, proposal_source=source)


@pytest.fixture
def temp_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


@pytest.fixture
def page(qapp, temp_context):
    widget = CalculationPage(temp_context)
    yield widget
    widget.deleteLater()


def _complete_visual_ai(page, observation: AIObservation, proposal: PackagingProposal) -> None:
    page._diagnostic_operation = page.context.diagnostic_logger.begin_operation("test-contract-closure")
    outcome = RecognitionOutcome(
        raw_observation=observation,
        raw_ai_proposal=proposal,
        adopted_proposal=proposal,
        arbitration_observation=observation,
        arbitration_trace={},
    )
    page._recognition_completed(outcome)


# ==================================================================
# A 数量合同：purchase_quantity + quantity_unit + quantity_summary 三者分开
# ==================================================================


class TestQuantityUnitContract:
    def test_quantity_2_unit_du_displays_2du(self):
        """purchase_quantity=2 + quantity_unit=双 → “数量 2双”（A-1）。"""
        obs = _parse(_v1_payload(quantity={
            "purchase_quantity": 2, "quantity_source": "page", "quantity_unit": "双", "quantity_summary": "",
        }))
        assert obs.quantity_unit == "双"
        assert product_summary(obs) == "测试商品｜数量 2双"

    def test_quantity_2_unit_tao_long_summary_stable(self):
        """quantity=2 + unit=套 + 超长 summary → 稳定显示“数量 2套”（A-2）。"""
        obs = _parse(_v1_payload(quantity={
            "purchase_quantity": 2, "quantity_source": "page", "quantity_unit": "套",
            "quantity_summary": "页面显示2套，每套3件共6件，总价99元，规格可选",
        }))
        assert product_summary(obs) == "测试商品｜数量 2套"

    def test_quantity_2_without_unit_shows_x2(self):
        """quantity=2、unit 缺失 → “数量 ×2”（A-3）。"""
        obs = _parse(_v1_payload(quantity={
            "purchase_quantity": 2, "quantity_source": "page", "quantity_unit": "", "quantity_summary": "2双",
        }))
        assert product_summary(obs) == "测试商品｜数量 ×2"

    def test_unknown_quantity_not_faked_as_1(self):
        """quantity 未知 → 不伪装成“1件/数量 ×1”（A-4）。"""
        obs = _parse(_v1_payload(quantity={
            "purchase_quantity": None, "quantity_source": None, "quantity_unit": None,
            "quantity_summary": "购买数量未确认",
        }))
        assert obs.quantity_source == "assumed/unknown"
        result = product_summary(obs)
        assert "数量 ×1" not in result
        assert "购买数量未确认" in result

    def test_quantity_1_with_unit_shows_1_unit(self):
        """quantity=1 + 有 unit + 有来源 → “数量 1件”（有单位时不丢单位）。"""
        obs = _parse(_v1_payload(quantity={
            "purchase_quantity": 1, "quantity_source": "page", "quantity_unit": "件", "quantity_summary": "1件",
        }))
        assert product_summary(obs) == "测试商品｜数量 1件"

    def test_quantity_summary_and_unit_kept_in_raw_history_manifest(self):
        """quantity_summary 全文 + quantity_unit 在解析/历史/manifest 完整保留（A-5）。"""
        full = "页面显示已选1款4双，总价15.2元，规格为均码，尺码可选"
        obs = _parse(_v1_payload(quantity={
            "purchase_quantity": 4, "quantity_source": "page", "quantity_unit": "双", "quantity_summary": full,
        }))
        assert obs.quantity_summary == full
        assert obs.quantity_unit == "双"
        initial = _machine_ai_initial({"_v2": {"ai_initial": {"observation": obs.to_dict()}}})
        assert initial["observation"]["quantity_summary"] == full
        assert initial["observation"]["quantity_unit"] == "双"
        # 重估上下文也能读取数量/单位/解释
        prompt = LocalReestimateService._context(
            product_name="测试商品", confirmed_facts={}, current_shipment={},
            user_correction="更大",
            initial_ai_observation={"quantity": 4, "quantity_unit": "双", "quantity_summary": full},
        )
        assert "quantity_unit" in prompt and "quantity_summary" in prompt


# ==================================================================
# B 商品成本：product_cost_rmb 恒为本次购买总商品成本
# ==================================================================


class TestProductCostSemantics:
    def test_unit_price_times_confirmed_quantity(self):
        """页面单价 0.83 × 已确认数量 2 → product_cost_rmb=1.66（B-6）。"""
        obs = _parse(_v1_payload(observed={
            "product_unit_price_rmb": 0.83, "product_total_cost_rmb": None,
            "product_cost_value_type": "exact", "page_shipping_rmb": None,
            "page_shipping_value_type": None,
            "bare_dimensions_cm": {"length": None, "width": None, "height": None}, "bare_weight_g": None,
        }, quantity={
            "purchase_quantity": 2, "quantity_source": "page", "quantity_unit": "双", "quantity_summary": "2双",
        }))
        assert obs.product_unit_price_rmb == 0.83
        assert obs.product_cost_rmb == pytest.approx(1.66, abs=0.001)

    def test_page_total_wins_over_unit_times_quantity(self):
        """页面明确总价 15.20（单价3.80×4）→ total 优先（B-7）。"""
        obs = _parse(_v1_payload(observed={
            "product_unit_price_rmb": 3.80, "product_total_cost_rmb": 15.20,
            "product_cost_value_type": "exact", "page_shipping_rmb": None,
            "page_shipping_value_type": None,
            "bare_dimensions_cm": {"length": None, "width": None, "height": None}, "bare_weight_g": None,
        }, quantity={
            "purchase_quantity": 4, "quantity_source": "page", "quantity_unit": None, "quantity_summary": "",
        }))
        assert obs.product_total_cost_rmb == 15.20
        assert obs.product_cost_rmb == pytest.approx(15.20, abs=0.001)

    def test_unit_price_without_quantity_not_faked_as_total(self):
        """quantity 未知 + 只有单价 → 不得把 0.83 伪装成本次总成本（B-8）。"""
        obs = _parse(_v1_payload(observed={
            "product_unit_price_rmb": 0.83, "product_total_cost_rmb": None,
            "product_cost_value_type": "exact", "page_shipping_rmb": None,
            "page_shipping_value_type": None,
            "bare_dimensions_cm": {"length": None, "width": None, "height": None}, "bare_weight_g": None,
        }, quantity={
            "purchase_quantity": None, "quantity_source": None, "quantity_unit": None, "quantity_summary": "",
        }))
        assert obs.product_cost_rmb is None
        issues = obs.raw_payload["numeric_parse_issues"]
        assert issues["cost.unit_price_without_quantity"]["reason"] == "quantity_unconfirmed_unit_price_not_total"

    def test_page_total_without_quantity_is_still_total(self):
        """页面事实明确是总价时，即使数量未知也采用 total（B-8 的“除非”分支）。"""
        obs = _parse(_v1_payload(observed={
            "product_unit_price_rmb": None, "product_total_cost_rmb": 15.20,
            "product_cost_value_type": "exact", "page_shipping_rmb": None,
            "page_shipping_value_type": None,
            "bare_dimensions_cm": {"length": None, "width": None, "height": None}, "bare_weight_g": None,
        }, quantity={
            "purchase_quantity": None, "quantity_source": None, "quantity_unit": None, "quantity_summary": "",
        }))
        assert obs.product_cost_rmb == pytest.approx(15.20, abs=0.001)

    def test_unit_total_conflict_records_audit_warning(self):
        """unit×quantity 与页面 total 明显冲突 → 记录 audit warning，不静默选错值（B-9）。"""
        obs = _parse(_v1_payload(observed={
            "product_unit_price_rmb": 3.80, "product_total_cost_rmb": 10.0,
            "product_cost_value_type": "exact", "page_shipping_rmb": None,
            "page_shipping_value_type": None,
            "bare_dimensions_cm": {"length": None, "width": None, "height": None}, "bare_weight_g": None,
        }, quantity={
            "purchase_quantity": 4, "quantity_source": "page", "quantity_unit": None, "quantity_summary": "",
        }))
        # 页面 total 优先，但冲突必须留痕
        assert obs.product_cost_rmb == pytest.approx(10.0, abs=0.001)
        issues = obs.raw_payload["numeric_parse_issues"]
        assert issues["cost.unit_total_conflict"]["reason"] == "unit_times_quantity_conflicts_with_page_total"
        assert obs.raw_payload["cost_audit"]["unit_total_conflict"]["unit_times_quantity"] == pytest.approx(15.2, abs=0.001)


# ==================================================================
# C value_type：exact / estimated / starting_from / range_min / unknown
# ==================================================================


class TestCostValueType:
    def _cost_obs(self, value_type: str | None, *, evidence: dict | None = None) -> AIObservation:
        observed = {
            "product_unit_price_rmb": 3.0, "product_total_cost_rmb": None,
            "product_cost_value_type": value_type, "page_shipping_rmb": None,
            "page_shipping_value_type": None,
            "bare_dimensions_cm": {"length": None, "width": None, "height": None}, "bare_weight_g": None,
        }
        payload = _v1_payload(observed=observed, quantity={
            "purchase_quantity": 1, "quantity_source": "page", "quantity_unit": None, "quantity_summary": "",
        })
        if evidence is not None:
            payload["field_evidence"] = {"product_cost_rmb": evidence}
        return _parse(payload)

    def test_starting_from_not_exact(self):
        """“¥3起” → starting_from，绝不 exact（C-10）。"""
        obs = self._cost_obs("starting_from")
        assert obs.product_cost_value_type == "starting_from"

    def test_estimated(self):
        """“约¥3” → estimated（C-11）。"""
        obs = self._cost_obs("estimated")
        assert obs.product_cost_value_type == "estimated"

    def test_exact(self):
        """明确 ¥3 → exact（C-12）。"""
        obs = self._cost_obs("exact")
        assert obs.product_cost_value_type == "exact"

    def test_range_min(self):
        """区间 → range_min，绝不 exact（C-13）。"""
        obs = self._cost_obs("range_min")
        assert obs.product_cost_value_type == "range_min"

    def test_ai_silent_evidence_inference(self):
        """AI 未给 value_type 时按页面原文推断（起→starting_from / 约→estimated / 区间→range_min）。"""
        assert self._cost_obs(None, evidence={"raw_text": "¥3起", "meaning": "起价"}).product_cost_value_type == "starting_from"
        assert self._cost_obs(None, evidence={"raw_text": "约¥3", "meaning": ""}).product_cost_value_type == "estimated"
        assert self._cost_obs(None, evidence={"raw_text": "¥3-5", "meaning": "区间价"}).product_cost_value_type == "range_min"

    def test_ai_silent_no_evidence_stays_unknown_not_exact(self):
        """AI 未给 value_type 且无证据 → unknown（Parser 不得因数值非 null 自动标 exact）。"""
        obs = self._cost_obs(None)
        assert obs.product_cost_value_type == "unknown"
        assert obs.product_cost_value_type != "exact"

    def test_non_canonical_value_type_becomes_unknown_with_issue(self):
        """AI 返回非正式 value_type（如 page_estimate）→ unknown + parse issue，不猜测。"""
        obs = self._cost_obs("page_estimate")
        assert obs.product_cost_value_type == "unknown"
        assert obs.raw_payload["numeric_parse_issues"]["observed.product_cost_value_type"]["reason"] == "non_canonical_value_type"

    def test_domestic_shipping_value_type(self):
        """国内运费同样保留 value_type（起→starting_from，不自动 exact）。"""
        obs = _parse(_v1_payload(observed={
            "product_unit_price_rmb": None, "product_total_cost_rmb": None,
            "product_cost_value_type": None, "page_shipping_rmb": 3.0,
            "page_shipping_value_type": "starting_from",
            "bare_dimensions_cm": {"length": None, "width": None, "height": None}, "bare_weight_g": None,
        }))
        assert obs.domestic_shipping_value_type == "starting_from"


# ==================================================================
# D schema/parser：canonical 统一 + 有限 alias
# ==================================================================


class TestSchemaParserAlignment:
    def test_structure_enums_schema_parser_aligned(self):
        """Prompt/JSON示例/Schema/Parser 的 structure 枚举完全一致（D-14/17）。"""
        for field in ("rigidity", "foldability", "compressibility", "packaging_state_hint", "overall_form"):
            schema_enum = set(
                RecognitionService.RESPONSE_SCHEMA["properties"]["structure"]["properties"][field]["enum"]
            )
            assert schema_enum == set(RecognitionService.STRUCT_CANONICAL[field]), field

    def test_packing_actions_schema_parser_prompt_aligned(self):
        """packing_actions 集合在 Schema/Parser/Prompt 三处一致；stack 不扩 schema（D-17）。"""
        schema_actions = set(
            RecognitionService.RESPONSE_SCHEMA["properties"]["structure"]["properties"]
            ["packing_actions"]["items"]["enum"]
        )
        assert schema_actions == set(RecognitionService.PACKING_ACTIONS_CANONICAL)
        prompt = RecognitionService._prompt(1, include_json_shape=True)
        for action in RecognitionService.PACKING_ACTIONS_CANONICAL:
            assert action in prompt
        obs = _parse(_v1_payload(structure={"packing_actions": ["flat_fold", "stack"]}))
        assert obs.packing_actions == ["flat_fold"]
        issues = obs.raw_payload["numeric_parse_issues"]["structure.packing_actions"]
        assert issues["raw_values"] == ["stack"]
        assert issues["reason"] == "non_canonical_packing_action"

    def test_canonical_foldability_good_kept(self):
        """canonical foldability=good 正常保留（D-14）。"""
        obs = _parse(_v1_payload(structure={"foldability": "good"}))
        assert obs.foldability == "good"

    def test_alias_high_to_good_raw_preserved(self):
        """有限 alias：foldability=high → good，raw 仍保存 high（D-15）。"""
        obs = _parse(_v1_payload(structure={"foldability": "high", "compressibility": "high"}))
        assert obs.foldability == "good"
        assert obs.compressibility == "good"
        assert obs.raw_payload["structure"]["foldability"] == "high"
        assert obs.raw_payload["structure"]["compressibility"] == "high"

    def test_common_explicit_aliases(self):
        """其余常见明确别名：moderate→limited / not_foldable→none / rigid→hard。"""
        obs = _parse(_v1_payload(structure={
            "foldability": "moderate", "compressibility": "not_compressible", "rigidity": "rigid",
        }))
        assert obs.foldability == "limited"
        assert obs.compressibility == "none"
        assert obs.rigidity == "hard"

    def test_unmappable_value_unknown_with_parse_issue(self):
        """无法明确映射的值 → normalized unknown + parse issue，不猜（D-16）。"""
        obs = _parse(_v1_payload(structure={"foldability": "extreme"}))
        assert obs.foldability == "unknown"
        issue = obs.raw_payload["numeric_parse_issues"]["structure.foldability"]
        assert issue["raw_value"] == "extreme"
        assert issue["reason"] == "non_canonical_structure_value"


# ==================================================================
# E evidence：可定位证据才当硬事实
# ==================================================================


class TestFieldEvidenceContract:
    def test_hard_structure_with_located_evidence_is_hard_fact(self):
        """硬结构 true + source_image_index + region + meaning → 可当明确证据（E-18）。"""
        svc = PackagingEstimationService()
        obs = _parse(_v1_payload(
            structure={"has_hard_bottom": True},
            field_evidence={"has_hard_bottom": {
                "source_image_index": 1, "region": "商品主体底部", "raw_text": "", "meaning": "可见硬质底板",
            }},
        ))
        assert svc._has_explicit_rigid_evidence(obs) is True

    def test_hard_structure_without_evidence_not_hard_fact(self):
        """硬结构 true 但无定位 evidence → observation 保留，本地不当硬证据（E-19）。"""
        svc = PackagingEstimationService()
        obs = _parse(_v1_payload(structure={"has_hard_bottom": True}))
        assert obs.has_hard_bottom is True
        assert svc._has_explicit_rigid_evidence(obs) is False

    def test_page_text_evidence_canonical_shape_preserved(self):
        """页面文字证据走 canonical 格式并原样保留在 raw_payload。"""
        evidence = {"has_hard_backboard": {
            "source_image_index": 1, "region": "规格区域", "raw_text": "净重 80g", "meaning": "页面明确裸重",
        }}
        obs = _parse(_v1_payload(structure={"has_hard_backboard": True}, field_evidence=evidence))
        assert obs.raw_payload["field_evidence"]["has_hard_backboard"]["region"] == "规格区域"


# ==================================================================
# F needs_review：真实风险才复核
# ==================================================================


class TestNeedsReviewRealConditions:
    def test_complete_legal_ai_shipment_no_review(self):
        """完整合法 AI shipment、无冲突 → proposal.needs_review=False（F-20）。"""
        service = PackagingEstimationService(calibration_version="safety-test")
        proposal = service.estimate(AIObservation(product_name="袋装商品"), external_proposal=_proposal())
        assert proposal.proposal_source == "ai_candidate"
        assert proposal.needs_review is False
        assert proposal.normal.needs_review is False
        assert proposal.conservative.needs_review is False

    def test_missing_shipment_requires_review(self):
        """shipment 缺失 → needs_review=True（F-21）。"""
        service = PackagingEstimationService(calibration_version="safety-test")
        proposal = service.estimate(AIObservation(product_name="袋装商品"))
        assert proposal.needs_review is True

    def test_semantic_conflict_still_requires_review(self):
        """明确语义冲突（声明压缩但外廓未反映）→ 仍需要复核。"""
        service = PackagingEstimationService(calibration_version="safety-test")
        observation = AIObservation(
            product_name="柔性商品", compressibility="limited",
            length_cm=20, width_cm=15, height_cm=6, weight_g=100,
            weight_scope="net_weight", dimension_scope="product_size",
        )
        proposal = service.estimate(observation, external_proposal=_proposal(weight=130.0))
        assert proposal.needs_review is True

    def test_unknown_structure_field_alone_no_review(self):
        """普通 unknown structure 字段不能单独触发 needs_review（F-23）。"""
        service = PackagingEstimationService(calibration_version="safety-test")
        observation = AIObservation(product_name="袋装商品", rigidity="unknown", foldability="unknown")
        proposal = service.estimate(observation, external_proposal=_proposal())
        assert proposal.needs_review is False

    def test_starting_from_cost_produces_review_reason(self):
        """国内运费 starting_from → 允许计算，但有明确复核 reason（F-22）。"""
        obs = AIObservation(
            product_name="测试商品", product_cost_rmb=5.0, product_cost_value_type="exact",
            domestic_shipping_rmb=3.0, domestic_shipping_value_type="starting_from",
        )
        warnings = cost_review_warnings(obs)
        assert "国内运费为起价/区间下限，实际成本可能更高" in warnings
        # 不弹窗、不阻止：纯原因文本，无异常
        assert cost_review_warnings(AIObservation(domestic_shipping_rmb=3.0, domestic_shipping_value_type="exact")) == []


# ==================================================================
# G raw 洁净：ai_raw 不可变 + product_name 分离（页面级）
# ==================================================================


def _ensure_forwarders(page) -> None:
    settings = page.context.settings_service.load()
    shenzhen = SettingsService.new_forwarder("深圳货代", 80.0, 10.0, 8000.0)
    settings["forwarders"] = [asdict(shenzhen)]
    settings["selected_forwarder_id"] = shenzhen.id
    page.context.settings_service.save(settings)
    page.refresh_settings()


class TestRawCleanliness:
    def test_ui_summary_quantity_not_polluting_ai_raw_product_name(self, page):
        """UI 摘要“卡通袜子｜数量 2双”→ ai_raw.product_name 仍是“卡通袜子”（G-25）。"""
        _ensure_forwarders(page)
        observation = AIObservation(
            product_name="卡通袜子", display_product_summary="卡通袜子",
            quantity=2, quantity_source="page", quantity_unit="双",
            raw_payload={"observation": {"product_name": "卡通袜子"}},
        )
        _complete_visual_ai(page, observation, _proposal())
        assert page.product_summary.text() == "卡通袜子｜数量 2双"
        payload = page.build_record_payload()
        assert payload["layers"]["ai_raw"]["observation"]["product_name"] == "卡通袜子"
        assert payload["product_name"] == "卡通袜子"
        # display summary 才可含数量/单位
        assert "数量 2双" in payload["layers"]["ai_raw"]["observation"]["display_product_summary"] \
            or payload["layers"]["ai_raw"]["observation"]["display_product_summary"] == "卡通袜子"

    def test_user_later_changes_do_not_pollute_ai_raw(self, page):
        """用户后改材质/结构/右卡 → ai_raw.observation 不变化（G-26/27）。"""
        _ensure_forwarders(page)
        observation = AIObservation(
            product_name="测试商品", material="原始材质", requires_shape_retention=None,
            rigidity="soft", raw_payload={"observation": {"product_name": "测试商品"}},
        )
        _complete_visual_ai(page, observation, _proposal())
        # 用户修改页面显示与结构勾选（非程序化）
        page._updating = False
        page.material_summary.setText("用户新材质")
        page.structure_checks["has_frame"].setChecked(True)
        page.conservative_fields["length"].setValue(55.0)
        page.manual_scenarios.add("当前采用")
        page._user_manual_package_fields.add("length_cm")
        payload = page.build_record_payload()
        raw_observation = payload["layers"]["ai_raw"]["observation"]
        assert raw_observation["product_name"] == "测试商品"
        assert raw_observation["material"] == "原始材质"
        assert raw_observation["requires_shape_retention"] is None
        assert raw_observation["rigidity"] == "soft"
        # 用户当前状态进入 adopted / user_modified 层
        assert payload["layers"]["adopted"]["conservative"]["length_cm"] == pytest.approx(55.0)
        assert payload["layers"]["adopted"]["user_modified"] is True
        # current_estimate 反映用户当前采用
        assert payload["_v2"] is not None

    def test_badge_user_manual_edit_neutral_not_need_review(self, page):
        """用户手改当前采用 → 中性“用户已修改”，不能机械变成“需要复核”（F-24）。"""
        _ensure_forwarders(page)
        observation = AIObservation(product_name="测试商品", raw_payload={"observation": {}})
        _complete_visual_ai(page, observation, _proposal())
        assert page.review_badge.text() == "已识别"
        page._updating = False
        page._scenario_manually_changed("当前采用", "length")
        assert page.review_badge.text() == "用户已修改"
        assert page.review_badge.property("warning") is False

    def test_badge_real_conflict_still_need_review(self, page):
        """确有真实风险（成本为起价）→ 仍显示“需要复核”并保留具体 reason。"""
        _ensure_forwarders(page)
        observation = AIObservation(product_name="测试商品", raw_payload={"observation": {}})
        _complete_visual_ai(page, observation, _proposal())
        page.observation.product_cost_rmb = 5.0
        page.observation.product_cost_value_type = "starting_from"
        page._updating = False
        page._scenario_manually_changed("当前采用", "length")
        assert page.review_badge.text() == "需要复核"
        assert page.review_badge.property("warning") is True
        tooltip = page.review_badge.toolTip()
        assert "实际成本可能更高" in tooltip

    def test_reestimate_adoption_badge_neutral(self, page, monkeypatch):
        """接受 AI 重估（无真实风险）→ 中性“已采用修正重估”，不机械“需要复核”。"""
        import profit_accounting_26.ui.pages.calculation_page as calc_page_module

        _ensure_forwarders(page)
        observation = AIObservation(product_name="测试商品", raw_payload={"observation": {}})
        _complete_visual_ai(page, observation, _proposal())
        candidate = _proposal("corrected_reestimate_v1", length=20, width=12, height=1, weight=35)
        from profit_accounting_26.application.local_reestimate_service import LocalReestimateResult

        result = LocalReestimateResult(shipment=candidate.normal, packaging_proposal=candidate)
        monkeypatch.setattr(calc_page_module, "confirm_action", lambda *a, **k: True)
        page._local_reestimate_completed(result)
        assert page.review_badge.text() == "已采用修正重估"
        assert page.review_badge.property("warning") is False

    def test_saved_record_review_reasons_consistent(self, page):
        """保存记录：conservative.needs_review 只反映真实风险，与 proposal 一致。"""
        _ensure_forwarders(page)
        page.product_cost.setValue(5.0)
        page.domestic_shipping.setValue(3.0)
        observation = AIObservation(
            product_name="测试商品",
            product_cost_rmb=5.0, product_cost_value_type="exact",
            domestic_shipping_rmb=3.0, domestic_shipping_value_type="starting_from",
            raw_payload={"observation": {}},
        )
        _complete_visual_ai(page, observation, _proposal())
        payload = page.build_record_payload()
        assert payload["layers"]["adopted"]["conservative"]["needs_review"] is True
        assert payload["layers"]["adopted"]["review_reasons"] != []
        # 无风险记录：needs_review False
        observation2 = AIObservation(product_name="测试商品2", raw_payload={"observation": {}})
        page._updating = False
        page.product_cost.setValue(0.0)
        page.domestic_shipping.setValue(0.0)
        _complete_visual_ai(page, observation2, _proposal())
        payload2 = page.build_record_payload()
        assert payload2["layers"]["adopted"]["conservative"]["needs_review"] is False


# ==================================================================
# 兼容：quantity_unit 可选字段向后兼容（G-28）
# ==================================================================


class TestBackwardCompatibility:
    def test_old_record_without_quantity_unit_loads(self):
        """旧记录没有 quantity_unit → 默认空串，正常读取。"""
        obs = AIObservation.from_dict({"product_name": "旧商品", "quantity": 2, "quantity_source": "page"})
        assert obs.quantity_unit == ""
        assert product_summary(obs) == "旧商品｜数量 ×2"

    def test_new_record_manifest_carries_quantity_facts(self):
        """manifest 自然携带 quantity / quantity_unit / quantity_summary，无新增列。"""
        from profit_accounting_26.application.calibration_export_service import SHEET1_COLUMNS
        assert len(SHEET1_COLUMNS) == 7
        obs = _parse(_v1_payload(quantity={
            "purchase_quantity": 2, "quantity_source": "page", "quantity_unit": "双", "quantity_summary": "2双",
        }))
        initial = _machine_ai_initial({"_v2": {"ai_initial": {"observation": obs.to_dict()}}})
        assert initial["observation"]["quantity"] == 2
        assert initial["observation"]["quantity_unit"] == "双"
        # 经济字段绝不进 manifest
        obs.product_unit_price_rmb = 0.83
        obs.product_total_cost_rmb = 1.66
        initial2 = _machine_ai_initial({"_v2": {"ai_initial": {"observation": obs.to_dict()}}})
        assert "product_unit_price_rmb" not in json.dumps(initial2, ensure_ascii=False)
        assert "product_total_cost_rmb" not in json.dumps(initial2, ensure_ascii=False)
