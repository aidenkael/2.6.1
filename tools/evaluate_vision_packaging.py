"""Offline evaluation entry for the AI vision / packaging estimation chain.

This tool NEVER calls any API. It replays saved AI raw responses through the
current production parser and arbitration, scores them against human
ground truth, and reports per-layer accuracy.

Usage:
    python tools/evaluate_vision_packaging.py --data-dir <path>
    python tools/evaluate_vision_packaging.py --synthetic
    python tools/evaluate_vision_packaging.py --list-experiments
    python tools/evaluate_vision_packaging.py --data-dir <path> --experiment expA_relaxed_outline_check

Data directory resolution: --data-dir > PROFIT_ACCOUNTING_EVAL_DATA_DIR >
E:\\Profit-Accounting-2.6.1-evaluation-data. Real cases live in
<data-dir>/cases/<case_id>/ and are never stored inside the repository.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.evaluation.vision_packaging.harness import case_io  # noqa: E402
from tests.evaluation.vision_packaging.harness.experiments import EXPERIMENTS, get_strategy  # noqa: E402
from tests.evaluation.vision_packaging.harness.replay import (  # noqa: E402
    build_baseline_service,
    dimension_journey,
    replay_case,
)
from tests.evaluation.vision_packaging.harness.scoring import aggregate_metrics, score_case  # noqa: E402


def _fmt_rate(block: dict) -> str:
    rate = block.get("rate")
    return f"{block['correct']}/{block['graded']} ({'n/a' if rate is None else f'{rate:.1%}'})"


def _print_metrics(metrics: dict) -> None:
    print(f"\n=== 指标（{metrics['label']}）===")
    print(f"案例总数: {metrics['cases_total']}    成功重放: {metrics['cases_replayed']}")
    if metrics["replay_errors"]:
        for item in metrics["replay_errors"]:
            print(f"  重放失败: {item['case_id']} -> {item['error']}")
    print(f"AI 原始候选准确率   ai_candidate_accuracy : {_fmt_rate(metrics['ai_candidate_accuracy'])}")
    print(f"parser 后准确率       parsed_accuracy       : {_fmt_rate(metrics['parsed_accuracy'])}")
    print(f"最终包装准确率      final_accuracy        : {_fmt_rate(metrics['final_accuracy'])}")
    local = metrics["local_processing"]
    improvement = local["local_improvement_rate"]
    print(
        "本地处理效果: improved="
        f"{local['improved']} unchanged={local['unchanged']} degraded={local['degraded']} "
        f"not_graded={local['not_graded']} (local_improvement_rate="
        f"{'n/a' if improvement is None else f'{improvement:.1%}'})"
    )
    degradation = metrics["post_ai_degradation"]
    rate = degradation["post_ai_degradation_rate"]
    print(
        "核心指标 AI正确→Final错误 post_ai_degradation_rate: "
        f"{degradation['count']}/{degradation['ai_correct_count']} "
        f"({'n/a' if rate is None else f'{rate:.1%}'})"
    )
    if degradation["cases"]:
        print("  受影响案例: " + ", ".join(degradation["cases"]))
    business = metrics["business_metrics"]
    mean_error = business["mean_chargeable_weight_error_kg"]
    print(
        "业务指标（仅真实 actual_feedback 可评，不足时输出 unavailable，不编造）: "
        f"可评 {business['available_cases']} 例 / 不可评 {business['unavailable_cases']} 例；"
        f"平均计费重误差 {'n/a' if mean_error is None else f'{mean_error:+.3f} kg'}；"
        f"低估 {len(business['underestimate_cases'])} 例；严重低估(>10%) {len(business['severe_underestimate_cases'])} 例"
    )


def _run_suite(label: str, cases, service) -> dict:
    replays = []
    scores = []
    print(f"\n=== 重放 {label}（{len(cases)} 例）===")
    for case in cases:
        replay = replay_case(case, service)
        score = score_case(replay, case.ground_truth)
        replays.append((case, replay))
        scores.append(score)
        if not replay.ok:
            print(f"[{case.case_id}] 重放失败: {replay.error}")
            continue
        final_normal = (replay.final.get("normal") or {})
        dims = (
            f"{final_normal.get('length_cm')}x{final_normal.get('width_cm')}"
            f"x{final_normal.get('height_cm')}cm {final_normal.get('weight_g')}g"
        )
        verdict = {True: "OK", False: "WRONG", None: "n/a"}
        print(
            f"[{case.case_id}] source={replay.trace.get('proposal_source')} final={dims} "
            f"AI={verdict[score.ai.correct]} FINAL={verdict[score.final.correct]} effect={score.local_effect}"
        )
    metrics = aggregate_metrics(scores, label=label)
    _print_metrics(metrics)
    return {
        "metrics": metrics,
        "cases": [
            {
                "score": score.to_dict(),
                "replay": replay.to_dict(),
                "dimension_journey": dimension_journey(replay),
            }
            for (_, replay), score in zip(replays, scores)
        ],
    }


def _list_experiments() -> int:
    print("可用策略（experiment）：")
    for strategy in EXPERIMENTS.values():
        marker = "baseline（生产规则）" if strategy.is_production_baseline else "实验（仅评测，不影响生产）"
        print(f"- {strategy.experiment_id}: {strategy.name} [{marker}]")
        print(f"    {strategy.description}")
        for requirement in strategy.data_requirements:
            print(f"    需要数据: {requirement}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI识图/包装估算离线评测（不调用任何API）")
    parser.add_argument("--data-dir", help="仓库外真实评测数据目录（默认读取环境变量 "
                                            f"{case_io.ENV_DATA_DIR} 或 {case_io.DEFAULT_DATA_DIR}）")
    parser.add_argument("--experiment", default="baseline", help="baseline 或实验策略 ID（--list-experiments 查看）")
    parser.add_argument("--synthetic", action="store_true", help="额外运行仓库内 synthetic 机制回归案例（不计入真实准确率）")
    parser.add_argument("--case", help="只评测指定 case_id")
    parser.add_argument("--report", help="报告 JSON 输出路径（默认写入数据目录 reports/，不写入仓库）")
    parser.add_argument("--list-experiments", action="store_true", help="列出全部策略后退出")
    args = parser.parse_args(argv)

    if args.list_experiments:
        return _list_experiments()
    try:
        strategy = get_strategy(args.experiment)
    except ValueError as exc:
        print(exc)
        return 2

    service = strategy.build_service(build_baseline_service())
    data_dir = case_io.resolve_data_dir(args.data_dir)

    print("AI识图/包装估算离线评测框架")
    print("注：当前生产引擎 normal/conservative 双档输出在报告中标记为 legacy_current_engine_output，")
    print("    并为 V2 预留单一主结果 estimated_package（本轮不修改生产算法）。")
    print(f"策略: {strategy.experiment_id} - {strategy.name}")
    if not strategy.is_production_baseline:
        print("注意：当前为实验策略，结果只用于对比研究，不代表生产行为。")
    print(f"数据目录: {data_dir if data_dir else '（未找到；用 --data-dir 或环境变量 ' + case_io.ENV_DATA_DIR + ' 指定）'}")

    report: dict = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "strategy": strategy.experiment_id,
        "is_production_baseline": strategy.is_production_baseline,
        "engine_version": service.ENGINE_VERSION,
        "calibration_version": service.calibration_version,
        "suites": {},
    }

    try:
        real_cases = case_io.discover_real_cases(data_dir)
    except case_io.CaseFormatError as exc:
        print(f"案例加载失败: {exc}")
        return 2
    if args.case:
        real_cases = [item for item in real_cases if item.case_id == args.case]

    print(f"\n{len(real_cases)} real evaluation cases")
    if real_cases:
        report["suites"]["real"] = _run_suite("real", real_cases, service)
    else:
        print("评测框架已就绪，需要真实案例。")
        print("下一步：")
        print("  1. 在软件中完成一次 AI 识图（诊断日志会保存 provider raw response）；")
        print("  2. python tools/import_vision_diagnostic_case.py --diagnostic <诊断目录> --out <数据目录>；")
        print("  3. 在生成的 case.json 中填写人工标准（允许 unknown / 区间 / 多个可接受包装方式）；")
        print("  4. 重新运行本命令。")

    if args.synthetic:
        synthetic_cases = case_io.discover_synthetic_cases()
        if args.case:
            synthetic_cases = [item for item in synthetic_cases if item.case_id == args.case]
        print("\n注意：SYNTHETIC 案例为虚构机制回归数据，不计入真实准确率。")
        report["suites"]["synthetic"] = _run_suite("synthetic", synthetic_cases, service)

    report_path = None
    if args.report:
        report_path = Path(args.report).expanduser()
    elif data_dir and report["suites"]:
        reports_dir = Path(data_dir) / "reports"
        try:
            reports_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            report_path = reports_dir / f"evaluation_{strategy.experiment_id}_{stamp}.json"
        except OSError:
            report_path = None
    if report_path is not None:
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\n报告已写入: {report_path}")
        except OSError as exc:
            print(f"\n报告写入失败: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
