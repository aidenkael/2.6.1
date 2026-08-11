import json
from pathlib import Path


def test_all_77_cal_records_are_archived_without_runtime_role():
    # CAL77 Conservative Migration V1：77 条历史 sample 保留档案，
    # 但全部 enabled=false 退出 runtime；原 role 语义保持不变。
    root = Path(__file__).resolve().parents[2]
    registry = json.loads((root / "calibration/logistics_v2/packaging_rule_registry_v1.json").read_text(encoding="utf-8"))
    sample_rules = registry["sample_rules"]
    assert len(sample_rules) == 77
    assert {item["rule_id"] for item in sample_rules} == {f"CAL-{index:03d}" for index in range(1, 78)}
    assert all(item["enabled"] is False for item in sample_rules)
    assert all(item["role"] in {"numeric_reference", "experience_reference", "guard_only"} for item in sample_rules)
