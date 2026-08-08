"""Offline evaluation harness for the AI vision / packaging estimation chain.

This package is TEST-SIDE ONLY. Production code (``src/profit_accounting_26``)
must never import anything from here. The harness only *calls* production
entry points (``RecognitionService.parse_payload`` and
``PackagingEstimationService.estimate``); it never modifies them.
"""

from .case_io import (
    ENV_DATA_DIR,
    SCHEMA_VERSION,
    EvalCase,
    discover_real_cases,
    discover_synthetic_cases,
    load_case,
    resolve_data_dir,
    validate_case_metadata,
)
from .experiments import (
    EXPERIMENTS,
    ExperimentStrategy,
    get_strategy,
)
from .replay import (
    LayeredReplay,
    build_baseline_service,
    replay_case,
)
from .scoring import (
    aggregate_metrics,
    score_case,
)

__all__ = [
    "ENV_DATA_DIR",
    "SCHEMA_VERSION",
    "EvalCase",
    "discover_real_cases",
    "discover_synthetic_cases",
    "load_case",
    "resolve_data_dir",
    "validate_case_metadata",
    "EXPERIMENTS",
    "ExperimentStrategy",
    "get_strategy",
    "LayeredReplay",
    "build_baseline_service",
    "replay_case",
    "aggregate_metrics",
    "score_case",
]
