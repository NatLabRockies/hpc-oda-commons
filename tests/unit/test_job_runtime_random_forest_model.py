from __future__ import annotations

import math

import pytest

from hpc_oda_commons.models.job_runtime_random_forest.model import (
    JobRuntimeRandomForestConfig,
    JobRuntimeRandomForestModel,
)

pytest.importorskip("sklearn")


def test_random_forest_evaluate_returns_requested_metrics() -> None:
    rows = [
        {
            "job_id": 1,
            "submit_time": "2026-01-01T00:05:00Z",
            "end_time": "2026-01-01T00:20:00Z",
            "runtime_seconds": 840.0,
            "partition": "debug",
            "allocated_cpus": 2,
        },
        {
            "job_id": 2,
            "submit_time": "2026-01-01T01:10:00Z",
            "end_time": "2026-01-01T01:30:00Z",
            "runtime_seconds": 1080.0,
            "partition": "compute",
            "allocated_cpus": 4,
        },
        {
            "job_id": 3,
            "submit_time": "2026-01-01T02:15:00Z",
            "end_time": "2026-01-01T02:33:00Z",
            "runtime_seconds": 1020.0,
            "partition": "debug",
            "allocated_cpus": 2,
        },
    ]
    metric_defs = [
        {"name": "mae", "target": "runtime_seconds"},
        {"name": "rmse", "target": "runtime_seconds"},
        {"name": "underprediction_ratio", "target": "runtime_seconds"},
    ]
    model = JobRuntimeRandomForestModel(
        config=JobRuntimeRandomForestConfig(
            n_windows=2,
            test_window_hours=1,
            training_lookback_days=1,
            n_estimators=8,
            max_depth=3,
            max_svd_components=8,
            target_max_one_hot_width=64,
        )
    )

    payload = model.evaluate(rows, metric_defs=metric_defs)

    assert math.isfinite(payload["mae"]) and payload["mae"] >= 0.0
    assert math.isfinite(payload["rmse"]) and payload["rmse"] >= 0.0
    assert 0.0 <= payload["underprediction_ratio"] <= 100.0
    assert payload["summary"]["windows_scored"] >= 1
