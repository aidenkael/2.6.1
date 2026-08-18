"""PR #40 最终架构收口 targeted tests（任务书第十五节 30 项验收）。

覆盖：
【用户事实】1-3  用户 700g / AI 600g 全链一致；裸长宽高同规则；AI 程序化值不升级为确认
【Prompt】  4-7  v1.9 减法：核心块 / 正常仓库最可能发货 / structure 辅助 / 无案例无规则
【本地】    8-12 完整 AI 直通 / 软冲突仅 warning / generic 不覆盖 / candidate 不进 Runtime / validated 生效
【重估】    13-17 两次重估都保留 / 不覆盖 / 完整轨迹 / ai_initial 不变 / current_estimate 为最终采用
【历史】    18-21 保存更新不丢不重复 / 重开 700 不被 600 覆盖 / 左卡 raw AI / 右卡最终采用
【导出】    22-25 Excel 7 列 / manifest 五层 / 无经济字段 / Calibration 开放读取且不当 truth
【物流】    26-27 只读右卡 / quantity/structure/raw 不进物流公式
【兼容】    28-30 旧记录可打开 / 旧 manifest 兼容 / 版本 3.0.1

禁止真实 API / 浏览器 / 外部链接。
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

import profit_accounting_26.ui.pages.calculation_page as calc_page_module  # noqa: E402
from profit_accounting_26.application import AppContext, SettingsService  # noqa: E402
from profit_accounting_26.application.calibration_export_service import (  # noqa: E402
    SHEET1_COLUMNS,
    _machine_reestimate_history,
)
from profit_accounting_26.application.calculation_session import CalculationSession  # noqa: E402
from profit_accounting_26.application.data_contracts import (  # noqa: E402
    attach_v2_block,
    record_from_payload,
)
from profit_accounting_26.application.local_reestimate_service import LocalReestimateResult  # noqa: E402
from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService  # noqa: E402
from profit_accounting_26.application.recognition_service import RecognitionService  # noqa: E402
from profit_accounting_26.application.runtime_ai_services import (  # noqa: E402
    RecognitionOutcome,
    RuntimePackagingArbitrator,
    RuntimeRecognitionService,
    apply_confirmed_facts,
)
from profit_accounting_26.domain.models import (  # noqa: E402
    AIObservation,
    PackagingProposal,
    PackagingScenario,
    PackagingState,
)
from profit_accounting_26.ui.pages import CalculationPage  # noqa: E402


# ------------------------------------------------------------------ helpers


def _scenario(label: str, *, length: float, width: float, height: float, weight: float,
              method: str = "袋装发货") -> PackagingScenario:
    return PackagingScenario(
        label=label, packaging_method=method, packaging_state=PackagingState.MODERATE_COMPRESSION,
        length_cm=length, width_cm=width, height_cm=height, weight_g=weight,
        confidence="medium", needs_review=False,
    )


def _proposal(source: str = "vision_ai_v1", *, length: float = 20.0, width: float = 15.0,
              height: float = 6.0, weight: float = 650.0) -> PackagingProposal:
    return PackagingProposal(
        normal=_scenario("AI估算", length=length, width=width, height=height, weight=weight),
        conservative=_scenario("当前采用", length=length, width=width, height=height, weight=weight),
        proposal_source=source,
        engine_version="vision-runtime-v1",
        calibration_version="",
    )


def _raw_ai_600() -> tuple[AIObservation, PackagingProposal]:
    """构造一次 AI raw 返回 600g 的 V1 视觉结果（真实 parse 路径）。"""
    payload = {
        "product_name": "测试包",
        "observed": {
            "product_price_rmb": None,
            "page_shipping_rmb": None,
            "bare_dimensions_cm": {"length": 25, "width": 15, "height": 5},
            "bare_weight_g": 600,
        },
        "bare_estimate": {"length_cm": None, "width_cm": None, "height_cm": None, "weight_g": None},
        "shipment": {"length_cm": 28, "width_cm": 18, "height_cm": 8, "weight_g": 650, "state": "袋装"},
        "note": "",
    }
    response = {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}
    return RecognitionService.parse_payload(response, model="vision-test")


def _outcome_700(raw_observation: AIObservation, raw_proposal: PackagingProposal) -> RecognitionOutcome:
    arbitration = AIObservation.from_dict(raw_observation.to_dict())
    conflicts = apply_confirmed_facts(
        arbitration, {"weight_g": {"value": 700, "source": "user_confirmed"}},
    )
    return RecognitionOutcome(
        raw_observation=raw_observation,
        raw_ai_proposal=raw_proposal,
        adopted_proposal=replace(raw_proposal),
        arbitration_observation=arbitration,
        arbitration_trace={"confirmed_facts_applied": {"weight_g": 700}, "conflicts": conflicts},
    )


class _Manager:
    def __init__(self, package=None):
        self.package = package

    def active_package(self):
        return self.package


class _FakeRecognitionService:
    PROMPT_VERSION = "frozen-test"

    def __init__(self, observation, proposal):
        self.observation = observation
        self.proposal = proposal

    def recognize(self, *args, **kwargs):
        del args, kwargs
        return self.observation, self.proposal


class _FakePackagingService:
    def __init__(self, name: str, registry=None):
        self.name = name
        self.registry = registry or {"aggregate_rules": [], "sample_rules": []}
        self.calibration_version = name

    def estimate(self, observation, *, external_proposal):
        del observation
        ids = [
            str(rule.get("rule_id"))
            for key in ("aggregate_rules", "sample_rules")
            for rule in self.registry.get(key, [])
            if isinstance(rule, dict) and rule.get("enabled", True)
        ]
        return replace(
            external_proposal,
            proposal_source=self.name,
            applied_profile_ids=ids,
            calibration_version=self.calibration_version,
        )


@pytest.fixture
def temp_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


@pytest.fixture
def page(qapp, temp_context):
    widget = CalculationPage(temp_context)
    yield widget
    widget.deleteLater()


def _ensure_forwarders(page):
    settings = page.context.settings_service.load()
    shenzhen = SettingsService.new_forwarder("深圳货代", 80.0, 10.0, 8000.0)
    settings["forwarders"] = [asdict(shenzhen)]
    settings["selected_forwarder_id"] = shenzhen.id
    page.context.settings_service.save(settings)
    page.refresh_settings()
    return shenzhen.id


def _silence_dialogs(monkeypatch):
    import PySide6.QtWidgets as qw

    monkeypatch.setattr(qw.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(qw.QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(calc_page_module, "confirm_action", lambda *a, **k: True)


def _reestimate_result(*, length: float, width: float, height: float, weight: float,
                       correction: str) -> LocalReestimateResult:
    raw = _proposal("corrected_reestimate_v1", length=length, width=width, height=height, weight=weight)
    adopted = _proposal("safety", length=length, width=width, height=height, weight=weight)
    return LocalReestimateResult(
        shipment=adopted.conservative,
        packaging_proposal=adopted,
        reestimate_raw_proposal=raw,
        arbitration_trace={"source": "local_reestimate_arbitration", "confirmed_facts_applied": {"weight_g": 700}},
        model="qwen3.8-max",
        provider="阿里云百炼",
    )


def _adopt_full(page, adopted: PackagingProposal, raw: PackagingProposal | None = None) -> None:
    """adopt + 填充左右卡（模拟完整识图后的页面状态），保证保存链路可用。"""
    page._adopt_packaging(adopted)
    page.apply_proposal(page._adopted_packaging(), raw_proposal=raw)


# ==================================================================
# 【用户事实】1-3
# ==================================================================


class TestUserFactPriority:
    def test_apply_observation_defensively_merges_confirmed_facts(self, page):
        """用户 700g → AI raw 600g：UI 裸重必须显示 700，不得回填 600。"""
        page.session.confirm_value("weight_g", 700.0)
        page.bare_weight.setValue(700.0)  # 用户实际输入
        raw = AIObservation(product_name="测试包", weight_g=600.0, weight_scope="unknown")
        page._apply_observation(raw)
        assert page.bare_weight.value() == pytest.approx(700.0)
        assert page.lbl_bare_weight_source.text() == "用户确认"

    def test_full_chain_user_700_ai_raw_600(self, page):
        """raw=600 / confirmed=700 / UI=700 / arbitration=700 / 重估上下文=700 同时成立。"""
        page.session.confirm_value("weight_g", 700.0)
        page.bare_weight.setValue(700.0)
        raw_observation, raw_proposal = _raw_ai_600()
        outcome = _outcome_700(raw_observation, raw_proposal)
        page._diagnostic_operation = page.context.diagnostic_logger.begin_operation("test-rec")
        page._recognition_completed(outcome)
        # raw AI 永久 600
        assert page.session.normalized_observation.weight_g == 600.0
        assert page.initial_ai_snapshot["observation"]["weight_g"] == 600.0
        # confirmed 700
        assert page.initial_ai_snapshot["confirmed_facts"]["weight_g"]["value"] == 700.0
        # UI 裸重 700
        assert page.bare_weight.value() == pytest.approx(700.0)
        # 展示/仲裁 observation 700
        assert page.session.observation.weight_g == 700.0
        # 重估上下文硬事实 700
        assert page.session.confirmed_facts()["weight_g"]["value"] == 700.0

    def test_bare_dimensions_not_overwritten_by_ai(self, page):
        """裸长宽高同规则：AI 不能覆盖用户确认的 30×20×10。"""
        for field, value in (("length_cm", 30.0), ("width_cm", 20.0), ("height_cm", 10.0)):
            page.session.confirm_value(field, value)
            page.bare_length.setValue(30.0)
            page.bare_width.setValue(20.0)
            page.bare_height.setValue(10.0)
        raw = AIObservation(product_name="测试包", length_cm=25.0, width_cm=15.0, height_cm=5.0)
        page._apply_observation(raw)
        assert page.bare_length.value() == pytest.approx(30.0)
        assert page.bare_width.value() == pytest.approx(20.0)
        assert page.bare_height.value() == pytest.approx(10.0)
        assert page.lbl_bare_dim_source.text() == "用户确认"

    def test_ai_programmatic_fill_not_promoted_to_confirmed(self, page):
        """AI 程序化回填的 600g 只显示，不升级成用户确认事实。"""
        raw = AIObservation(product_name="测试包", weight_g=600.0, weight_scope="unknown")
        page._apply_observation(raw)
        assert page.bare_weight.value() == pytest.approx(600.0)
        assert page.lbl_bare_weight_source.text() == "图片识别"
        assert "weight_g" not in page.session.confirmed_facts()

    def test_runtime_uses_700_in_arbitration_keeps_raw_600(self):
        """RuntimeRecognitionService：仲裁用 700，raw 保留 600。"""
        raw_observation = AIObservation(product_name="测试包", weight_g=600.0, weight_scope="unknown")
        raw_proposal = _proposal(weight=650.0)

        class _CapturingSafety(_FakePackagingService):
            def __init__(self):
                super().__init__("safety")
                self.observation = None

            def estimate(self, observation, *, external_proposal):
                self.observation = observation
                return super().estimate(observation, external_proposal=external_proposal)

        safety = _CapturingSafety()
        runtime = RuntimeRecognitionService(
            _FakeRecognitionService(raw_observation, raw_proposal),
            RuntimePackagingArbitrator(
                _FakePackagingService("formal"),
                _Manager({"metadata": {"builtin": True}}),
                safety_service=safety,
            ),
        )
        outcome = runtime.recognize(
            [], user_context={"confirmed_facts": {"weight_g": {"value": 700.0, "source": "user_confirmed"}}},
        )
        assert outcome.raw_observation.weight_g == 600.0
        assert safety.observation.weight_g == 700.0
        assert outcome.arbitration_trace["conflicts"]["weight_g"]["user_confirmed"] == 700.0


# ==================================================================
# 【Prompt / AI】4-7
# ==================================================================


class TestPromptV19:
    def _text(self) -> str:
        prompt = RecognitionService._prompt(1, include_json_shape=False)
        return prompt

    def test_prompt_keeps_core_blocks(self):
        """包含：页面事实 / bare estimate / sales unit / quantity / shipment。"""
        prompt = self._text()
        assert RecognitionService.PROMPT_VERSION == "2.6.1-visual-v2.3"
        assert "observed" in prompt and "页面事实" in prompt
        assert "bare_estimate" in prompt
        assert "销售单位" in prompt and "purchase_quantity" in prompt
        assert "quantity" in prompt and "shipment" in prompt
        assert "structure" in prompt

    def test_prompt_judges_normal_warehouse_most_likely(self):
        """明确：正常真实仓库最可能怎么发。"""
        prompt = self._text()
        assert "正常真实仓库最可能怎么发" in prompt
        assert "不是\"最安全怎么发\"" in prompt
        assert "不是\"最极限省体积怎么发\"" in prompt

    def test_prompt_structure_is_auxiliary_evidence(self):
        """structure 降级为辅助观察，不得机械推导 shipment。"""
        prompt = self._text()
        assert "辅助观察" in prompt
        assert "不得机械推导 shipment" in prompt
        assert "看起来挺括" in prompt  # 明确禁止无证据推出保形
        assert "semi_rigid" in prompt  # 明确禁止无证据推出不能压缩

    def test_prompt_no_cases_rules_or_formulas(self):
        """无商品案例 / 83 条 / CAL 规则包 / 物流公式。"""
        prompt = self._text()
        for banned in ("83", "案例", "/6000", "/8000", "货代费", "利润率公式",
                       "袜子", "手套", "socks", "gloves", "R1", "R2"):
            assert banned not in prompt, f"Prompt 包含禁止内容: {banned}"

    def test_prompt_no_new_shipping_behavior_field(self):
        """不新增 shipping_behavior 字段，继续用 shipment.state。"""
        assert "shipping_behavior" not in self._text()
        assert "shipment.state" in self._text()

    def test_prompt_text_bounded_sanity(self):
        """v2.0 不再以字符数下降为目标；仅保留宽松上限防止失控膨胀。

        真正约束由内容测试保证（运输可变性 / 展示态≠运输态 / 无品类规则）。
        v2.3 新增裸重/裸尺寸作用域说明（合计净重 + 单销售单位尺寸），上限放宽到 3800。
        """
        prompt = RecognitionService._prompt(1, include_json_shape=True)
        marker = "\n严格按以下 JSON"
        idx = prompt.find(marker)
        text = prompt[:idx] if idx >= 0 else prompt
        assert len(text) < 3800, f"Prompt 文本异常膨胀: {len(text)} chars"
        assert len(text) > 1300, "Prompt 已具备覆盖全品类运输可变性的必要内容"


# ==================================================================
# 【本地】8-12
# ==================================================================


class TestLocalArbitration:
    def test_complete_valid_ai_shipment_passes_without_validated_rules(self):
        service = PackagingEstimationService(calibration_version="safety-test")
        observation = AIObservation(product_name="袋装商品")
        result = service.estimate(observation, external_proposal=_proposal())
        assert result.proposal_source == "ai_candidate"
        assert result.normal.weight_g == 650.0
        assert result.normal.length_cm == 20.0

    def test_soft_structure_conflict_only_warning_needs_review(self):
        service = PackagingEstimationService(calibration_version="safety-test")
        observation = AIObservation(
            product_name="柔性商品", compressibility="limited",
            length_cm=20, width_cm=15, height_cm=6, weight_g=100,
            weight_scope="net_weight", dimension_scope="product_size",
        )
        proposal = service.estimate(observation, external_proposal=_proposal(weight=130.0))
        assert proposal.proposal_source == "ai_candidate"
        assert proposal.normal.weight_g == 130.0
        warnings = proposal.candidate_records["ai_candidate"].get("warnings", [])
        assert "declared_transport_adjustment_not_reflected" in warnings

    def test_generic_candidate_cannot_override_complete_ai_shipment(self):
        service = PackagingEstimationService(calibration_version="safety-test")
        observation = AIObservation(product_name="袋装商品")
        result = service.estimate(observation, external_proposal=_proposal())
        assert result.proposal_source == "ai_candidate"
        assert "GENERIC" not in result.applied_profile_ids
        assert result.normal.length_cm == 20.0

    def test_candidate_rule_never_enters_runtime(self):
        formal = _FakePackagingService(
            "formal",
            registry={"aggregate_rules": [{"rule_id": "CANDIDATE-X", "enabled": True}], "sample_rules": []},
        )
        arbiter = RuntimePackagingArbitrator(
            formal,
            _Manager({"metadata": {"formal_bundle": True, "validated_rule_ids": ["VALIDATED-1"]}}),
            safety_service=_FakePackagingService("safety"),
        )
        result = arbiter.estimate(AIObservation(product_name="item"), external_proposal=_proposal())
        assert result.applied_profile_ids == []

    def test_validated_rule_interface_still_works(self):
        formal = _FakePackagingService(
            "formal",
            registry={"aggregate_rules": [{"rule_id": "VALIDATED-1", "enabled": True}], "sample_rules": []},
        )
        arbiter = RuntimePackagingArbitrator(
            formal,
            _Manager({"metadata": {"formal_bundle": True, "validated_rule_ids": ["VALIDATED-1"]}}),
            safety_service=_FakePackagingService("safety"),
        )
        result = arbiter.estimate(AIObservation(product_name="item"), external_proposal=_proposal())
        assert result.applied_profile_ids == ["VALIDATED-1"]


# ==================================================================
# 【重估】13-17
# ==================================================================


class TestReestimateHistory:
    def test_two_reestimates_both_kept_second_does_not_override_first(self, page):
        page._pending_reestimate_meta = {
            "user_correction": "打包没有那么大",
            "confirmed_facts": {"weight_g": 700},
            "input_current_adopted": {"length_cm": 28, "width_cm": 18, "height_cm": 8, "weight_g": 650},
        }
        page._record_reestimate_attempt(
            _reestimate_result(length=20, width=12, height=1, weight=35, correction="打包没有那么大"),
            accepted=True,
        )
        page._pending_reestimate_meta = {
            "user_correction": "这次又偏低",
            "confirmed_facts": {"weight_g": 700},
            "input_current_adopted": {"length_cm": 20, "width_cm": 12, "height_cm": 1, "weight_g": 35},
        }
        page._record_reestimate_attempt(
            _reestimate_result(length=20, width=12, height=2, weight=45, correction="这次又偏低"),
            accepted=True,
        )
        history = page.session.reestimate_history
        assert len(history) == 2
        assert history[0]["sequence"] == 1
        assert history[1]["sequence"] == 2
        assert history[0]["user_correction"] == "打包没有那么大"
        assert history[1]["user_correction"] == "这次又偏低"
        # 第二次不会覆盖第一次
        assert history[0]["adopted_reestimate_proposal"]["normal"]["weight_g"] == 35.0
        assert history[1]["adopted_reestimate_proposal"]["normal"]["weight_g"] == 45.0

    def test_each_entry_has_full_trace_and_accepted_status(self, page):
        page._pending_reestimate_meta = {
            "user_correction": "更大",
            "confirmed_facts": {"weight_g": 700},
            "input_current_adopted": {"length_cm": 28, "width_cm": 18, "height_cm": 8, "weight_g": 650},
        }
        page._record_reestimate_attempt(
            _reestimate_result(length=30, width=20, height=10, weight=800, correction="更大"),
            accepted=False,
        )
        entry = page.session.reestimate_history[0]
        assert entry["user_correction"] == "更大"
        assert entry["confirmed_facts"] == {"weight_g": 700}
        assert entry["input_current_adopted"]["length_cm"] == 28
        assert entry["raw_reestimate_proposal"]["proposal_source"] == "corrected_reestimate_v1"
        assert entry["adopted_reestimate_proposal"]["proposal_source"] == "safety"
        assert entry["arbitration_trace"]["source"] == "local_reestimate_arbitration"
        assert entry["accepted"] is False
        assert entry["model"] == "qwen3.8-max"
        assert entry["provider"] == "阿里云百炼"
        assert entry["prompt_version"] == "2.6.1-reestimate-v1.2"
        assert entry["timestamp"]

    def test_append_reestimate_dedup_by_id(self):
        session = CalculationSession()
        assert session.append_reestimate({"reestimate_id": "A", "accepted": True}) is True
        assert session.append_reestimate({"reestimate_id": "A", "accepted": False}) is False
        assert len(session.reestimate_history) == 1
        assert session.reestimate_history[0]["accepted"] is True

    def test_ai_initial_never_changes_after_reestimates(self):
        """两次重估并保存：ai_initial 完全不变，只写 reestimate_history / current_estimate。"""
        from profit_accounting_26.application.history_record_service import HistoryRecordV2Service
        from profit_accounting_26.storage import SQLiteStore
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "app.sqlite3")
            store.initialize()
            service = HistoryRecordV2Service(store)
            payload = {"product_name": "测试包", "layers": {"adopted": {}, "calculated": {}}}
            rid = service.create_record(
                payload,
                ai_initial={"observation": {"weight_g": 600.0}, "external_ai_packaging_proposal": {"normal": {"weight_g": 650}}},
                current_estimate={"weight_g": 650},
            )
            # 两次重估轨迹写入 payload 的 _v2 增量
            payload["_v2"] = {"reestimate_history": [
                {"reestimate_id": "E1", "sequence": 1, "accepted": True, "adopted_reestimate_proposal": {"normal": {"weight_g": 35}}},
                {"reestimate_id": "E2", "sequence": 2, "accepted": True, "adopted_reestimate_proposal": {"normal": {"weight_g": 45}}},
            ]}
            service.update_record(rid, payload, current_estimate={"weight_g": 45})
            record = service.load_v2(rid)
            assert record.ai_initial["observation"]["weight_g"] == 600.0
            assert record.ai_initial["external_ai_packaging_proposal"]["normal"]["weight_g"] == 650.0
            assert len(record.reestimate_history) == 2

    def test_current_estimate_equals_final_adopted_after_two_reestimates(self, page, monkeypatch):
        _silence_dialogs(monkeypatch)
        _ensure_forwarders(page)
        page.product_cost.setValue(66.80)
        page.domestic_shipping.setValue(28.0)
        raw_observation, raw_proposal = _raw_ai_600()
        _adopt_full(page, raw_proposal, raw=raw_proposal)
        page._maybe_capture_initial_ai_snapshot(raw_observation, raw_proposal)
        page._local_diagnostic_operation = page.context.diagnostic_logger.begin_operation("test-reestimate")
        # 第一次重估（接受）
        page._pending_reestimate_meta = {
            "user_correction": "打包没有那么大",
            "confirmed_facts": {"weight_g": 700},
            "input_current_adopted": {"length_cm": 28, "width_cm": 18, "height_cm": 8, "weight_g": 650},
        }
        page._local_reestimate_completed(_reestimate_result(length=20, width=12, height=1, weight=35, correction="打包没有那么大"))
        # 第二次重估（接受）
        page._pending_reestimate_meta = {
            "user_correction": "这次又偏低",
            "confirmed_facts": {"weight_g": 700},
            "input_current_adopted": {"length_cm": 20, "width_cm": 12, "height_cm": 1, "weight_g": 35},
        }
        page._local_reestimate_completed(_reestimate_result(length=20, width=12, height=2, weight=45, correction="这次又偏低"))
        page.recalculate()
        page.save_record()
        rid = page.record_id
        assert rid
        v2 = page.context.history_record_v2_service.load_v2(rid)
        assert len(v2.reestimate_history) == 2
        # 最终 current_estimate = 最后一次采用
        assert v2.current_estimate["weight_g"] == pytest.approx(45.0)
        assert v2.current_estimate["length_cm"] == pytest.approx(20.0)
        assert v2.current_estimate["height_cm"] == pytest.approx(2.0)
        # ai_initial 不变
        assert v2.ai_initial["observation"]["weight_g"] == 600.0


# ==================================================================
# 【历史】18-21
# ==================================================================


class TestHistoryReload:
    def test_save_and_resave_keep_reestimate_history_without_duplication(self, page, monkeypatch):
        _silence_dialogs(monkeypatch)
        _ensure_forwarders(page)
        page.product_cost.setValue(66.80)
        page.domestic_shipping.setValue(28.0)
        raw_observation, raw_proposal = _raw_ai_600()
        _adopt_full(page, raw_proposal, raw=raw_proposal)
        page._maybe_capture_initial_ai_snapshot(raw_observation, raw_proposal)
        page._local_diagnostic_operation = page.context.diagnostic_logger.begin_operation("test-reestimate")
        page._pending_reestimate_meta = {
            "user_correction": "打包没有那么大",
            "confirmed_facts": {"weight_g": 700},
            "input_current_adopted": {"length_cm": 28, "width_cm": 18, "height_cm": 8, "weight_g": 650},
        }
        page._local_reestimate_completed(_reestimate_result(length=20, width=12, height=1, weight=35, correction="打包没有那么大"))
        page.recalculate()
        page.save_record()
        rid = page.record_id
        assert page.context.history_record_v2_service.load_v2(rid).reestimate_history[0]["user_correction"] == "打包没有那么大"
        # 再次保存（update）：不丢、不重复
        page.save_record()
        v2 = page.context.history_record_v2_service.load_v2(rid)
        assert len(v2.reestimate_history) == 1
        assert v2.reestimate_history[0]["reestimate_id"] == page.session.reestimate_history[0]["reestimate_id"]

    def test_history_reload_keeps_user_700_not_ai_600(self, page, monkeypatch):
        """保存 → 重开：用户 700g 仍显示 700，raw AI 600g 不覆盖。"""
        _silence_dialogs(monkeypatch)
        _ensure_forwarders(page)
        page.product_cost.setValue(66.80)
        page.domestic_shipping.setValue(28.0)
        page.session.confirm_value("weight_g", 700.0)
        page.bare_weight.setValue(700.0)
        raw_observation, raw_proposal = _raw_ai_600()
        outcome = _outcome_700(raw_observation, raw_proposal)
        page._diagnostic_operation = page.context.diagnostic_logger.begin_operation("test-rec")
        page._recognition_completed(outcome)
        assert page.bare_weight.value() == pytest.approx(700.0)
        page.recalculate()
        page.save_record()
        rid = page.record_id
        # 重开历史
        page.load_record_payload(rid)
        assert page.bare_weight.value() == pytest.approx(700.0)
        assert page.session.confirmed_facts()["weight_g"]["value"] == 700.0
        assert page.session.normalized_observation.weight_g == 600.0
        assert page.lbl_bare_weight_source.text() == "用户确认"
        # 重开后再次 AI 识图（session 已重建 700 硬事实）也不覆盖
        outcome2 = _outcome_700(page.session.normalized_observation, raw_proposal)
        page._diagnostic_operation = page.context.diagnostic_logger.begin_operation("test-rec-2")
        page._recognition_completed(outcome2)
        assert page.bare_weight.value() == pytest.approx(700.0)

    def test_history_reload_left_card_shows_first_raw_ai(self, page, monkeypatch):
        _silence_dialogs(monkeypatch)
        _ensure_forwarders(page)
        page.product_cost.setValue(66.80)
        page.domestic_shipping.setValue(28.0)
        raw_observation, raw_proposal = _raw_ai_600()
        adopted = _proposal("ai_candidate", length=30, width=20, height=10, weight=750)
        _adopt_full(page, adopted, raw=raw_proposal)
        page._maybe_capture_initial_ai_snapshot(raw_observation, raw_proposal)
        page.recalculate()
        page.save_record()
        rid = page.record_id
        page.load_record_payload(rid)
        # 左卡 = 第一次 raw AI（external_ai_packaging_proposal.normal = 28×18×8 / 650g）
        assert page.normal_fields["length"].value() == pytest.approx(28.0)
        assert page.normal_fields["width"].value() == pytest.approx(18.0)
        assert page.normal_fields["height"].value() == pytest.approx(8.0)
        assert page.normal_fields["weight"].value() == pytest.approx(650.0)

    def test_history_reload_right_card_shows_final_adopted(self, page, monkeypatch):
        _silence_dialogs(monkeypatch)
        _ensure_forwarders(page)
        page.product_cost.setValue(66.80)
        page.domestic_shipping.setValue(28.0)
        raw_observation, raw_proposal = _raw_ai_600()
        page._adopt_packaging(raw_proposal)
        page._maybe_capture_initial_ai_snapshot(raw_observation, raw_proposal)
        # 用户把当前采用改成 30×20×10 / 780
        page.conservative_fields["length"].setValue(30.0)
        page.conservative_fields["width"].setValue(20.0)
        page.conservative_fields["height"].setValue(10.0)
        page.conservative_fields["weight"].setValue(780.0)
        page.recalculate()
        page.save_record()
        rid = page.record_id
        page.load_record_payload(rid)
        assert page.conservative_fields["length"].value() == pytest.approx(30.0)
        assert page.conservative_fields["weight"].value() == pytest.approx(780.0)


# ==================================================================
# 【导出】22-25
# ==================================================================


class TestCalibrationExport:
    def test_excel_still_seven_columns(self):
        assert len(SHEET1_COLUMNS) == 7

    def test_manifest_machine_facts_five_layers_with_reestimate_history(self):
        payload = {
            "id": "r1",
            "_v2": {
                "ai_initial": {
                    "observation": {"product_name": "测试包", "weight_g": 600},
                    "external_ai_packaging_proposal": {"normal": {"weight_g": 650}},
                },
                "reestimate_history": [
                    {
                        "reestimate_id": "E1",
                        "sequence": 1,
                        "timestamp": "2026-01-01T00:00:00+00:00",
                        "user_correction": "打包没有那么大",
                        "confirmed_facts": {"weight_g": 700},
                        "raw_reestimate_proposal": {
                            "normal": {"length_cm": 20, "width_cm": 12, "height_cm": 1, "weight_g": 35, "packaging_method": "袋装", "packaging_state": "full_flat_fold", "confidence": "medium", "needs_review": False, "default_fields_used": [], "reasoning_summary": ""},
                            "conservative": {"length_cm": 20, "width_cm": 12, "height_cm": 1, "weight_g": 35, "packaging_method": "袋装", "packaging_state": "full_flat_fold", "confidence": "medium", "needs_review": False, "default_fields_used": [], "reasoning_summary": ""},
                            "proposal_source": "corrected_reestimate_v1",
                        },
                        "adopted_reestimate_proposal": {
                            "normal": {"length_cm": 20, "width_cm": 12, "height_cm": 2, "weight_g": 45, "packaging_method": "袋装", "packaging_state": "moderate_compression", "confidence": "medium", "needs_review": False, "default_fields_used": [], "reasoning_summary": ""},
                            "conservative": {"length_cm": 20, "width_cm": 12, "height_cm": 2, "weight_g": 45, "packaging_method": "袋装", "packaging_state": "moderate_compression", "confidence": "medium", "needs_review": False, "default_fields_used": [], "reasoning_summary": ""},
                            "proposal_source": "safety",
                        },
                        "arbitration_trace": {"source": "local_reestimate_arbitration"},
                        "model": "qwen3.8-max",
                        "provider": "阿里云百炼",
                        "prompt_version": "2.6.1-reestimate-v1.2",
                        "accepted": True,
                        # 经济字段：必须被递归剔除
                        "profit_rmb": 999,
                        "sale_price_usd": 10,
                        "exchange_rate": 7.2,
                    },
                ],
            },
        }
        history = _machine_reestimate_history(payload)
        assert len(history) == 1
        entry = history[0]
        assert entry["user_correction"] == "打包没有那么大"
        assert entry["confirmed_facts"] == {"weight_g": 700}
        assert entry["raw_reestimate_proposal"]["normal"]["weight_g"] == 35
        assert entry["adopted_reestimate_proposal"]["normal"]["weight_g"] == 45
        assert entry["accepted"] is True
        assert entry["model"] == "qwen3.8-max"
        assert entry["prompt_version"] == "2.6.1-reestimate-v1.2"
        assert entry["arbitration_trace"]["source"] == "local_reestimate_arbitration"
        # 经济字段不进入
        for key in ("profit_rmb", "sale_price_usd", "exchange_rate"):
            assert key not in entry

    def test_manifest_five_layer_key_set(self):
        from profit_accounting_26.application.calibration_export_service import (
            _machine_ai_initial,
            _machine_local_adopted,
        )
        payload = {
            "id": "r1",
            "_v2": {
                "ai_initial": {
                    "observation": {"product_name": "测试包", "weight_g": 600},
                    "external_ai_packaging_proposal": {"normal": {"weight_g": 650}},
                    "adopted_packaging": {"normal": {"weight_g": 650}},
                },
                "reestimate_history": [],
            },
        }
        machine_facts = {
            "ai_initial": _machine_ai_initial(payload),
            "local_adopted": _machine_local_adopted(payload["_v2"]["ai_initial"]),
            "user_feedback": None,
            "actual_logistics": None,
            "reestimate_history": _machine_reestimate_history(payload),
        }
        assert set(machine_facts) == {
            "ai_initial", "local_adopted", "user_feedback", "actual_logistics", "reestimate_history",
        }
        assert machine_facts["reestimate_history"] == []

    def test_calibration_agent_reads_history_as_open_dict_not_truth(self):
        """模拟 Logistics-calibration 的开放 dict 读取：能看到新 history，且每条带 accepted 标志。"""
        payload = {
            "id": "r1",
            "_v2": {
                "ai_initial": {"observation": {"product_name": "测试包", "weight_g": 600}},
                "reestimate_history": [
                    {
                        "reestimate_id": "E1", "sequence": 1, "timestamp": "t",
                        "user_correction": "打包没有那么大",
                        "confirmed_facts": {"weight_g": 700},
                        "raw_reestimate_proposal": {"normal": {"weight_g": 35}, "conservative": {"weight_g": 35}, "proposal_source": "corrected_reestimate_v1"},
                        "adopted_reestimate_proposal": {"normal": {"weight_g": 45}, "conservative": {"weight_g": 45}, "proposal_source": "safety"},
                        "arbitration_trace": {"source": "local_reestimate_arbitration"},
                        "model": "m", "provider": "p", "prompt_version": "v1.2", "accepted": True,
                    },
                ],
            },
        }
        record = {"record_id": "r1", "machine_facts": {"ai_initial": {"observation": {"weight_g": 600}}, "reestimate_history": _machine_reestimate_history(payload)}}
        # 与 _fb83_merge.py 相同的开放 dict 读取方式
        mf = record.get("machine_facts") or {}
        ai = mf.get("ai_initial") or {}
        assert ai["observation"]["weight_g"] == 600
        history = mf.get("reestimate_history") or []
        assert len(history) == 1
        # 纠偏过程证据，不是 actual truth：raw 与 adopted 分离 + accepted 标志
        assert history[0]["accepted"] is True
        assert history[0]["raw_reestimate_proposal"]["normal"]["weight_g"] != history[0]["adopted_reestimate_proposal"]["normal"]["weight_g"]


# ==================================================================
# 【物流】26-27
# ==================================================================


class TestLogisticsBoundary:
    def test_logistics_and_profit_use_only_adopted_right_card(self):
        session = CalculationSession()
        raw = _proposal(weight=500.0)
        adopted = _proposal("ai_candidate", weight=760.0)
        session.ai_packaging_proposal = raw
        session.adopt(adopted)
        assert session.adopted_packaging.conservative.weight_g == 760.0
        assert session.adopted_packaging.conservative.weight_g != raw.normal.weight_g

    def test_quantity_structure_ai_raw_not_in_logistics_formula(self):
        import pathlib

        from profit_accounting_26.engines.logistics import core as logistics_core

        src = pathlib.Path(logistics_core.__file__).read_text(encoding="utf-8")
        for token in ("quantity_summary", "requires_shape_retention", "overall_form", "packing_actions"):
            assert token not in src, f"物流公式不应读取 {token}"


# ==================================================================
# 【兼容】28-30
# ==================================================================


class TestCompatibility:
    def test_legacy_record_without_v2_still_opens(self):
        legacy = {
            "id": "legacy-1",
            "product_name": "旧商品",
            "layers": {
                "adopted": {
                    "selected_packaging": "保守档",
                    "normal": {"length_cm": 30, "weight_g": 500},
                    "conservative": {"length_cm": 32, "weight_g": 550},
                },
            },
        }
        record = record_from_payload(legacy)
        assert record.record_id == "legacy-1"
        assert record.reestimate_history == []
        assert record.current_estimate["weight_g"] == 550

    def test_legacy_manifest_without_reestimate_history_compatible(self):
        payload = {"id": "legacy", "_v2": {"ai_initial": {"observation": {"product_name": "旧商品"}}}}
        assert _machine_reestimate_history(payload) == []
        # 旧记录依然能正常构造五层 machine_facts（reestimate_history 为空列表）
        from profit_accounting_26.application.calibration_export_service import _machine_ai_initial
        assert _machine_ai_initial(payload) is not None

    def test_version_kept_3_0_1(self):
        """软件版本由 _version.py 统一管理，入口文件从 _version 导入。"""
        import pathlib

        version_src = pathlib.Path("src/profit_accounting_26/_version.py").read_text(encoding="utf-8")
        assert '"3.0.1"' in version_src
        app_src = pathlib.Path("src/profit_accounting_26/ui/app.py").read_text(encoding="utf-8")
        assert "from profit_accounting_26._version import __version__" in app_src
