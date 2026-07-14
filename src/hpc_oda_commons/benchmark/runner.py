"""
Benchmark execution logic for HPC ODA Commons models.
"""

from __future__ import annotations

import math
from typing import Any

from tqdm import tqdm

from hpc_oda_commons.benchmark.run_extras import BenchmarkArtifacts, pop_eval_artifact_keys
from hpc_oda_commons.kernel.metrics import (
    SUPPORTED_ROLLING_METRIC_NAMES,
    compute_regression_metrics_from_defs,
)
from hpc_oda_commons.models.job_power_uopc.model import JobPowerUopcModel
from hpc_oda_commons.models.job_runtime_baseline.model import JobRuntimeBaselineModel
from hpc_oda_commons.models.job_runtime_embedding_knn.model import (
    JobRuntimeEmbeddingKnnConfig,
    JobRuntimeEmbeddingKnnModel,
)
from hpc_oda_commons.models.job_runtime_mlp.model import (
    JobRuntimeMlpConfig,
    JobRuntimeMlpModel,
)
from hpc_oda_commons.models.job_runtime_random_forest.model import (
    JobRuntimeRandomForestConfig,
    JobRuntimeRandomForestModel,
)
from hpc_oda_commons.models.job_runtime_tfidf_knn.model import (
    JobRuntimeTfidfKnnConfig,
    JobRuntimeTfidfKnnModel,
)
from hpc_oda_commons.models.job_runtime_xgboost.model import (
    JobRuntimeXGBoostConfig,
    JobRuntimeXGBoostModel,
)
from hpc_oda_commons.models.rolling_tabular.split import (
    build_rolling_splits,
    materialize_split_rows,
)


def _validate_rolling_metric_defs(metric_defs: list[dict[str, Any]]) -> set[str]:
    requested = {str(m.get("name", "")) for m in metric_defs}
    unsupported = sorted(requested - SUPPORTED_ROLLING_METRIC_NAMES)
    if unsupported:
        raise ValueError(
            "rolling benchmark currently supports only "
            f"{', '.join(sorted(SUPPORTED_ROLLING_METRIC_NAMES))} metrics; "
            f"unsupported: {', '.join(unsupported)}"
        )
    return requested


def _metrics_from_eval_payload(
    eval_payload: dict[str, Any], requested: set[str]
) -> dict[str, float]:
    return {name: float(eval_payload[name]) for name in requested if name in eval_payload}


def run_fixed_baseline(
    rows: list[dict[str, Any]],
    *,
    split: dict[str, Any],
    metric_defs: list[dict[str, Any]],
    capture_artifacts: bool = False,
) -> tuple[dict[str, float], dict[str, Any], BenchmarkArtifacts]:
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
    artifacts = BenchmarkArtifacts()
    if capture_artifacts:
        artifacts = BenchmarkArtifacts(
            y_true=y_true,
            y_pred=y_pred,
            last_model={"kind": "job_runtime_baseline", "model": model},
        )
    return metrics, metrics_payload, artifacts


