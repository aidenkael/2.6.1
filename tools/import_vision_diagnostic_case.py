"""Import one diagnostic record into the out-of-repo evaluation data set.

Production ``DiagnosticLogger`` already persists the sanitized provider raw
response (``ai-response.json``) before parsing, plus request/image metadata
(``ai-request.json``), under ``<data_dir>/logs/<timestamp>_<op>_<id>/``.

This importer COPIES and further sanitizes one such operation folder into an
evaluation case skeleton. It never modifies production code or log files.

Usage:
    python tools/import_vision_diagnostic_case.py --diagnostic <诊断目录或 logs 目录>
    python tools/import_vision_diagnostic_case.py --diagnostic <...> --out <数据目录> --case-id <id>

Safety: API keys, Authorization headers, base64 image data and full local
paths are stripped; the final JSON is re-scanned for secret patterns and the
import aborts if anything suspicious remains.
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
from tests.evaluation.vision_packaging.harness.sanitize import (  # noqa: E402
    anonymize_image_metadata,
    sanitize_value,
    scan_for_secrets,
)

RESPONSE_FILE = "ai-response.json"
REQUEST_FILE = "ai-request.json"


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def find_operation_dir(diagnostic: Path) -> Path | None:
    """Accept an operation dir directly, or pick the newest usable one below it."""
    if (diagnostic / RESPONSE_FILE).is_file():
        return diagnostic
    candidates: list[tuple[float, Path]] = []
    if diagnostic.is_dir():
        for child in diagnostic.iterdir():
            response_path = child / RESPONSE_FILE
            if child.is_dir() and response_path.is_file():
                data = _read_json(response_path)
                if data and isinstance(data.get("provider_raw_response"), dict):
                    candidates.append((response_path.stat().st_mtime, child))
    if not candidates:
        return None
    return max(candidates)[1]


def build_case_payload(operation_dir: Path, case_id: str) -> tuple[dict, dict] | None:
    """Return (raw_response, case_metadata) fully sanitized, or None."""
    response = _read_json(operation_dir / RESPONSE_FILE) or {}
    raw_response = response.get("provider_raw_response")
    if not isinstance(raw_response, dict) or not raw_response:
        print("该诊断记录没有可用的 provider_raw_response（可能是请求失败记录）。")
        return None
    request = _read_json(operation_dir / REQUEST_FILE) or {}

    sanitized_response = sanitize_value(raw_response)
    normalized_result = response.get("normalized_result")
    normalized_result = sanitized_value(normalized_result) if isinstance(normalized_result, dict) else None
    images = anonymize_image_metadata(request.get("images"))

    serialized = json.dumps(sanitized_response, ensure_ascii=False)
    findings = scan_for_secrets(serialized)
    if findings:
        print(f"脱敏后仍检测到敏感内容（{', '.join(findings)}），已中止导入。")
        return None

    current_observation = normalized_result.get("observation") if normalized_result else None
    current_packaging = normalized_result.get("external_proposal") if normalized_result else None
    metadata = {
        "case_id": case_id,
        "schema_version": case_io.SCHEMA_VERSION,
        "origin": "real",
        "imported_from_diagnostic": operation_dir.name,
        "imported_at": datetime.now().astimezone().isoformat(),
        "model": str(sanitized_response.get("model") or "unknown-model"),
        "description": "",
        "images": images,
        "image_role_note": "请按张把 image_role 改为 main/dimension/weight/packaging/other",
        "current_observation": current_observation,
        "current_packaging_result": current_packaging,
        "ground_truth": {
            "expected_product_summary": None,
            "expected_material": None,
            "expected_structure": None,
            "bare_dimensions": {"unknown": True},
            "bare_weight": {"unknown": True},
            "normal_packaging": {
                "length_range": None, "width_range": None, "height_range": None,
                "weight_range": None, "acceptable_methods": None,
            },
            "conservative_packaging": None,
            "estimated_package": None,
            "structure_feedback": None,
            "actual_feedback": None,
            "notes": "normal/conservative 为当前引擎 legacy 输出；estimated_package 为 V2 单一主结果预留。全部允许保持 null。",
        },
    }
    return sanitized_response, metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把一次诊断记录导入为离线评测案例（脱敏）")
    parser.add_argument("--diagnostic", required=True,
                        help="诊断操作目录（含 ai-response.json），或其上级 logs 目录（自动选最新可用）")
    parser.add_argument("--out", help="评测数据目录（默认读取环境变量 "
                                       f"{case_io.ENV_DATA_DIR} 或 {case_io.DEFAULT_DATA_DIR}）")
    parser.add_argument("--case-id", help="案例 ID（默认按时间生成）")
    parser.add_argument("--force", action="store_true", help="允许覆盖已存在的同名案例")
    args = parser.parse_args(argv)

    diagnostic = Path(args.diagnostic).expanduser()
    if not diagnostic.exists():
        print(f"诊断路径不存在: {diagnostic}")
        return 2
    operation_dir = find_operation_dir(diagnostic)
    if operation_dir is None:
        print("未找到包含 provider_raw_response 的诊断记录。")
        return 1

    out_dir = case_io.resolve_data_dir(args.out)
    if out_dir is None:
        print(f"请通过 --out 或环境变量 {case_io.ENV_DATA_DIR} 指定仓库外评测数据目录。")
        return 2
    case_id = args.case_id or datetime.now().strftime("case-%Y%m%d-%H%M%S")
    case_dir = Path(out_dir) / "cases" / case_id
    if case_dir.exists() and not args.force:
        print(f"案例已存在: {case_dir}（使用 --force 覆盖）")
        return 1

    payload = build_case_payload(operation_dir, case_id)
    if payload is None:
        return 1
    sanitized_response, metadata = payload

    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / case_io.RAW_RESPONSE_FILE).write_text(
        json.dumps(sanitized_response, ensure_ascii=False, indent=2), encoding="utf-8")
    (case_dir / case_io.CASE_FILE).write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"已导入案例: {case_dir}")
    print(f"来源诊断: {operation_dir}")
    print("下一步：")
    print("  1. 如需图片证据，把对应图片手动复制到 images/ 并在 case.json 登记（仅文件名+角色）；")
    print("  2. 逐张填写 images[].image_role（main/dimension/weight/packaging/other）；")
    print("  3. 填写 ground_truth（允许 unknown、区间、多个可接受包装方式）；")
    print("  4. python tools/evaluate_vision_packaging.py --data-dir " + str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
