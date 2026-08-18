"""PR #40 数量作用域语义收口 targeted tests（任务书第七节 12 项）。

统一语义：
- 裸重 weight_g / bare_estimate.weight_g = 当前页面实际购买/选择的全部商品合计净重
  （不含快递包装材料；一个销售单位本身是多件套时按整套全部组成商品净重合计）。
- 裸尺寸 = 一个销售单位本身的自然未包装裸品尺寸（禁止裸尺寸×数量；
  组合套装无法单一外廓描述时允许 null，由 shipment 整体判断）。
- shipment.weight_g 不得小于当前全部商品裸重。
- 用户手填裸重使用相同语义；旧记录无作用域信息不迁移、不乘数量。

禁止真实 API / 浏览器 / 外部链接。
"""
from __future__ import annotations

import json
import os
import pathlib
from dataclasses import asdict

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from profit_accounting_26.application import AppContext, SettingsService  # noqa: E402
from profit_accounting_26.application.data_contracts import ActualLogistics, record_from_payload  # noqa: E402
from profit_accounting_26.application.local_reestimate_service import LocalReestimateService  # noqa: E402
from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService  # noqa: E402
from profit_accounting_26.application.packaging_presentation import product_summary  # noqa: E402
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


def _observed(**fields) -> dict:
    observed = {
        "product_unit_price_rmb": None, "product_total_cost_rmb": None,
        "product_cost_value_type": None, "page_shipping_rmb": None, "page_shipping_value_type": None,
        "bare_dimensions_cm": {"length": None, "width": None, "height": None},
        "bare_weight_g": None,
    }
    observed.update(fields)
    return observed


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
    page._diagnostic_operation = page.context.diagnostic_logger.begin_operation("test-quantity-scope")
    outcome = RecognitionOutcome(
        raw_observation=observation,
        raw_ai_proposal=proposal,
        adopted_proposal=proposal,
        arbitration_observation=observation,
        arbitration_trace={},
    )
    page._recognition_completed(outcome)


def _ensure_forwarders(page) -> None:
    settings = page.context.settings_service.load()
    shenzhen = SettingsService.new_forwarder("深圳货代", 80.0, 10.0, 8000.0)
    settings["forwarders"] = [asdict(shenzhen)]
    settings["selected_forwarder_id"] = shenzhen.id
    page.context.settings_service.save(settings)
    page.refresh_settings()


# ==================================================================
# 1-6：裸重/裸尺寸唯一语义 + 无本地×数量
# ==================================================================