def run_fixed_uopc(
    rows: list[dict[str, Any]],
    *,
    split: dict[str, Any],
    metric_defs: list[dict[str, Any]],
    verbose: bool = False,
    capture_artifacts: bool = False,
) -> tuple[dict[str, float], dict[str, Any], BenchmarkArtifacts]:
    """Run a fixed chronological split benchmark with the UoPC kNN model."""
    model = JobPowerUopcModel()
    eval_payload = model.evaluate_fixed(
        rows,
        split=split,
        metric_defs=metric_defs,
        verbose=verbose,
        capture_artifacts=capture_artifacts,
    )
    requested = {str(m.get("name", "")) for m in metric_defs}
    artifacts = pop_eval_artifact_keys(eval_payload) if capture_artifacts else BenchmarkArtifacts()
    metrics = _metrics_from_eval_payload(eval_payload, requested)
    metrics_payload: dict[str, Any] = {**eval_payload, "definitions": metric_defs}
    return metrics, metrics_payload, artifacts


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
    capture_artifacts: bool = False,
) -> tuple[dict[str, float], dict[str, Any], BenchmarkArtifacts]:
    """Run a rolling benchmark with the baseline model."""
    requested = _validate_rolling_metric_defs(metric_defs)

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
    last_model: JobRuntimeBaselineModel | None = None

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

        window_metrics = compute_regression_metrics_from_defs(y_true, y_pred, metric_defs)
        all_y_true.extend(y_true)
        all_y_pred.extend(y_pred)
        if capture_artifacts:
            last_model = model

        if verbose:
            metric_bits = " ".join(f"{k}={window_metrics[k]:.6f}" for k in sorted(window_metrics))
            print(
                f"[baseline][verbose] split={s.split_time_iso} status=ok "
                f"train={len(train_supervised)} test={len(test_supervised)} "
                f"{metric_bits}"
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

    global_metrics = compute_regression_metrics_from_defs(all_y_true, all_y_pred, metric_defs)
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
        metric_bits = " ".join(f"{k}={global_metrics[k]:.6f}" for k in sorted(global_metrics))
        print(
            "[baseline][verbose] summary "
            f"windows_total={summary['windows_total']} "
            f"windows_scored={summary['windows_scored']} "
            f"windows_skipped={summary['windows_skipped']} "
            f"rows_scored={summary['rows_scored']} "
            f"{metric_bits}"
        )

    metrics = _metrics_from_eval_payload(global_metrics, requested)
    eval_payload: dict[str, Any] = {
        **global_metrics,
        "definitions": metric_defs,
        "windows": window_entries,
        "summary": summary,
    }
    artifacts = BenchmarkArtifacts()
    if capture_artifacts:
        artifacts = BenchmarkArtifacts(
            y_true=all_y_true,
            y_pred=all_y_pred,
            last_model=(
                {"kind": "job_runtime_baseline", "model": last_model}
                if last_model is not None
                else None
            ),
        )
    return metrics, eval_payload, artifacts


def _run_rolling_model_evaluate(
    model: Any,
    rows: list[dict[str, Any]],
    *,
    split: dict[str, Any],
    metric_defs: list[dict[str, Any]],
    verbose: bool,
    capture_artifacts: bool,
) -> tuple[dict[str, float], dict[str, Any], BenchmarkArtifacts]:
    requested = _validate_rolling_metric_defs(metric_defs)
    eval_payload = model.evaluate(
        rows,
        verbose=verbose,
        metric_defs=metric_defs,
        capture_artifacts=capture_artifacts,
    )
    artifacts = pop_eval_artifact_keys(eval_payload) if capture_artifacts else BenchmarkArtifacts()
    metrics = _metrics_from_eval_payload(eval_payload, requested)
    metrics_payload: dict[str, Any] = {**eval_payload, "definitions": metric_defs}
    return metrics, metrics_payload, artifacts


def run_rolling_xgboost(
    rows: list[dict[str, Any]],
    *,
    split: dict[str, Any],
    metric_defs: list[dict[str, Any]],
    verbose: bool = False,
    capture_artifacts: bool = False,
) -> tuple[dict[str, float], dict[str, Any], BenchmarkArtifacts]:
    """Run a rolling benchmark with the XGBoost model."""
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
    return _run_rolling_model_evaluate(
        model,
        rows,
        split=split,
        metric_defs=metric_defs,
        verbose=verbose,
        capture_artifacts=capture_artifacts,
    )


def run_rolling_random_forest(
    rows: list[dict[str, Any]],
    *,
    split: dict[str, Any],
    metric_defs: list[dict[str, Any]],
    verbose: bool = False,
    capture_artifacts: bool = False,
) -> tuple[dict[str, float], dict[str, Any], BenchmarkArtifacts]:
    """Run a rolling benchmark with the Random Forest model."""
    n_windows = int(split.get("n_windows", 1000))
    test_window_hours = int(split.get("test_window_hours", 6))
    training_lookback_days = int(split.get("training_lookback_days", 100))
    model = JobRuntimeRandomForestModel(
        config=JobRuntimeRandomForestConfig(
            n_windows=n_windows,
            test_window_hours=test_window_hours,
            training_lookback_days=training_lookback_days,
        )
    )
    return _run_rolling_model_evaluate(
        model,
        rows,
        split=split,
        metric_defs=metric_defs,
        verbose=verbose,
        capture_artifacts=capture_artifacts,
    )


def run_rolling_mlp(
    rows: list[dict[str, Any]],
    *,
    split: dict[str, Any],
    metric_defs: list[dict[str, Any]],
    verbose: bool = False,
    capture_artifacts: bool = False,
) -> tuple[dict[str, float], dict[str, Any], BenchmarkArtifacts]:
    """Run a rolling benchmark with the feed-forward MLP model."""
    n_windows = int(split.get("n_windows", 1000))
    test_window_hours = int(split.get("test_window_hours", 6))
    training_lookback_days = int(split.get("training_lookback_days", 100))
    model = JobRuntimeMlpModel(
        config=JobRuntimeMlpConfig(
            n_windows=n_windows,
            test_window_hours=test_window_hours,
            training_lookback_days=training_lookback_days,
        )
    )
    return _run_rolling_model_evaluate(
        model,
        rows,
        split=split,
        metric_defs=metric_defs,
        verbose=verbose,
        capture_artifacts=capture_artifacts,
    )


def run_rolling_embedding_knn(
    rows: list[dict[str, Any]],
    *,
    split: dict[str, Any],
    metric_defs: list[dict[str, Any]],
    verbose: bool = False,
    capture_artifacts: bool = False,
) -> tuple[dict[str, float], dict[str, Any], BenchmarkArtifacts]:
    """Run a rolling benchmark with the embedding-based kNN model."""
    model = JobRuntimeEmbeddingKnnModel(
        config=JobRuntimeEmbeddingKnnConfig(
            n_windows=int(split.get("n_windows", 1000)),
            test_window_hours=int(split.get("test_window_hours", 6)),
            training_lookback_days=int(split.get("training_lookback_days", 100)),
            k=int(split.get("k", 5)),
            embedding_field=str(split.get("embedding_field", "embedding")),
            backend=str(split.get("backend", "auto")),
            device=str(split.get("device", "auto")),
            weighting=str(split.get("weighting", "similarity")),
        )
    )
    return _run_rolling_model_evaluate(
        model,
        rows,
        split=split,
        metric_defs=metric_defs,
        verbose=verbose,
        capture_artifacts=capture_artifacts,
    )


def run_rolling_tfidf_knn(
    rows: list[dict[str, Any]],
    *,
    split: dict[str, Any],
    metric_defs: list[dict[str, Any]],
    verbose: bool = False,
    capture_artifacts: bool = False,
) -> tuple[dict[str, float], dict[str, Any], BenchmarkArtifacts]:
    """Run a rolling benchmark with the TF-IDF + kNN model."""
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
    return _run_rolling_model_evaluate(
        model,
        rows,
        split=split,
        metric_defs=metric_defs,
        verbose=verbose,
        capture_artifacts=capture_artifacts,
    )
