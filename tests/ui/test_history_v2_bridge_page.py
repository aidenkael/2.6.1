"""CalculationPage 首次 AI 快照捕获测试（History V2 ai_initial 唯一来源）。"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from profit_accounting_26.domain.models import AIObservation, PackagingProposal, PackagingScenario


@pytest.fixture()
def temp_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    from profit_accounting_26.application import AppContext

    return AppContext.create_default()


def _proposal() -> PackagingProposal:
    normal = PackagingScenario(
        label="正常档", packaging_method="袋装",
        length_cm=10, width_cm=8, height_cm=2, weight_g=50,
    )
    conservative = PackagingScenario(
        label="保守档", packaging_method="盒装",
        length_cm=12, width_cm=10, height_cm=3, weight_g=60,
    )
    return PackagingProposal(normal=normal, conservative=conservative)


def _observation(model: str) -> AIObservation:
    observation = AIObservation()
    observation.model = model
    observation.prompt_version = "pv-test"
    observation.length_cm = 10
    return observation


def test_initial_ai_snapshot_captured_only_once(qapp, temp_context):
    from profit_accounting_26.ui.pages import CalculationPage

    page = CalculationPage(temp_context)
    try:
        assert page.initial_ai_snapshot is None
        # 第一次完整识图：捕获
        page._maybe_capture_initial_ai_snapshot(_observation("model-1"), _proposal())
        first = page.initial_ai_snapshot
        assert first is not None
        assert first["model"] == "model-1"
        assert first["prompt_version"] == "pv-test"
        assert first["engine_version"]
        assert first["calibration_version"]
        assert first["observation"]["model"] == "model-1"
        assert first["external_ai_packaging_proposal"] is not None
        assert first["adopted_packaging"] is None  # 未完成页面采纳时不写假值
        # 第二次整体识图：不得覆盖
        page._maybe_capture_initial_ai_snapshot(_observation("model-2"), None)
        assert page.initial_ai_snapshot == first
        assert page.initial_ai_snapshot["model"] == "model-1"
        # 局部重估不经过捕获入口：状态保持不变
        assert page.initial_ai_snapshot["observation"]["model"] == "model-1"
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_clear_new_resets_initial_ai_snapshot(qapp, temp_context):
    from profit_accounting_26.ui.pages import CalculationPage

    page = CalculationPage(temp_context)
    try:
        page._maybe_capture_initial_ai_snapshot(_observation("model-1"), _proposal())
        assert page.initial_ai_snapshot is not None
        page.clear_new()
        assert page.initial_ai_snapshot is None
    finally:
        page.deleteLater()
        qapp.processEvents()
