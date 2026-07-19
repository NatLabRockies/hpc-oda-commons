"""Exactness of the opt-in per-window parallelism in RollingTabularModel.

``window_n_jobs`` only changes *how many threads* run the independent per-window
fits; it must never change *what* they compute. These tests pin that guarantee by
running the same evaluation sequentially and in parallel and asserting the full
payloads are identical.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from hpc_oda_commons.models.job_runtime_mlp.model import (
    JobRuntimeMlpConfig,
    JobRuntimeMlpModel,
)

pytest.importorskip("sklearn")

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
_PARTITIONS = ("debug", "compute", "gpu")
_CPUS = (2, 4, 8)


def _rows(n_hours: int = 72) -> list[dict]:
    """One job per hour over several days; runtime is a deterministic function of the
    features (no randomness) so fits are reproducible and the categorical/numeric
    preprocessing has real signal to encode."""
    rows = []
    for i in range(n_hours):
        submit = _BASE + timedelta(hours=i)
        cpus = _CPUS[i % len(_CPUS)]
        part = _PARTITIONS[i % len(_PARTITIONS)]
        runtime = 600.0 + 100.0 * cpus + 50.0 * (i % len(_PARTITIONS))
        rows.append(
            {
                "job_id": i,
                "submit_time": submit,
                "end_time": submit + timedelta(minutes=30),
                "runtime_seconds": runtime,
                "partition": part,
                "allocated_cpus": cpus,
            }
        )
    return rows


def _config(window_n_jobs: int) -> JobRuntimeMlpConfig:
    return JobRuntimeMlpConfig(
        n_windows=12,
        test_window_hours=6,
        training_lookback_days=2,
        hidden_layer_sizes=(8,),
        max_iter=40,
        max_svd_components=4,
        target_max_one_hot_width=16,
        window_n_jobs=window_n_jobs,
    )


def test_parallel_windows_match_sequential_exactly():
    rows = _rows()
    seq = JobRuntimeMlpModel(_config(1)).evaluate(rows)
    par = JobRuntimeMlpModel(_config(4)).evaluate(rows)

    # Scenario sanity: several windows scored across more than one day (so the
    # cross-day preprocessing precompute + refit bookkeeping is actually exercised).
    assert seq["summary"]["windows_scored"] >= 3
    assert seq["summary"]["preprocessing_refits"] >= 2

    # Identical outputs, not merely close: metrics, per-window entries, and summary.
    assert seq["mae"] == par["mae"]
    assert seq["rmse"] == par["rmse"]
    assert seq["summary"] == par["summary"]
    assert seq["windows"] == par["windows"]


def test_parallel_and_sequential_capture_same_artifacts():
    rows = _rows()
    seq = JobRuntimeMlpModel(_config(1)).evaluate(rows, capture_artifacts=True)
    par = JobRuntimeMlpModel(_config(4)).evaluate(rows, capture_artifacts=True)
    # The captured "last scored window" is chosen by split order, not finish order.
    assert seq["_last_model"]["split_time"] == par["_last_model"]["split_time"]
    assert seq["_y_pred"] == par["_y_pred"]
    assert seq["_y_true"] == par["_y_true"]
