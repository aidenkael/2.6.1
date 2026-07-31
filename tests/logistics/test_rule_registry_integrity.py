import json
from pathlib import Path


def test_all_77_cal_records_have_runtime_role():
    root = Path(__file__).resolve().parents[2]
    registry = json.loads((root / "calibration/logistics_v2/packaging_rule_registry_v1.json").read_text(encoding="utf-8"))
    sample_rules = registry["sample_rules"]
    assert len(sample_rules) == 77
    assert {item["rule_id"] for item in sample_rules} == {f"CAL-{index:03d}" for index in range(1, 78)}
    assert all(item["enabled"] for item in sample_rules)
    assert all(item["role"] in {"numeric_reference", "experience_reference", "guard_only"} for item in sample_rules)
