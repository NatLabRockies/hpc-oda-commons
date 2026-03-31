"""
Benchmark execution logic for HPC ODA Commons models.
"""

from __future__ import annotations

import math
from typing import Any

from tqdm import tqdm

from hpc_oda_commons.kernel.metrics import (
    compute_regression_metrics,
    compute_regression_metrics_from_defs,
)
from hpc_oda_commons.models.job_runtime_baseline.model import JobRuntimeBaselineModel
from hpc_oda_commons.models.job_runtime_tfidf_knn.model import (
    JobRuntimeTfidfKnnConfig,
    JobRuntimeTfidfKnnModel,
)
from hpc_oda_commons.models.job_runtime_xgboost.model import (
    JobRuntimeXGBoostConfig,
    JobRuntimeXGBoostModel,
)
from hpc_oda_commons.models.job_runtime_xgboost.split import (
    build_rolling_splits,
    materialize_split_rows,
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


def _filter_runtime_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only rows with a finite runtime_seconds value."""
    result: list[dict[str, Any]] = []
    for row in rows:
        raw = row.get("runtime_seconds")
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        result.append(row)
    return result


def run_rolling_baseline(
    rows: list[dict[str, Any]],
    *,
    split: dict[str, Any],
    metric_defs: list[dict[str, Any]],
    verbose: bool = False,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Run a rolling benchmark with the baseline model."""
    requested = {str(m.get("name", "")) for m in metric_defs}
    unsupported = sorted(requested - {"mae", "rmse"})
    if unsupported:
        raise ValueError(
            "rolling benchmark currently supports only mae/rmse metrics; "
            f"unsupported: {', '.join(unsupported)}"
        )

    n_windows = int(split.get("n_windows", 1000))
    test_window_hours = int(split.get("test_window_hours", 6))
    training_lookback_days = int(split.get("training_lookback_days", 100))

    splits = build_rolling_splits(
        rows,
        n_windows=n_windows,
        test_window_hours=test_window_hours,
        training_lookback_days=training_lookback_days,
        verbose=verbose,
    )

    window_entries: list[dict[str, Any]] = []
    all_y_true: list[float] = []
    all_y_pred: list[float] = []

    if verbose:
        print(
            "[baseline][verbose] starting rolling evaluation "
            f"splits={len(splits)} "
            f"n_windows={n_windows} "
            f"training_lookback_days={training_lookback_days}"
        )

    split_iter = tqdm(
        splits,
        desc="rolling/baseline",
        unit="window",
        disable=not verbose,
    )

    for s in split_iter:
        train_rows, test_rows = materialize_split_rows(rows, s)
        train_supervised = _filter_runtime_rows(train_rows)
        test_supervised = _filter_runtime_rows(test_rows)

        if len(train_supervised) < 1:
            window_entries.append(
                {
                    **s.to_dict(),
                    "status": "skipped",
                    "reason": "insufficient_training_rows",
                    "train_rows_supervised": 0,
                    "test_rows_supervised": len(test_supervised),
                    "metrics": None,
                }
            )
            if verbose:
                print(
                    f"[baseline][verbose] split={s.split_time_iso} status=skipped "
                    f"reason=insufficient_training_rows train=0 test={len(test_supervised)}"
                )
            continue

        if len(test_supervised) < 1:
            window_entries.append(
                {
                    **s.to_dict(),
                    "status": "skipped",
                    "reason": "insufficient_test_rows",
                    "train_rows_supervised": len(train_supervised),
                    "test_rows_supervised": 0,
                    "metrics": None,
                }
            )
            if verbose:
                print(
                    f"[baseline][verbose] split={s.split_time_iso} status=skipped "
                    f"reason=insufficient_test_rows train={len(train_supervised)} test=0"
                )
            continue

        model = JobRuntimeBaselineModel()
        model.fit(train_supervised)
        y_pred = model.predict(test_supervised)
        y_true = [float(r["runtime_seconds"]) for r in test_supervised]

        window_metrics = compute_regression_metrics(y_true, y_pred)
        all_y_true.extend(y_true)
        all_y_pred.extend(y_pred)

        if verbose:
            print(
                f"[baseline][verbose] split={s.split_time_iso} status=ok "
                f"train={len(train_supervised)} test={len(test_supervised)} "
                f"mae={window_metrics['mae']:.6f} rmse={window_metrics['rmse']:.6f}"
            )

        window_entries.append(
            {
                **s.to_dict(),
                "status": "ok",
                "reason": None,
                "train_rows_supervised": len(train_supervised),
                "test_rows_supervised": len(test_supervised),
                "metrics": window_metrics,
            }
        )

    if not all_y_true:
        raise ValueError("No rolling splits produced scored predictions.")

    global_metrics = compute_regression_metrics(all_y_true, all_y_pred)
    windows_scored = sum(1 for e in window_entries if e["status"] == "ok")

    summary = {
        "windows_total": len(splits),
        "windows_scored": windows_scored,
        "windows_skipped": len(splits) - windows_scored,
        "rows_scored": len(all_y_true),
        "n_windows": n_windows,
        "test_window_hours": test_window_hours,
        "training_lookback_days": training_lookback_days,
    }

    if verbose:
        print(
            "[baseline][verbose] summary "
            f"windows_total={summary['windows_total']} "
            f"windows_scored={summary['windows_scored']} "
            f"windows_skipped={summary['windows_skipped']} "
            f"rows_scored={summary['rows_scored']} "
            f"mae={global_metrics['mae']:.6f} rmse={global_metrics['rmse']:.6f}"
        )

    metrics = {"mae": float(global_metrics["mae"]), "rmse": float(global_metrics["rmse"])}
    eval_payload: dict[str, Any] = {
        **global_metrics,
        "definitions": metric_defs,
        "windows": window_entries,
        "summary": summary,
    }
    return metrics, eval_payload


def run_rolling_xgboost(
    rows: list[dict[str, Any]],
    *,
    split: dict[str, Any],
    metric_defs: list[dict[str, Any]],
    verbose: bool = False,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Run a rolling benchmark with the XGBoost model."""
    requested = {str(m.get("name", "")) for m in metric_defs}
    unsupported = sorted(requested - {"mae", "rmse"})
    if unsupported:
        raise ValueError(
            "rolling benchmark currently supports only mae/rmse metrics; "
            f"unsupported: {', '.join(unsupported)}"
        )

    n_windows = int(split.get("n_windows", 1000))
    test_window_hours = int(split.get("test_window_hours", 6))
    training_lookback_days = int(split.get("training_lookback_days", 100))
    model = JobRuntimeXGBoostModel(
        config=JobRuntimeXGBoostConfig(
            n_windows=n_windows,
            test_window_hours=test_window_hours,
            training_lookback_days=training_lookback_days,
        )
    )
    eval_payload = model.evaluate(rows, verbose=verbose)

    metrics = {
        "mae": float(eval_payload["mae"]),
        "rmse": float(eval_payload["rmse"]),
    }
    metrics_payload: dict[str, Any] = {**eval_payload, "definitions": metric_defs}
    return metrics, metrics_payload


def run_rolling_tfidf_knn(
    rows: list[dict[str, Any]],
    *,
    split: dict[str, Any],
    metric_defs: list[dict[str, Any]],
    verbose: bool = False,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Run a rolling benchmark with the TF-IDF + kNN model."""
    requested = {str(m.get("name", "")) for m in metric_defs}
    unsupported = sorted(requested - {"mae", "rmse"})
    if unsupported:
        raise ValueError(
            "rolling benchmark currently supports only mae/rmse metrics; "
            f"unsupported: {', '.join(unsupported)}"
        )

    n_windows = int(split.get("n_windows", 1000))
    test_window_hours = int(split.get("test_window_hours", 6))
    training_lookback_days = int(split.get("training_lookback_days", 100))
    model = JobRuntimeTfidfKnnModel(
        config=JobRuntimeTfidfKnnConfig(
            n_windows=n_windows,
            test_window_hours=test_window_hours,
            training_lookback_days=training_lookback_days,
        )
    )
    eval_payload = model.evaluate(rows, verbose=verbose)

    metrics = {
        "mae": float(eval_payload["mae"]),
        "rmse": float(eval_payload["rmse"]),
    }
    metrics_payload: dict[str, Any] = {**eval_payload, "definitions": metric_defs}
    return metrics, metrics_payload