class TestWeightAndDimensionScope:
    def test_bare_estimate_weight_is_total_not_multiplied(self):
        """quantity=3双，AI 给 bare_estimate.weight_g=60（总裸重）→ 本地不再 ×3（第1项）。"""
        payload = _v1_payload(
            quantity={"purchase_quantity": 3, "quantity_source": "page", "quantity_unit": "双", "quantity_summary": "3双"},
            bare_estimate={"length_cm": 20, "width_cm": 10, "height_cm": 1, "weight_g": 60},
        )
        obs, _ = RecognitionService._parse_v1_payload(payload, model="test")
        assert obs.raw_payload["bare_estimate"]["weight_g"] == 60.0
        # 本地不把 bare_estimate 提升为 weight_g，更不会乘数量
        assert obs.weight_g is None

    def test_no_quantity_multiplication_in_estimation_or_logistics(self):
        """估算与物流路径不存在 ×quantity（第1/6/12项）。"""
        import profit_accounting_26.application.packaging_estimation_service as pes
        from profit_accounting_26.engines.logistics import core as logistics_core

        pes_src = pathlib.Path(pes.__file__).read_text(encoding="utf-8")
        logistics_src = pathlib.Path(logistics_core.__file__).read_text(encoding="utf-8")
        assert "quantity" not in pes_src, "估算服务不得读取 quantity"
        assert "quantity" not in logistics_src, "物流公式不得读取 quantity"

    def test_user_confirmed_total_weight_floor_with_quantity(self):
        """用户手填 60g + quantity=3 → 60g 是总裸重硬事实，shipment 重量不得低于 60g（第2项）。"""
        service = PackagingEstimationService(calibration_version="safety-test")
        observation = AIObservation(
            product_name="测试商品", weight_g=60.0, weight_scope="net_weight",
            quantity=3, quantity_source="page", quantity_unit="双",
        )
        low = service.estimate(observation, external_proposal=_proposal(weight=55.0))
        assert "packaged_weight_below_confirmed_net_weight" in low.rejected_candidates["ai_candidate"]
        ok = service.estimate(observation, external_proposal=_proposal(weight=70.0))
        assert "packaged_weight_below_confirmed_net_weight" not in ok.rejected_candidates.get("ai_candidate", [])

    def test_quantity_1_bare_weight_degenerates_to_single_unit(self):
        """quantity=1 → 裸重语义自然退化为单销售单位净重（第3项）。"""
        payload = _v1_payload(
            quantity={"purchase_quantity": 1, "quantity_source": "page", "quantity_unit": "件", "quantity_summary": "1件"},
            observed=_observed(bare_weight_g=20),
        )
        obs, _ = RecognitionService._parse_v1_payload(payload, model="test")
        assert obs.weight_g == 20
        assert product_summary(obs) == "测试商品｜数量 1件"

    def test_set_sales_unit_total_weight(self):
        """一个销售单位=套装 → AI 可给整套合计裸重，包装后重量下限使用整套合计（第4项）。"""
        payload = _v1_payload(
            quantity={"purchase_quantity": 1, "quantity_source": "page", "quantity_unit": "套", "quantity_summary": "一套含3件"},
            observed=_observed(bare_weight_g=500),
        )
        obs, _ = RecognitionService._parse_v1_payload(payload, model="test")
        assert obs.weight_g == 500
        service = PackagingEstimationService(calibration_version="safety-test")
        low = service.estimate(AIObservation(weight_g=500.0, weight_scope="net_weight"),
                               external_proposal=_proposal(weight=480.0))
        assert "packaged_weight_below_confirmed_net_weight" in low.rejected_candidates["ai_candidate"]

    def test_combo_set_null_dims_shipment_complete(self):
        """不同商品组成套装且无法单一裸尺寸 → 裸尺寸允许 null，shipment 仍完整返回（第5项）。"""
        payload = _v1_payload(
            observed=_observed(bare_weight_g=300),
            bare_estimate={"length_cm": None, "width_cm": None, "height_cm": None, "weight_g": None},
            shipment={"length_cm": 30, "width_cm": 20, "height_cm": 10, "weight_g": 400, "state": "整套袋装"},
            quantity={"purchase_quantity": 1, "quantity_source": "page", "quantity_unit": "套", "quantity_summary": ""},
        )
        obs, proposal = RecognitionService._parse_v1_payload(payload, model="test")
        assert obs.length_cm is None and obs.width_cm is None and obs.height_cm is None
        assert proposal is not None
        assert proposal.normal.is_complete()
        assert proposal.proposal_source == "vision_ai_v1"

    def test_bare_dims_not_multiplied_locally(self):
        """quantity=3 → 裸尺寸保持一个销售单位外廓，本地不自动 ×3（第6项）。"""
        payload = _v1_payload(
            quantity={"purchase_quantity": 3, "quantity_source": "page", "quantity_unit": None, "quantity_summary": ""},
            observed=_observed(bare_dimensions_cm={"length": 20, "width": 10, "height": 5}),
        )
        obs, _ = RecognitionService._parse_v1_payload(payload, model="test")
        assert (obs.length_cm, obs.width_cm, obs.height_cm) == (20.0, 10.0, 5.0)


# ==================================================================
# 7-10：历史 / 重估 / 校准 / 旧记录兼容
# ==================================================================


