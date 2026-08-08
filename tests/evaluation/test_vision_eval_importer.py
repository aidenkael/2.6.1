"""Diagnostic-log importer tests: extraction, sanitization, secret refusal."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_importer_module():
    spec = importlib.util.spec_from_file_location(
        "import_vision_diagnostic_case_under_test",
        ROOT / "tools" / "import_vision_diagnostic_case.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


importer = _load_importer_module()

from tests.evaluation.vision_packaging.harness.sanitize import scan_for_secrets  # noqa: E402


def _write_operation(dir_path: Path, *, raw_response: dict | None, request: dict | None = None) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    response = {"session_id": "s", "operation_id": "o",
                "provider_raw_response": raw_response, "normalized_result": None}
    (dir_path / "ai-response.json").write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
    (dir_path / "ai-request.json").write_text(
        json.dumps(request or {}, ensure_ascii=False), encoding="utf-8")
    return dir_path


def _clean_raw_response() -> dict:
    content = json.dumps({"observation": {"product_name": "示例商品"}, "packaging_proposal": {}},
                         ensure_ascii=False)
    return {"id": "chatcmpl-1", "model": "m",
            "choices": [{"message": {"role": "assistant", "content": content}}]}


@pytest.fixture()
def diagnostic_tree(tmp_path):
    logs = tmp_path / "logs"
    operation = _write_operation(
        logs / "20260808-101010_ai-recognition_ab12cd34",
        raw_response={
            **_clean_raw_response(),
            "authorization": "Bearer should-be-removed",
            "nested": {"api_key": "secret-key-value", "token": "tok"},
            "debug": {"image": "data:image/png;base64,QUJDREVGRw==",
                       "saved_to": "C:\\Users\\SecretUser\\Pictures\\IMG_0001.jpg"},
        },
        request={
            "prompt": "...",
            "images": [{"path": "C:\\Users\\SecretUser\\Pictures\\IMG_0001.jpg",
                          "sha256": "0" * 64, "bytes": 1234, "mime_type": ".jpg",
                          "width": 800, "height": 600}],
        },
    )
    # 一条没有 raw response 的失败记录，importer 不应选中它
    _write_operation(logs / "20260808-090000_ai-recognition_deadbeef", raw_response=None)
    return logs, operation


def test_import_sanitizes_keys_paths_and_data_urls(tmp_path, diagnostic_tree):
    logs, operation = diagnostic_tree
    out_dir = tmp_path / "eval-data"
    exit_code = importer.main(["--diagnostic", str(operation), "--out", str(out_dir),
                               "--case-id", "case-test"])
    assert exit_code == 0
    case_dir = out_dir / "cases" / "case-test"
    raw = json.loads((case_dir / "ai_raw_response.json").read_text(encoding="utf-8"))
    metadata = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))

    serialized = json.dumps(raw, ensure_ascii=False)
    assert "authorization" not in raw
    assert "api_key" not in json.dumps(raw)
    assert "secret-key-value" not in serialized
    assert "[image base64 omitted]" in serialized
    assert "SecretUser" not in serialized
    assert raw["debug"]["saved_to"] == "IMG_0001.jpg"
    assert scan_for_secrets(serialized) == []

    image = metadata["images"][0]
    assert image["file"] == "IMG_0001.jpg"
    assert image["image_role"] == "unknown"
    assert image["sha256"] == "0" * 64
    assert "SecretUser" not in json.dumps(metadata, ensure_ascii=False)
    assert metadata["ground_truth"]["bare_dimensions"] == {"unknown": True}
    assert metadata["ground_truth"]["normal_packaging"]["length_range"] is None


def test_find_operation_dir_picks_only_usable_record(diagnostic_tree):
    logs, operation = diagnostic_tree
    assert importer.find_operation_dir(logs) == operation
    assert importer.find_operation_dir(operation) == operation


def test_import_refuses_when_secret_pattern_remains(tmp_path):
    leaked_content = json.dumps({"note": "sk-" + "a" * 40}, ensure_ascii=False)
    operation = _write_operation(
        tmp_path / "logs" / "20260808-120000_ai-recognition_aa00bb11",
        raw_response={"model": "m", "choices": [{"message": {"content": leaked_content}}]},
    )
    out_dir = tmp_path / "eval-data"
    exit_code = importer.main(["--diagnostic", str(operation), "--out", str(out_dir),
                               "--case-id", "case-leak"])
    assert exit_code == 1
    assert not (out_dir / "cases" / "case-leak").exists()


def test_import_requires_raw_response(tmp_path, capsys):
    operation = _write_operation(tmp_path / "op", raw_response=None)
    exit_code = importer.main(["--diagnostic", str(operation), "--out", str(tmp_path / "out")])
    assert exit_code == 1
    assert "provider_raw_response" in capsys.readouterr().out


def test_import_refuses_overwrite(tmp_path, diagnostic_tree):
    logs, operation = diagnostic_tree
    out_dir = tmp_path / "eval-data"
    assert importer.main(["--diagnostic", str(operation), "--out", str(out_dir),
                          "--case-id", "case-dup"]) == 0
    assert importer.main(["--diagnostic", str(operation), "--out", str(out_dir),
                          "--case-id", "case-dup"]) == 1
    assert importer.main(["--diagnostic", str(operation), "--out", str(out_dir),
                          "--case-id", "case-dup", "--force"]) == 0
