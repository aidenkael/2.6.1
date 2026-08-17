"""PR #40 本轮（第三次收口）targeted tests：权威事实层 + 700g 捕获 + Prompt v2.0。

任务书第十七节 17 项验收映射：
【1-5  权威事实捕获】1 用户输入 700g 后立即点 AI：发给 Vision AI 的 confirmed_facts 必须含 700；
                      2 AI raw 650：raw=650 / confirmed=700 / UI=700 / 仲裁=700 / 重估=700；
                      3 裸长宽高同规则；4 程序化 AI 回填不升级为 confirmed；5 历史重开 700 仍成立。
【6-10 Prompt v2.0】6 运输态≠展示态强原则；7 可折/压/卷/嵌套/收纳/可拆/可转向；
                     8 把手/肩带/线材/软突出外轮廓变化且无包类特判；
                     9 刚性/易损证据仍允许保形；10 structure 只作证据，不机械生成 shipment。
【11-13 本地边界】11 完整 AI shipment 无 validated 冲突保持 AI 判断；12 Candidate 不影响结果；
                  13 本地不生成 generic 包装。
【14-17 闭环】14 连续局部重估仍完整记录；15 manifest 仍含完整纠偏链；
              16 物流只读当前采用；17 版本仍为 3.0.1。

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
    _machine_reestimate_history,
)
from profit_accounting_26.application.calculation_session import CalculationSession  # noqa: E402
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
              height: float = 6.0, weight: float = 680.0) -> PackagingProposal:
    return PackagingProposal(
        normal=_scenario("AI估算", length=length, width=width, height=height, weight=weight),
        conservative=_scenario("当前采用", length=length, width=width, height=height, weight=weight),
        proposal_source=source,
        engine_version="vision-runtime-v1",
        calibration_version="",
    )


def _raw_ai_650() -> tuple[AIObservation, PackagingProposal]:
    """构造一次 AI raw 返回裸重 650g 的 V1 视觉结果（真实 parse 路径）。"""
    payload = {
        "product_name": "测试商品",
        "observed": {
            "product_price_rmb": None,
            "page_shipping_rmb": None,
            "bare_dimensions_cm": {"length": 26, "width": 16, "height": 5},
            "bare_weight_g": 650,
        },
        "bare_estimate": {"length_cm": None, "width_cm": None, "height_cm": None, "weight_g": None},
        "shipment": {"length_cm": 30, "width_cm": 20, "height_cm": 9, "weight_g": 680, "state": "袋装"},
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


def _v1_response() -> dict:
    return {"choices": [{"message": {"content": json.dumps({
        "product_name": "测试商品",
        "observed": {
            "product_price_rmb": None, "page_shipping_rmb": None,
            "bare_dimensions_cm": {"length": None, "width": None, "height": None},
            "bare_weight_g": None,
        },
        "shipment": {"length_cm": 17, "width_cm": 32, "height_cm": 17, "weight_g": 720, "state": "袋装"},
        "note": "",
    }, ensure_ascii=False)}}]}


def _recognition_service_for_provider(provider: str) -> RecognitionService:
    class Settings:
        @staticmethod
        def load():
            return {"vision_api_timeout_seconds": 30}

    class Profile:
        api_url = "https://example.invalid"
        model_name = "vision-test"

    Profile.provider = provider

    class Store:
        @staticmethod
        def bound_profile(_purpose):
            return Profile(), "secret"

    return RecognitionService(Settings(), Store())


# ==================================================================
# 【1-4】confirmed_facts 捕获主机制：不依赖失焦/editingFinished
# ==================================================================


class TestConfirmedFactsCapture:
    def test_user_typed_weight_immediately_captured(self, page):
        """用户在识图前刚输入 700（焦点仍在输入框，未按回车/未失焦）。"""
        page.bare_weight.spin.setValue(700.0)  # 模拟真实用户编辑（非程序化 setValue）
        facts = page._ai_request_confirmed_facts()
        assert facts["weight_g"]["value"] == 700.0
        assert page.session.confirmed_facts()["weight_g"]["value"] == 700.0
        assert "weight_g" in page._user_edited_bare_fields
        assert page.lbl_bare_weight_source.text() == "用户确认"

    def test_user_typed_dimensions_immediately_captured(self, page):
        """裸长宽高同规则：用户刚输入 30×20×10，立即点 AI 也能进入请求。"""
        page.bare_length.spin.setValue(30.0)
        page.bare_width.spin.setValue(20.0)
        page.bare_height.spin.setValue(10.0)
        facts = page._ai_request_confirmed_facts()
        for key, expected in (("length_cm", 30.0), ("width_cm", 20.0), ("height_cm", 10.0)):
            assert facts[key]["value"] == expected
            assert page.session.confirmed_facts()[key]["value"] == expected
        assert page.lbl_bare_dim_source.text() == "用户确认"

    def test_zero_still_means_unset(self, page):
        """0 尺寸/0 重量仍表示未设置：用户清空后不再进入 confirmed_facts。"""
        page.bare_weight.spin.setValue(700.0)
        assert page.session.confirmed_facts()["weight_g"]["value"] == 700.0
        page.bare_weight.spin.setValue(0.0)  # 用户清空
        facts = page._ai_request_confirmed_facts()
        assert "weight_g" not in facts
        assert "weight_g" not in page.session.confirmed_facts()

    def test_programmatic_fill_never_captured(self, page):
        """程序化 AI 回填不升级为 confirmed：setValue/adapter 路径不进入捕获。"""
        page.bare_weight.setValue(650.0)  # 程序化 setValue（adapter 层，无用户信号）
        assert "weight_g" not in page._user_edited_bare_fields
        assert "weight_g" not in page.session.confirmed_facts()
        page._apply_observation(AIObservation(product_name="测试", weight_g=650.0, weight_scope="unknown"))
        assert "weight_g" not in page.session.confirmed_facts()
        assert "weight_g" not in page._user_edited_bare_fields

    def test_vision_request_content_contains_confirmed_700(self, tmp_path, monkeypatch):
        """实际发送给 Vision AI 的请求内容必须包含用户 700g。"""
        image = tmp_path / "product.png"
        image.write_bytes(b"image")
        captured = {}
        service = _recognition_service_for_provider("DeepSeek")
        monkeypatch.setattr(
            service, "_request_payload",
            lambda **kwargs: captured.update(kwargs) or _v1_response(),
        )
        service.recognize(
            [{"path": str(image)}],
            user_context={"weight_g": {"value": 700.0, "source": "user_confirmed"}},
        )
        fact_text = next(
            item["text"] for item in captured["content"]
            if item["type"] == "text" and item["text"].startswith("confirmed_facts")
        )
        assert '"weight_g"' in fact_text
        assert "700.0" in fact_text

    def test_runtime_receives_page_confirmed_facts(self, page):
        """页面捕获的权威事实进入 Runtime：仲裁用 700，raw 保留 650。"""
        page.bare_weight.spin.setValue(700.0)  # 用户刚输入
        facts = page._ai_request_confirmed_facts()
        assert facts["weight_g"]["value"] == 700.0
        raw = AIObservation(product_name="测试商品", weight_g=650.0, weight_scope="unknown")
        proposal = _proposal(weight=680.0)
        captured: dict = {}

        class _FakeBase:
            def recognize(self, *args, **kwargs):
                captured["user_context"] = kwargs.get("user_context")
                return raw, proposal

        runtime = RuntimeRecognitionService(
            _FakeBase(),
            RuntimePackagingArbitrator(
                _FakePackagingService("formal"),
                _Manager({"metadata": {"builtin": True}}),
                safety_service=_FakePackagingService("safety"),
            ),
        )
        outcome = runtime.recognize([], user_context=facts)
        assert captured["user_context"]["weight_g"]["value"] == 700.0
        assert outcome.raw_observation.weight_g == 650.0
        assert outcome.arbitration_observation.weight_g == 700.0


# ==================================================================
# 【2】AI raw 650：raw/confirmed/UI/仲裁/重估 全链一致
# ==================================================================


class TestFullChain650:
    def test_full_chain_raw_650_confirmed_700(self, page):
        """raw 历史=650、confirmed=700、UI=700、仲裁=700、重估上下文=700 同时成立。"""
        page.session.confirm_value("weight_g", 700.0)
        page.bare_weight.setValue(700.0)
        raw_observation, raw_proposal = _raw_ai_650()
        outcome = _outcome_700(raw_observation, raw_proposal)
        page._diagnostic_operation = page.context.diagnostic_logger.begin_operation("test-round3")
        page._recognition_completed(outcome)
        # raw AI 永久 650（历史/校准层）
        assert page.session.normalized_observation.weight_g == 650.0
        assert page.initial_ai_snapshot["observation"]["weight_g"] == 650.0
        # confirmed 700
        assert page.initial_ai_snapshot["confirmed_facts"]["weight_g"]["value"] == 700.0
        # UI 裸重 700
        assert page.bare_weight.value() == pytest.approx(700.0)
        # 展示/仲裁 observation 700
        assert page.session.observation.weight_g == 700.0
        # 重估上下文（reestimate_packaging 读取同一权威事实源）700
        assert page.session.confirmed_facts()["weight_g"]["value"] == 700.0


# ==================================================================
# 【5】历史重开后 700 仍成立
# ==================================================================


class TestHistoryReload700:
    def test_history_reload_keeps_700_not_650(self, page, monkeypatch):
        _silence_dialogs(monkeypatch)
        _ensure_forwarders(page)
        page.product_cost.setValue(66.80)
        page.domestic_shipping.setValue(28.0)
        page.session.confirm_value("weight_g", 700.0)
        page.bare_weight.setValue(700.0)
        raw_observation, raw_proposal = _raw_ai_650()
        outcome = _outcome_700(raw_observation, raw_proposal)
        page._diagnostic_operation = page.context.diagnostic_logger.begin_operation("test-round3-rec")
        page._recognition_completed(outcome)
        assert page.bare_weight.value() == pytest.approx(700.0)
        page.recalculate()
        page.save_record()
        rid = page.record_id
        # 重开历史：700 不被 raw 650 覆盖
        page.load_record_payload(rid)
        assert page.bare_weight.value() == pytest.approx(700.0)
        assert page.session.confirmed_facts()["weight_g"]["value"] == 700.0
        assert page.session.normalized_observation.weight_g == 650.0
        assert page.lbl_bare_weight_source.text() == "用户确认"


# ==================================================================
# 【6-9】Prompt v2.0：展示态≠运输态 + 全品类运输可变性
# ==================================================================


class TestPromptV20:
    def _text(self) -> str:
        return RecognitionService._prompt(1, include_json_shape=False)

    def test_version_v20(self):
        assert RecognitionService.PROMPT_VERSION == "2.6.1-visual-v2.1"

    def test_display_state_not_transport_state(self):
        """展示态≠运输态恢复为强通用原则，并给出具体处理动作。"""
        prompt = self._text()
        assert "展示态≠运输态" in prompt
        for token in ("折下", "收进", "贴平", "转向", "拆下", "自然压平"):
            assert token in prompt, f"缺少展示态处理动作: {token}"

    def test_transformability_factors(self):
        """Prompt 要求对所有商品统一考虑真实运输形态变化能力。"""
        prompt = self._text()
        for token in ("折叠", "压平", "卷起", "嵌套", "收纳", "可拆卸", "可转向",
                      "空腔", "刚性", "易碎", "保形", "多件"):
            assert token in prompt, f"缺少全品类运输可变性因素: {token}"

    def test_generic_parts_without_bag_specific_rule(self):
        """把手/肩带/线材/软突出是通用运输外轮廓因素；不得包含包类特判。"""
        prompt = self._text()
        for token in ("把手", "肩带", "线材", "软突出"):
            assert token in prompt, f"缺少通用软突出部分因素: {token}"
        for banned in ("包类", "手提包", "背包", "单肩包"):
            assert banned not in prompt, f"Prompt 包含包类特判: {banned}"

    def test_allows_protection_for_rigid_fragile(self):
        """有刚性骨架/不可逆损伤/易碎/必须保形证据时仍允许保护与保形。"""
        prompt = self._text()
        assert "保形" in prompt
        assert "不可逆" in prompt
        assert "retain_shape" in prompt
        assert "不预设压缩，也不预设保形" in prompt

    def test_protrusion_flattenable_restored_in_text_and_example(self):
        """protrusion_flattenable 恢复 AI 观察能力：文本 + JSON 示例均包含。"""
        prompt = RecognitionService._prompt(1, include_json_shape=True)
        assert "protrusion_flattenable" in prompt
        marker = "不要 Markdown：\n"
        idx = prompt.find(marker)
        assert idx >= 0
        shape = json.loads(prompt[idx + len(marker):])
        assert "protrusion_flattenable" in shape["structure"]

    def test_shipment_remains_ai_owned_overall_judgment(self):
        """shipment 仍是 AI 直接整体判断，不是本地规则计算结果。"""
        prompt = self._text()
        assert "AI 拥有最终判断权" in prompt
        assert "正常真实仓库最可能怎么发" in prompt
        assert "shipment.state" in prompt


# ==================================================================
# 【10】structure 只作证据，不机械生成 shipment
# ==================================================================


class TestStructureEvidenceOnly:
    def test_structure_evidence_does_not_drive_shipment(self):
        """即使 structure 声称硬质+必须保形+突出不可压平，AI shipment 原样保留。"""
        payload = {
            "product_name": "测试商品",
            "observed": {
                "product_price_rmb": None, "page_shipping_rmb": None,
                "bare_dimensions_cm": {"length": None, "width": None, "height": None},
                "bare_weight_g": None,
            },
            "bare_estimate": {"length_cm": None, "width_cm": None, "height_cm": None, "weight_g": None},
            "shipment": {"length_cm": 30, "width_cm": 20, "height_cm": 10, "weight_g": 500,
                         "state": "保持形状后箱装"},
            "structure": {
                "rigidity": "hard",
                "requires_shape_retention": True,
                "protrusion_flattenable": False,
                "packing_actions": ["retain_shape"],
            },
            "note": "",
        }
        obs, proposal = RecognitionService._parse_v1_payload(payload, model="test")
        # 结构证据被记录（可审计）
        assert obs.rigidity == "hard"
        assert obs.requires_shape_retention is True
        assert obs.protrusion_flattenable is False
        assert obs.packing_actions == ["retain_shape"]
        # 但 shipment 不被本地重算：完整 AI 判断原样保留
        assert proposal.proposal_source == "vision_ai_v1"
        assert proposal.normal.length_cm == 30.0
        assert proposal.normal.width_cm == 20.0
        assert proposal.normal.height_cm == 10.0
        assert proposal.normal.weight_g == 500.0
        assert proposal.normal.packaging_method == "保持形状后箱装"


# ==================================================================
# 【11-13】本地边界：AI 判断保持 / candidate 不进 Runtime / 无 generic
# ==================================================================


class TestLocalBoundary:
    def test_complete_ai_shipment_preserved_without_validated_conflict(self):
        service = PackagingEstimationService(calibration_version="safety-test")
        result = service.estimate(AIObservation(product_name="测试商品"), external_proposal=_proposal(weight=680.0))
        assert result.proposal_source == "ai_candidate"
        assert result.normal.length_cm == 20.0
        assert result.normal.weight_g == 680.0

    def test_candidate_rule_not_in_runtime(self):
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

    def test_no_generic_packaging_from_local(self):
        service = PackagingEstimationService(calibration_version="safety-test")
        result = service.estimate(AIObservation(product_name="袋装商品"), external_proposal=_proposal())
        assert result.proposal_source == "ai_candidate"
        assert "GENERIC" not in result.applied_profile_ids
        assert result.normal.length_cm == 20.0


# ==================================================================
# 【14-15】重估与 manifest 闭环
# ==================================================================


class TestReestimateAndManifest:
    def test_consecutive_reestimates_recorded_with_700_intact(self, page):
        """连续两次重估（接受+拒绝）都留档，700 硬事实在所有轮次不丢。"""
        page._pending_reestimate_meta = {
            "user_correction": "第一次修正",
            "confirmed_facts": {"weight_g": 700},
            "input_current_adopted": {"length_cm": 30, "width_cm": 20, "height_cm": 9, "weight_g": 680},
        }
        page._record_reestimate_attempt(
            _reestimate_result(length=20, width=12, height=1, weight=35, correction="第一次修正"),
            accepted=True,
        )
        page._pending_reestimate_meta = {
            "user_correction": "第二次修正",
            "confirmed_facts": {"weight_g": 700},
            "input_current_adopted": {"length_cm": 20, "width_cm": 12, "height_cm": 1, "weight_g": 35},
        }
        page._record_reestimate_attempt(
            _reestimate_result(length=20, width=12, height=2, weight=45, correction="第二次修正"),
            accepted=False,
        )
        assert len(page.session.reestimate_history) == 2
        assert page.session.reestimate_history[0]["accepted"] is True
        assert page.session.reestimate_history[1]["accepted"] is False
        assert page.session.reestimate_history[1]["confirmed_facts"] == {"weight_g": 700}
        for entry in page.session.reestimate_history:
            assert entry["confirmed_facts"]["weight_g"] == 700

    def test_manifest_keeps_full_correction_trace(self):
        """manifest machine_facts.reestimate_history 保留完整纠偏链（raw/adopted/accepted）。"""
        payload = {
            "id": "r1",
            "_v2": {
                "ai_initial": {"observation": {"product_name": "测试商品", "weight_g": 650}},
                "reestimate_history": [
                    {
                        "reestimate_id": "E1", "sequence": 1, "timestamp": "t",
                        "user_correction": "打包没有那么大",
                        "confirmed_facts": {"weight_g": 700},
                        "raw_reestimate_proposal": {
                            "normal": {"weight_g": 35}, "conservative": {"weight_g": 35},
                            "proposal_source": "corrected_reestimate_v1",
                        },
                        "adopted_reestimate_proposal": {
                            "normal": {"weight_g": 45}, "conservative": {"weight_g": 45},
                            "proposal_source": "safety",
                        },
                        "arbitration_trace": {"source": "local_reestimate_arbitration"},
                        "model": "m", "provider": "p", "prompt_version": "v1.2", "accepted": True,
                    },
                ],
            },
        }
        history = _machine_reestimate_history(payload)
        assert len(history) == 1
        assert history[0]["confirmed_facts"] == {"weight_g": 700}
        assert history[0]["raw_reestimate_proposal"]["normal"]["weight_g"] == 35
        assert history[0]["adopted_reestimate_proposal"]["normal"]["weight_g"] == 45
        assert history[0]["accepted"] is True


# ==================================================================
# 【16-17】物流只读当前采用；版本 3.0.1
# ==================================================================


class TestLogisticsAndVersion:
    def test_logistics_reads_only_adopted(self):
        session = CalculationSession()
        raw = _proposal(weight=500.0)
        adopted = _proposal("ai_candidate", weight=760.0)
        session.ai_packaging_proposal = raw
        session.adopt(adopted)
        assert session.adopted_packaging.conservative.weight_g == 760.0
        assert session.adopted_packaging.conservative.weight_g != raw.normal.weight_g

    def test_version_kept_3_0_1(self):
        import pathlib

        app_src = pathlib.Path("src/profit_accounting_26/ui/app.py").read_text(encoding="utf-8")
        assert "UU护航 3.0.1" in app_src
