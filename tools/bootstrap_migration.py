from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

SOURCE_REPOSITORY = "aidenkael/EcommerceSkills"
SOURCE_TAG = "profit-legacy-freeze-20260728-r2"
SOURCE_COMMIT = "d0c07d374c9ee61926de9cd3e01b8c35260c8e5c"


@dataclass(frozen=True)
class Item:
    source: str
    classification: str
    adapted_target: str
    note: str


ITEMS = [
    Item("Profit accounting-Auto/calculation/profit.py", "ADAPT", "src/profit_accounting_26/engines/profit/core.py", "保留正算与反推边界，移除 UI 依赖"),
    Item("Profit accounting-Auto/calculation/logistics.py", "ADAPT", "src/profit_accounting_26/engines/logistics/core.py", "仅保留费用适配层，不平行维护上游算法"),
    Item("Profit accounting-Auto/calculation/profit_adjustments.py", "ADAPT", "src/profit_accounting_26/domain/rules.py", "可配置调整规则，不硬编码补贴"),
    Item("Profit accounting-Auto/calculation/rules.py", "ADAPT", "src/profit_accounting_26/domain/rules.py", "保留规则启停、归档和生命周期语义"),
    Item("Profit accounting-Auto/config/config_manager.py", "ADAPT", "src/profit_accounting_26/application/settings_service.py", "原子 JSON 设置读写"),
    Item("Profit accounting-Auto/config/forwarder_manager.py", "ADAPT", "src/profit_accounting_26/application/settings_service.py", "稳定 ID、启停、归档与恢复"),
    Item("Profit accounting-Auto/config/profit_adjustment_manager.py", "ADAPT", "src/profit_accounting_26/domain/rules.py", "规则持久化语义来源"),
    Item("Profit accounting-Auto/database/db_manager.py", "ADAPT", "src/profit_accounting_26/storage/sqlite_store.py", "新项目独立 SQLite schema，不连接旧库"),
    Item("Profit accounting-Auto/image_intake/image_types.py", "ADAPT", "src/profit_accounting_26/domain/models.py", "收敛为三类图片"),
    Item("Profit accounting-Auto/image_intake/result_models.py", "ADAPT", "src/profit_accounting_26/domain/models.py", "AI/人工/系统/实际四类值分层"),
    Item("Profit accounting-Auto/image_intake/intake_service.py", "ADAPT", "src/profit_accounting_26/application/image_session.py", "临时会话、哈希和导入基础"),
    Item("Profit accounting-Auto/image_intake/intake_controller.py", "REFERENCE_ONLY", "-", "Tkinter 控制器不迁移"),
    Item("Profit accounting-Auto/image_intake/extractors/common.py", "REFERENCE_ONLY", "-", "提取经验留档，正式识别由外部视觉 AI"),
    Item("Profit accounting-Auto/image_intake/extractors/dimension_extractor.py", "REFERENCE_ONLY", "-", "离线参考，不主导正式 UI"),
    Item("Profit accounting-Auto/image_intake/extractors/shein_price_extractor.py", "REFERENCE_ONLY", "-", "SHEIN 核价改为人工输入"),
    Item("Profit accounting-Auto/image_intake/extractors/cost_shipping_extractor.py", "REFERENCE_ONLY", "-", "离线参考"),
    Item("Profit accounting-Auto/tests/test_profit.py", "ADAPT", "tests/profit/", "迁移边界测试"),
    Item("Profit accounting-Auto/tests/test_logistics.py", "ADAPT", "tests/logistics/", "费用拆分测试"),
    Item("Profit accounting-Auto/tests/test_profit_adjustments.py", "ADAPT", "tests/profit/test_adjustments.py", "规则触发测试"),
    Item("Profit accounting-Auto/tests/test_unlimited_forwarders.py", "ADAPT", "tests/logistics/test_logistics_core.py", "动态货代测试"),
    Item("Profit accounting-Auto/docs/Development rules-1.5.md", "DOCUMENT_ONLY", "migration_sources/r2/", "旧项目冻结来源，不指导 2.6"),
    Item("logistics-cost-skill-2.0/logistics_cost/calculator.py", "KEEP", "migration_sources/r2/", "物流唯一上游冻结核心快照"),
    Item("logistics-cost-skill-2.0/logistics_cost/estimator.py", "ADAPT", "migration_sources/r2/", "后续通过正式版本包接入"),
    Item("logistics-cost-skill-2.0/logistics_cost/weight_rules.py", "KEEP", "migration_sources/r2/", "R2 重量规则快照"),
    Item("logistics-cost-skill-2.0/logistics_cost/ai_schema.py", "ADAPT", "migration_sources/r2/", "AI schema 来源快照"),
    Item("logistics-cost-skill-2.0/config/logistics_config.json", "KEEP", "config/logistics_source.json", "配置格式来源；默认值保持可修改"),
    Item("logistics-cost-skill-2.0/tests/test_integration.py", "ADAPT", "tests/logistics/", "兼容测试来源"),
    Item("logistics-cost-skill-2.0/tests/test_replay_validation.py", "ADAPT", "tests/logistics/", "回放验证来源"),
    Item("logistics-cost-skill-2.0/scripts/phase5_replay.py", "ADAPT", "migration_sources/r2/", "回放工具来源快照"),
    Item("logistics-cost-skill-2.0/scripts/phase1_clean_data.py", "ADAPT", "migration_sources/r2/", "清洗工具来源快照"),
    Item("docs/LEGACY_FREEZE.md", "DOCUMENT_ONLY", "migration_sources/r2/", "冻结声明"),
    Item("docs/MIGRATION_SOURCE_MANIFEST.md", "DOCUMENT_ONLY", "migration_sources/r2/", "R2 迁移索引"),
    Item("docs/BRANCH_MERGE_MANIFEST.md", "DOCUMENT_ONLY", "migration_sources/r2/", "R2 合并审计"),
    Item("review_packages/profit-legacy-freeze/final_report.md", "DOCUMENT_ONLY", "migration_sources/r2/", "冻结测试记录"),
    Item("logistics-cost-skill-2.0/docs/LOGISTICS_MAINTENANCE_WORKFLOW.md", "DOCUMENT_ONLY", "migration_sources/r2/", "物流维护唯一流程"),
]

