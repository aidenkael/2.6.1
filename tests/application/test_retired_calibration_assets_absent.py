from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_retired_bundled_calibration_assets_are_not_shipped():
    retired_paths = (
        ROOT / "calibration/r2",
        ROOT / "calibration/logistics_v2/calibration_all_cleaned_v3.json",
        ROOT / "calibration/logistics_v2/CAL77_CONSERVATIVE_MIGRATION.md",
        ROOT / "calibration/logistics_v2/CALIBRATION_ROUND_02_STATUS.md",
        ROOT / "calibration/logistics_v2/calibration_final_diagnostic_v3.md",
        ROOT / "docs/LOCAL_INTEGRATION_AUDIT.md",
        ROOT / "docs/LOCAL_INPUT_SHA256.txt",
        ROOT / "SHA256SUMS.txt",
    )
    assert all(not path.exists() for path in retired_paths)
