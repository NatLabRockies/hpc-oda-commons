"""Training on log1p(runtime) for the rolling tabular models."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from hpc_oda_commons.benchmark.runner import run_rolling_random_forest
from hpc_oda_commons.models.job_runtime_random_forest.model import (
    JobRuntimeRandomForestConfig,
    JobRuntimeRandomForestModel,
)

pytest.importorskip("sklearn")

METRIC_DEFS = [
    {"name": "mae", "target": "runtime_seconds"},
    {"name": "rmse", "target": "runtime_seconds"},
]


def _heavy_tailed_rows() -> list[dict[str, object]]:
    """Log-normal runtimes, the shape real workloads take.

    The partition and core count set each job's typical runtime; the spread around
    it is wide enough that a squared-error fit is dominated by the longest jobs —
    which is the condition ``log_target`` exists to handle. Seeded, so the fixture
    is the same on every run.
    """
    rng = np.random.RandomState(0)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows: list[dict[str, object]] = []
    for i in range(900):
        submit = base + timedelta(minutes=30 * i)
        partition = ["debug", "standard", "long"][i % 3]
        cores = 1 + (i % 8)
        mu = {"debug": 4.5, "standard": 6.5, "long": 8.5}[partition] + 0.1 * cores
        runtime = float(np.exp(mu + 1.4 * rng.randn()))
        rows.append(
            {
                "job_id": i,
                "submit_time": submit,
                "end_time": submit + timedelta(seconds=runtime),
                "runtime_seconds": runtime,
                "partition": partition,
                "user": f"user_{i % 4}",
                "num_cores_req": cores,
                "requested_seconds": 3600.0 * (1 + (i % 3) * 12),
            }
        )
    return rows


def _model(*, log_target: bool) -> JobRuntimeRandomForestModel:
    return JobRuntimeRandomForestModel(
        config=JobRuntimeRandomForestConfig(
            n_windows=20,
            test_window_hours=6,
            training_lookback_days=10,
            n_estimators=16,
            max_depth=4,
            max_svd_components=8,
            target_max_one_hot_width=64,
            log_target=log_target,
        )
    )


def _median_absolute_percentage_error(payload: dict) -> float:
    true = np.asarray(payload["_y_true"], dtype=float)
    pred = np.asarray(payload["_y_pred"], dtype=float)
    return float(np.median(np.abs(true - pred) / np.maximum(true, 1e-9)) * 100.0)


def test_log_target_predicts_in_seconds_and_stays_finite() -> None:
    """The transform is internal: predictions come back on the original scale."""
    payload = _model(log_target=True).evaluate(
        _heavy_tailed_rows(), metric_defs=METRIC_DEFS, capture_artifacts=True
    )

    assert payload["summary"]["rows_scored"] > 0
    assert all(math.isfinite(p) and p >= 0.0 for p in payload["_y_pred"])
    # Runtime territory (seconds), not log space — expm1 was applied.
    assert max(payload["_y_pred"]) > 1_000.0
    assert math.isfinite(payload["mae"]) and math.isfinite(payload["rmse"])


def test_log_target_improves_the_typical_job() -> None:
    """The point of the option: the median job stops paying for the tail."""
    rows = _heavy_tailed_rows()
    flat = _model(log_target=False).evaluate(rows, metric_defs=METRIC_DEFS, capture_artifacts=True)
    logged = _model(log_target=True).evaluate(rows, metric_defs=METRIC_DEFS, capture_artifacts=True)

    assert flat["summary"]["rows_scored"] == logged["summary"]["rows_scored"]
    # Both halves of "typical": relative error and the median absolute error.
    assert _median_absolute_percentage_error(logged) < 0.8 * _median_absolute_percentage_error(flat)
    assert np.median(np.abs(np.array(logged["_y_true"]) - np.array(logged["_y_pred"]))) < np.median(
        np.abs(np.array(flat["_y_true"]) - np.array(flat["_y_pred"]))
    )


def test_log_target_defaults_to_off() -> None:
    assert JobRuntimeRandomForestConfig().log_target is False


def test_recipe_split_enables_log_target() -> None:
    """`log_target` reaches the model from a recipe's split block."""
    rows = _heavy_tailed_rows()
    split = {"method": "rolling", "n_windows": 20, "test_window_hours": 6}

    flat, _payload, _artifacts = run_rolling_random_forest(
        rows, split=split, metric_defs=METRIC_DEFS
    )
    logged, _payload, _artifacts = run_rolling_random_forest(
        rows, split={**split, "log_target": True}, metric_defs=METRIC_DEFS
    )

    assert flat["mae"] != logged["mae"]
