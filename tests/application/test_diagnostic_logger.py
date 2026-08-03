import json
import os
from datetime import UTC, datetime, timedelta

from profit_accounting_26.application.diagnostic_logger import DiagnosticLogger


def test_each_operation_has_the_four_fixed_files(tmp_path):
    logger = DiagnosticLogger(tmp_path, {"log_retention_days": 30})
    first = logger.begin_operation("ai-recognition")
    second = logger.begin_operation("local-reestimate")
    expected = {"events.jsonl", "ai-request.json", "ai-response.json", "diagnostic_summary.json"}
    assert {item.name for item in first.root.iterdir()} == expected
    assert {item.name for item in second.root.iterdir()} == expected
    assert first.root != second.root


def test_operation_artifacts_exclude_credentials_and_base64(tmp_path):
    operation = DiagnosticLogger(tmp_path, {}).begin_operation("ai-recognition")
    operation.request(Authorization="Bearer secret", api_key="secret", image="data:image/png;base64,abcd", path="x.png")
    operation.response(cookie="secret-cookie", provider_raw_response={"image": "data:image/png;base64,more"})
    content = "\n".join(path.read_text(encoding="utf-8") for path in operation.root.iterdir())
    assert "secret" not in content
    assert "base64,abcd" not in content
    assert "base64,more" not in content
    assert "x.png" in content


def test_summary_truthfully_records_missing_fields_and_no_packaging(tmp_path):
    operation = DiagnosticLogger(tmp_path, {}).begin_operation("ai-recognition")
    operation.summary(
        returned_fields=["product_name"], missing_fields=["product_cost_rmb", "weight_g"],
        packaging_generated=False, normal_packaging=None, conservative_packaging=None,
        not_generated_reason=["missing dimensions and weight"],
    )
    data = json.loads((operation.root / "diagnostic_summary.json").read_text(encoding="utf-8"))
    assert data["missing_fields"] == ["product_cost_rmb", "weight_g"]
    assert data["packaging_generated"] is False
    assert data["normal_packaging"] is None


def test_retention_removes_only_expired_operation_directories(tmp_path):
    logger = DiagnosticLogger(tmp_path, {"log_retention_days": 1})
    old = logger.begin_operation("ai-recognition").root
    old_time = (datetime.now(UTC) - timedelta(days=2)).timestamp()
    os.utime(old, (old_time, old_time))
    fresh = logger.begin_operation("ai-recognition").root
    DiagnosticLogger(tmp_path, {"log_retention_days": 1})
    assert not old.exists()
    assert fresh.exists()
