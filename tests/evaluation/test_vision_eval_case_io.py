"""Case schema / IO tests for the vision-packaging evaluation framework."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.evaluation.vision_packaging.harness import case_io  # noqa: E402


def test_template_metadata_validates_clean():
    template = json.loads(
        (ROOT / "tests/evaluation/vision_packaging/templates/case_template.json").read_text(encoding="utf-8")
    )
    assert case_io.validate_case_metadata(template) == []


def test_invalid_image_role_reported():
    metadata = {"case_id": "x", "images": [{"file": "a.jpg", "image_role": "hero"}]}
    issues = case_io.validate_case_metadata(metadata)
    assert any("image_role" in issue for issue in issues)


def test_all_documented_image_roles_accepted():
    for role in case_io.IMAGE_ROLES:
        metadata = {"case_id": "x", "images": [{"image_role": role}]}
        assert case_io.validate_case_metadata(metadata) == []


def test_invalid_range_reported():
    metadata = {
        "case_id": "x",
        "ground_truth": {"normal_packaging": {"length_range": [10, 5]}},
    }
    issues = case_io.validate_case_metadata(metadata)
    assert any("length_range" in issue for issue in issues)


def test_unknown_ground_truth_is_valid():
    metadata = {
        "case_id": "x",
        "ground_truth": {
            "bare_dimensions": {"unknown": True},
            "bare_weight": {"unknown": True},
            "normal_packaging": None,
        },
    }
    assert case_io.validate_case_metadata(metadata) == []


def test_missing_case_id_reported():
    assert any("case_id" in issue for issue in case_io.validate_case_metadata({}))


def test_resolve_data_dir_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv(case_io.ENV_DATA_DIR, str(tmp_path / "env_dir"))
    assert case_io.resolve_data_dir(str(tmp_path / "explicit")) == tmp_path / "explicit"
    assert case_io.resolve_data_dir() == tmp_path / "env_dir"
    monkeypatch.delenv(case_io.ENV_DATA_DIR)
    # Default path only counts when it actually exists; otherwise None.
    resolved = case_io.resolve_data_dir()
    assert resolved in (None, case_io.DEFAULT_DATA_DIR)


def test_discover_real_cases_empty(tmp_path):
    assert case_io.discover_real_cases(tmp_path) == []
    assert case_io.discover_real_cases(None) == []


def test_load_case_missing_files(tmp_path):
    case_dir = tmp_path / "cases" / "c1"
    case_dir.mkdir(parents=True)
    try:
        case_io.load_case(case_dir)
        raise AssertionError("应当抛出 CaseFormatError")
    except case_io.CaseFormatError:
        pass


def test_synthetic_cases_discovered_and_marked():
    cases = case_io.discover_synthetic_cases()
    assert len(cases) == 3
    assert all(case.origin == "synthetic" for case in cases)
    assert all(case.metadata.get("origin") == "synthetic" for case in cases)


def test_synthetic_cases_pass_schema_validation():
    for case in case_io.discover_synthetic_cases():
        assert case_io.validate_case_metadata(case.metadata) == []
