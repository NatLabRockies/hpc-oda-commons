"""
Benchmark execution logic for HPC ODA Commons models.
"""

from __future__ import annotations

from typing import Any

from hpc_oda_commons.kernel.metrics import (
    compute_regression_metrics_from_defs,
)
from hpc_oda_commons.models.job_runtime_baseline.model import JobRuntimeBaselineModel
from hpc_oda_commons.models.job_runtime_xgboost.model import (
    JobRuntimeXGBoostConfig,
    JobRuntimeXGBoostModel,
)


def run_fixed_baseline(
    rows: list[dict[str, Any]],
    *,
    split: dict[str, Any],
    metric_defs: list[dict[str, Any]],
) -> tuple[dict[str, float], dict[str, Any]]:
    """Run a fixed train/test split benchmark with the baseline model."""
    train_fraction = float(split.get("train_fraction", 0.8))
    n_train = max(1, int(len(rows) * train_fraction))
    train_rows = rows[:n_train]
    test_rows = rows[n_train:] if n_train < len(rows) else rows[:]
    y_true = [float(r["runtime_seconds"]) for r in test_rows]

    model = JobRuntimeBaselineModel()
    model.fit(train_rows)
    y_pred = model.predict(test_rows)

    metrics = compute_regression_metrics_from_defs(y_true, y_pred, metric_defs)
    metrics_payload: dict[str, Any] = {**metrics, "definitions": metric_defs}
    return metrics, metrics_payload


def run_rolling_hourly_xgboost(
    rows: list[dict[str, Any]],
    *,
    split: dict[str, Any],
    metric_defs: list[dict[str, Any]],
    verbose: bool = False,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Run a rolling-hourly benchmark with the XGBoost model."""
    requested = {str(m.get("name", "")) for m in metric_defs}
    unsupported = sorted(requested - {"mae", "rmse"})
    if unsupported:
        raise ValueError(
            "rolling_hourly benchmark currently supports only mae/rmse metrics; "
            f"unsupported: {', '.join(unsupported)}"
        )

    n_recent_hours = int(split.get("n_recent_hours", 1000))
    training_lookback_days = int(split.get("training_lookback_days", 100))
    model = JobRuntimeXGBoostModel(
        config=JobRuntimeXGBoostConfig(
            n_recent_hours=n_recent_hours,
            training_lookback_days=training_lookback_days,
        )
    )
    eval_payload = model.evaluate_hourly(rows, verbose=verbose)

    metrics = {
        "mae": float(eval_payload["mae"]),
        "rmse": float(eval_payload["rmse"]),
    }
    metrics_payload: dict[str, Any] = {**eval_payload, "definitions": metric_defs}
    return metrics, metrics_payload
