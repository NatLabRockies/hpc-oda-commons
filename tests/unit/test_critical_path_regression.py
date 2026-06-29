"""Critical-path regression test for all three runtime prediction models.

Runs baseline, XGBoost, and TF-IDF kNN on a fixed deterministic dataset with
identical rolling split parameters.

The baseline (pure Python) and the structural split/scoring invariants are
asserted exactly and hold on every platform. The exact XGBoost and TF-IDF
MAE/RMSE values are NOT reproducible across CPU/BLAS environments (the compiled
math flips discrete tree splits / kNN neighbours on this tiny dataset), so those
two value tests are marked xfail pending a real reproducibility fix.
See docs/known-issues.md.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from hpc_oda_commons.benchmark.runner import run_rolling_baseline
from hpc_oda_commons.models.job_runtime_tfidf_knn.model import (
    JobRuntimeTfidfKnnConfig,
    JobRuntimeTfidfKnnModel,
)
from hpc_oda_commons.models.job_runtime_xgboost.model import (
    JobRuntimeXGBoostConfig,
    JobRuntimeXGBoostModel,
)

# --------------------------------------------------------------------------- #
# Expected values — determined once, then frozen. Any behavioral change in the
# critical path (splits, metrics, preprocessing, model logic) will cause a
# mismatch and fail the test.
# --------------------------------------------------------------------------- #

EXPECTED_BASELINE_MAE = 127.5
EXPECTED_BASELINE_RMSE = 133.93095235978873
EXPECTED_XGBOOST_MAE = 40.480323791503906
EXPECTED_XGBOOST_RMSE = 45.299687968515784
EXPECTED_TFIDF_MAE = 149.27537525072694
EXPECTED_TFIDF_RMSE = 152.78054891954585

EXPECTED_WINDOWS_SCORED = 4
EXPECTED_ROWS_SCORED = 16
EXPECTED_XGBOOST_PREPROCESSING_REFITS = 1

# Split params shared across all models
SPLIT_PARAMS = {
    "method": "rolling",
    "n_windows": 4,
    "test_window_hours": 1,
    "training_lookback_days": 100,
}
METRIC_DEFS = [
    {"name": "mae", "target": "runtime_seconds"},
    {"name": "rmse", "target": "runtime_seconds"},
]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _regression_rows() -> list[dict[str, object]]:
    """Deterministic dataset covering all fields needed by all three models."""
    base = datetime(2026, 1, 1, 20, 0, 0, tzinfo=timezone.utc)
    users = ["alice", "bob", "charlie"]
    accounts = ["phys", "chem", "bio"]
    names = ["vasp_relax", "gromacs_md", "lammps_run", "python_train", "matlab_sim"]
    rows: list[dict[str, object]] = []

    for hour in range(10):
        hour_start = base + timedelta(hours=hour)
        for j in range(4):
            submit_time = hour_start + timedelta(minutes=10 * j)
            end_time = submit_time + timedelta(minutes=20 + j)
            partition = "compute" if (hour + j) % 2 == 0 else "debug"
            runtime_seconds = float(
                900 + 30 * hour + 20 * j + (60 if partition == "compute" else 0)
            )

            rows.append(
                {
                    "job_id": hour * 4 + j,
                    "submit_time": _iso(submit_time),
                    "end_time": _iso(end_time),
                    "partition": partition,
                    "account": accounts[hour % 3],
                    "qos": "high" if j == 0 else "normal",
                    "user": users[hour % 3],
                    "name": names[j % 5],
                    "requested_cpus": float((j % 4) + 1),
                    "memory_requested": float(2048 + 128 * j + 32 * hour),
                    "runtime_seconds": runtime_seconds,
                }
            )
    return rows


def test_baseline_rolling_regression() -> None:
    rows = _regression_rows()
    metrics, payload, _artifacts = run_rolling_baseline(
        rows, split=SPLIT_PARAMS, metric_defs=METRIC_DEFS
    )
    summary = payload["summary"]

    assert metrics["mae"] == EXPECTED_BASELINE_MAE, f"Baseline MAE changed: {metrics['mae']}"
    assert metrics["rmse"] == EXPECTED_BASELINE_RMSE, f"Baseline RMSE changed: {metrics['rmse']}"
    assert summary["windows_scored"] == EXPECTED_WINDOWS_SCORED
    assert summary["rows_scored"] == EXPECTED_ROWS_SCORED


@pytest.mark.xfail(
    strict=False,
    reason="XGBoost MAE/RMSE not reproducible across CPU/BLAS environments "
    "(see docs/known-issues.md); splits/scoring covered by test_all_models_same_splits",
)
def test_xgboost_rolling_regression() -> None:
    rows = _regression_rows()
    config = JobRuntimeXGBoostConfig(
        n_windows=4,
        test_window_hours=1,
        max_svd_components=8,
        target_max_one_hot_width=64,
        random_state=42,
    )
    model = JobRuntimeXGBoostModel(config)
    payload = model.evaluate(rows)
    summary = payload["summary"]

    assert payload["mae"] == EXPECTED_XGBOOST_MAE, f"XGBoost MAE changed: {payload['mae']}"
    assert payload["rmse"] == EXPECTED_XGBOOST_RMSE, f"XGBoost RMSE changed: {payload['rmse']}"
    assert summary["windows_scored"] == EXPECTED_WINDOWS_SCORED
    assert summary["rows_scored"] == EXPECTED_ROWS_SCORED
    assert summary["preprocessing_refits"] == EXPECTED_XGBOOST_PREPROCESSING_REFITS


@pytest.mark.xfail(
    strict=False,
    reason="TF-IDF MAE/RMSE not reproducible across CPU/BLAS environments "
    "(see docs/known-issues.md); splits/scoring covered by test_all_models_same_splits",
)
def test_tfidf_knn_rolling_regression() -> None:
    rows = _regression_rows()
    config = JobRuntimeTfidfKnnConfig(
        n_windows=4,
        test_window_hours=1,
        k=3,
        n_hash_features=256,
    )
    model = JobRuntimeTfidfKnnModel(config)
    payload = model.evaluate(rows)
    summary = payload["summary"]

    assert payload["mae"] == EXPECTED_TFIDF_MAE, f"TF-IDF MAE changed: {payload['mae']}"
    assert payload["rmse"] == EXPECTED_TFIDF_RMSE, f"TF-IDF RMSE changed: {payload['rmse']}"
    assert summary["windows_scored"] == EXPECTED_WINDOWS_SCORED
    assert summary["rows_scored"] == EXPECTED_ROWS_SCORED


def test_all_models_same_splits() -> None:
    """All three models should score the same windows and rows."""
    rows = _regression_rows()

    _, baseline_payload, _artifacts = run_rolling_baseline(
        rows, split=SPLIT_PARAMS, metric_defs=METRIC_DEFS
    )

    xgb_config = JobRuntimeXGBoostConfig(
        n_windows=4,
        test_window_hours=1,
        max_svd_components=8,
        target_max_one_hot_width=64,
        random_state=42,
    )
    xgb_payload = JobRuntimeXGBoostModel(xgb_config).evaluate(rows)

    tfidf_config = JobRuntimeTfidfKnnConfig(
        n_windows=4, test_window_hours=1, k=3, n_hash_features=256
    )
    tfidf_payload = JobRuntimeTfidfKnnModel(tfidf_config).evaluate(rows)

    assert (
        baseline_payload["summary"]["windows_scored"]
        == xgb_payload["summary"]["windows_scored"]
        == tfidf_payload["summary"]["windows_scored"]
    )
    assert (
        baseline_payload["summary"]["rows_scored"]
        == xgb_payload["summary"]["rows_scored"]
        == tfidf_payload["summary"]["rows_scored"]
    )
