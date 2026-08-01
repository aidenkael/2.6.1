import json

from profit_accounting_26.application.diagnostic_logger import DiagnosticLogger


def test_ai_artifacts_exclude_credentials_and_base64(tmp_path):
    logger = DiagnosticLogger(tmp_path, {"log_retention_days": 30})
    logger.ai_artifact("request", {"Authorization": "Bearer secret", "api_key": "secret", "image": "data:image/png;base64,abcd", "path": "x.png"})
    content = next((tmp_path / "logs").glob("ai-request-*.json")).read_text(encoding="utf-8")
    assert "secret" not in content
    assert "base64,abcd" not in content
    assert "x.png" in content


def test_diagnostic_summary_can_describe_missing_ai_fields(tmp_path):
    logger = DiagnosticLogger(tmp_path, {})
    logger.diagnostic_summary(returned_fields=["product_name"], missing_fields=["product_cost_rmb", "weight_g"], parse_error=None)
    data = json.loads((tmp_path / "logs" / "diagnostic_summary.json").read_text(encoding="utf-8"))
    assert data["missing_fields"] == ["product_cost_rmb", "weight_g"]