class TestHistoryReestimateCalibration:
    def test_history_saves_quantity_unit_and_weight(self, page, monkeypatch):
        """历史保存后 quantity / quantity_unit + weight_g（总裸重）均保留（第7项）。"""
        import PySide6.QtWidgets as qw

        monkeypatch.setattr(qw.QMessageBox, "information", lambda *a, **k: None)
        monkeypatch.setattr(qw.QMessageBox, "warning", lambda *a, **k: None)
        _ensure_forwarders(page)
        page.product_cost.setValue(10.0)
        page.domestic_shipping.setValue(5.0)
        observation = AIObservation(
            product_name="测试商品", weight_g=60.0, quantity=3, quantity_source="page", quantity_unit="双",
            raw_payload={"observation": {"product_name": "测试商品"}},
        )
        _complete_visual_ai(page, observation, _proposal())
        page.recalculate()
        page.save_record()
        rid = page.record_id
        assert rid
        v2 = page.context.history_record_v2_service.load_v2(rid)
        initial_observation = v2.ai_initial["observation"]
        assert initial_observation["weight_g"] == 60.0
        assert initial_observation["quantity"] == 3
        assert initial_observation["quantity_unit"] == "双"

    def test_reestimate_confirmed_weight_is_total_bare_weight_hard_fact(self):
        """重估上下文：confirmed weight（当前购买总裸重）继续作为最高优先级硬事实（第8项）。"""
        prompt = LocalReestimateService._context(
            product_name="测试商品", confirmed_facts={"weight_g": 60.0},
            current_shipment={"length_cm": 30, "width_cm": 20, "height_cm": 10, "weight_g": 80},
            user_correction="更大",
        )
        marker = "\n输入：\n"
        idx = prompt.find(marker)
        assert idx >= 0
        payload = json.loads(prompt[idx + len(marker):])
        assert payload["confirmed_facts"]["weight_g"] == 60.0
        assert "最高优先级" in prompt or "不得修改" in prompt
        # 首次 AI 观察的重量与数量也进入上下文（quantity_unit 一起）
        prompt2 = LocalReestimateService._context(
            product_name="测试商品", confirmed_facts={}, current_shipment={}, user_correction="更大",
            initial_ai_observation={"weight_g": 60.0, "quantity": 3, "quantity_unit": "双"},
        )
        assert "weight_g" in prompt2
        assert "quantity_unit" in prompt2

    def test_actual_logistics_semantics_unchanged(self):
        """actual_logistics 仍是唯一真实物流证据；current adopted 只是当前估算（第9项）。"""
        actual = ActualLogistics.from_dict({
            "actual_first_mile_fee_rmb": 12.5, "actual_forwarder": "某货代",
            "evidence_level": "actual_logistics",
        })
        assert actual.actual_first_mile_fee_rmb == 12.5
        data = actual.to_dict()
        assert data["evidence_level"] == "actual_logistics"
        assert "current_estimate" not in data
        assert "quantity" not in data

    def test_legacy_record_scope_not_migrated_or_multiplied(self):
        """旧记录无作用域信息：原样保留，不自动乘数量、不迁移（第10项）。"""
        legacy = {
            "id": "legacy-1",
            "product_name": "旧商品",
            "layers": {
                "ai_raw": {"observation": {"product_name": "旧商品", "weight_g": 20.0}},
                "adopted": {
                    "selected_packaging": "保守档",
                    "normal": {"length_cm": 30, "weight_g": 500},
                    "conservative": {"length_cm": 32, "weight_g": 550},
                },
            },
        }
        record = record_from_payload(legacy)
        legacy_weight = record.ai_initial["legacy_layers_ai_raw"]["observation"]["weight_g"]
        assert legacy_weight == 20.0  # 未乘任何数量、未修改
        assert record.current_estimate["weight_g"] == 550.0


# ==================================================================
# 11-12：Prompt v2.3 + 物流公式零变化
# ==================================================================


class TestPromptV23:
    def test_prompt_version_v23(self):
        assert RecognitionService.PROMPT_VERSION == "2.6.1-visual-v2.3"

    def test_prompt_contains_scope_semantics(self):
        prompt = RecognitionService._prompt(1, include_json_shape=False)
        assert "合计净重" in prompt
        assert "禁止裸尺寸×购买数量" in prompt
        assert "组合套装" in prompt
        assert "shipment.weight_g 不得小于" in prompt
        # 不加入具体商品例子 / 物流费用公式
        for banned in ("袜子", "socks", "手套", "gloves", "/6000", "/8000", "利润率公式"):
            assert banned not in prompt, f"Prompt 包含禁止内容: {banned}"

    def test_logistics_formula_zero_change(self):
        """物流公式零变化：不读取 quantity，也不存在 ×数量逻辑（第12项）。"""
        from profit_accounting_26.engines.logistics import core as logistics_core

        src = pathlib.Path(logistics_core.__file__).read_text(encoding="utf-8")
        assert "quantity" not in src
        assert "weight_g * quantity" not in src
