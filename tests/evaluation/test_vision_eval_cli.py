"""CLI entry tests for tools/evaluate_vision_packaging.py (subprocess)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "evaluate_vision_packaging.py"


def _run_cli(*args: str, tmp_path: Path) -> subprocess.CompletedProcess:
    env = {key: value for key, value in os.environ.items()
           if key != "PROFIT_ACCOUNTING_EVAL_DATA_DIR"}
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True, text=True, encoding="utf-8", timeout=180, env=env, cwd=str(tmp_path),
    )


def test_empty_data_dir_reports_zero_real_cases(tmp_path):
    data_dir = tmp_path / "eval-data"
    data_dir.mkdir()
    result = _run_cli("--data-dir", str(data_dir), tmp_path=tmp_path)
    assert result.returncode == 0
    assert "0 real evaluation cases" in result.stdout
    assert "评测框架已就绪，需要真实案例。" in result.stdout
    assert "import_vision_diagnostic_case" in result.stdout


def test_synthetic_mode_runs_mechanism_regression(tmp_path):
    data_dir = tmp_path / "eval-data"
    data_dir.mkdir()
    result = _run_cli("--data-dir", str(data_dir), "--synthetic", tmp_path=tmp_path)
    assert result.returncode == 0
    assert "0 real evaluation cases" in result.stdout
    assert "SYNTHETIC" in result.stdout
    assert "syn_01_acrylic_coaster" in result.stdout
    assert "post_ai_degradation_rate" in result.stdout
    # synthetic 必须与真实准确率明确区分
    assert "不计入真实准确率" in result.stdout


def test_real_case_is_replayed_and_reported(tmp_path):
    data_dir = tmp_path / "eval-data"
    synthetic_root = ROOT / "tests" / "evaluation" / "vision_packaging" / "synthetic"
    source = synthetic_root / "syn_01_acrylic_coaster"
    target = data_dir / "cases" / "real_like_01"
    target.mkdir(parents=True)
    for name in ("case.json", "ai_raw_response.json"):
        target.joinpath(name).write_bytes((source / name).read_bytes())
    result = _run_cli("--data-dir", str(data_dir), tmp_path=tmp_path)
    assert result.returncode == 0
    assert "1 real evaluation cases" in result.stdout
    assert "source=ai_candidate" in result.stdout
    assert "final_accuracy" in result.stdout
    reports = list((data_dir / "reports").glob("evaluation_baseline_*.json"))
    assert reports, "应把报告写入数据目录而不是仓库"


def test_list_experiments(tmp_path):
    result = _run_cli("--list-experiments", tmp_path=tmp_path)
    assert result.returncode == 0
    for experiment_id in ("baseline", "expA_relaxed_outline_check",
                          "expB_independent_packaging_candidate",
                          "expC_cal_risk_only_for_complete_ai"):
        assert experiment_id in result.stdout


def test_unknown_experiment_is_rejected(tmp_path):
    result = _run_cli("--experiment", "no_such", "--synthetic", tmp_path=tmp_path)
    assert result.returncode == 2
    assert "未知实验" in result.stdout