CALIBRATION_FILES = [
    "logistics-cost-skill-2.0/archive/calibration/calibration_samples.json",
    "logistics-cost-skill-2.0/archive/calibration/calibration_samples_cleaned_v1.json",
    "logistics-cost-skill-2.0/archive/calibration/calibration_samples_round_02.json",
]
EXCLUDED_EXAMPLES = {"airpods_case", "folding_sunglasses", "seatbelt_extender"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()


def copy_required(source_root: Path, target_root: Path, item: Item) -> tuple[str, str]:
    source = source_root / item.source
    if not source.is_file():
        raise FileNotFoundError(f"R2 source file missing: {item.source}")
    audit = target_root / "migration_sources" / "r2" / item.source
    audit.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, audit)
    return audit.relative_to(target_root).as_posix(), sha256(audit)


def copy_calibration(source_root: Path, target_root: Path) -> list[tuple[str, str, str]]:
    rows = []
    destination = target_root / "calibration" / "r2"
    destination.mkdir(parents=True, exist_ok=True)
    for relative in CALIBRATION_FILES:
        source = source_root / relative
        if not source.is_file():
            raise FileNotFoundError(relative)
        target = destination / source.name
        shutil.copy2(source, target)
        rows.append((relative, target.relative_to(target_root).as_posix(), sha256(target)))

    examples_root = source_root / "logistics-cost-skill-2.0" / "examples"
    examples_target = destination / "examples"
    examples_target.mkdir(parents=True, exist_ok=True)
    for source in sorted(examples_root.glob("*.json")):
        if any(token in source.stem for token in EXCLUDED_EXAMPLES):
            continue
        target = examples_target / source.name
        shutil.copy2(source, target)
        rows.append((source.relative_to(source_root).as_posix(), target.relative_to(target_root).as_posix(), sha256(target)))
    return rows


def write_manifest(target_root: Path, item_rows, calibration_rows) -> None:
    lines = [
        "# MIGRATION_MANIFEST",
        "",
        f"- source_repository: `{SOURCE_REPOSITORY}`",
        f"- source_tag: `{SOURCE_TAG}`",
        f"- source_commit: `{SOURCE_COMMIT}`",
        "- target_branch: `migration/r2-baseline`",
        "",
        "所有来源均从固定 R2 标签提取。审计副本放在 `migration_sources/r2/`；可执行适配代码只放在 `src/profit_accounting_26/`。旧 Tkinter UI 不迁移。",
        "",
        "## 迁移文件",
        "",
        "| R2 来源 | 分类 | 审计副本 | 2.6 目标 | SHA256 | 说明 |",
        "|---|---|---|---|---|---|",
    ]
    for item, audit, digest in item_rows:
        lines.append(
            f"| `{item.source}` | {item.classification} | `{audit}` | `{item.adapted_target}` | `{digest}` | {item.note} |"
        )
    lines += [
        "",
        "## 校准与示例",
        "",
        "| R2 来源 | 分类 | 目标 | SHA256 |",
        "|---|---|---|---|",
    ]
    for source, target, digest in calibration_rows:
        lines.append(f"| `{source}` | KEEP | `{target}` | `{digest}` |")
    lines += [
        "",
        "## 明确排除",
        "",
        "- 旧 Tkinter 主窗口、ProductPage、历史页和 OCR 对话框的可执行迁移；",
        "- 旧 SQLite 真实数据库、真实图片和测试会话；",
        "- `.venv`、缓存、构建产物、Token、Cookie、API Key、浏览器 Profile 和压缩包；",
        "- `airpods_case`、`folding_sunglasses`、`seatbelt_extender` 三份下一轮校准数据。",
        "",
    ]
    (target_root / "MIGRATION_MANIFEST.md").write_text("\n".join(lines), encoding="utf-8")


def write_provenance(target_root: Path, actual_commit: str, example_count: int) -> None:
    text = f"""# SOURCE_PROVENANCE

- source_repository: `{SOURCE_REPOSITORY}`
- source_tag: `{SOURCE_TAG}`
- declared_source_commit: `{SOURCE_COMMIT}`
- verified_checkout_commit: `{actual_commit}`
- target_repository: `aidenkael/Profit-Accounting-2.6`
- target_branch: `migration/r2-baseline`
- authority: `Development rules-2.6.md`
- migrated_ai_json_examples: `{example_count}`

验证结果：来源 checkout Commit 与冻结 Commit 完全一致。迁移工作流未读取浮动 `master`、旧分支或本地未提交内容。

物流关系：`logistics-cost-skill-2.0` 仍是算法与校准的唯一开发上游；本仓库保存 R2 发布基线和兼容接口，不在两边平行修改算法。
"""
    (target_root / "SOURCE_PROVENANCE.md").write_text(text, encoding="utf-8")


def write_checksums(target_root: Path) -> None:
    excluded_parts = {".git", ".venv", ".venv-311", "__pycache__", ".pytest_cache", ".artifacts"}
    rows = []
    for path in sorted(target_root.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS.txt":
            continue
        if any(part in excluded_parts for part in path.relative_to(target_root).parts):
            continue
        rows.append(f"{sha256(path)}  {path.relative_to(target_root).as_posix()}")
    (target_root / "SHA256SUMS.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target", default=Path.cwd(), type=Path)
    args = parser.parse_args()
    source_root = args.source.resolve()
    target_root = args.target.resolve()

    actual_commit = git_head(source_root)
    if actual_commit != SOURCE_COMMIT:
        raise RuntimeError(f"Source commit mismatch: {actual_commit} != {SOURCE_COMMIT}")

    item_rows = []
    for item in ITEMS:
        audit, digest = copy_required(source_root, target_root, item)
        item_rows.append((item, audit, digest))
    calibration_rows = copy_calibration(source_root, target_root)
    example_count = sum(1 for source, _, _ in calibration_rows if "/examples/" in source)
    write_manifest(target_root, item_rows, calibration_rows)
    write_provenance(target_root, actual_commit, example_count)
    write_checksums(target_root)
    print(json.dumps({"source_commit": actual_commit, "items": len(item_rows), "calibration_and_examples": len(calibration_rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
