"""
Benchmark execution logic for HPC ODA Commons models.
"""

from __future__ import annotations

import math
from dataclasses import asdict, is_dataclass
from typing import Any

from tqdm import tqdm

from hpc_oda_commons.benchmark.run_extras import BenchmarkArtifacts, pop_eval_artifact_keys
from hpc_oda_commons.kernel.metrics import (
    SUPPORTED_ROLLING_METRIC_NAMES,
    compute_regression_metrics_from_defs,
)
from hpc_oda_commons.kernel.serialization import to_jsonable
from hpc_oda_commons.models.job_power_uopc.model import (
    PAPER_K,
    PAPER_K_VALUES,
    PAPER_TARGETS,
    PAPER_THETA,
    PAPER_THETA_VALUES,
    UOPC_DEFAULT_FEATURES,
    JobPowerUopcConfig,
    JobPowerUopcModel,
)
from hpc_oda_commons.models.job_power_uopc.rolling import (
    JobPowerUopcRollingConfig,
    JobPowerUopcRollingModel,
)
from hpc_oda_commons.models.job_runtime_baseline.model import JobRuntimeBaselineModel
from hpc_oda_commons.models.job_runtime_embedding_knn.backends import DEFAULT_SIMS_BLOCK_BYTES
from hpc_oda_commons.models.job_runtime_embedding_knn.model import (
    JobRuntimeEmbeddingKnnConfig,
    JobRuntimeEmbeddingKnnModel,
)
from hpc_oda_commons.models.job_runtime_mlp.model import (
    JobRuntimeMlpConfig,
    JobRuntimeMlpModel,
)
from hpc_oda_commons.models.job_runtime_moe_xgboost.model import (
    MoEXGBoostConfig,
    MoEXGBoostModel,
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
from hpc_oda_commons.models.rolling_tabular.artifact_store import default_artifact_store
from hpc_oda_commons.models.rolling_tabular.base import RollingTabularModel
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


def recipe_target(metric_defs: list[dict[str, Any]]) -> str | None:
    """The one column a recipe's metrics score, or None when they name none.

    A metric's ``target`` is not a label. Metrics are computed from whatever the model
    predicted, so a recipe whose metrics say ``avgpcon_per_node`` over a model that predicts
    ``runtime_seconds`` would report runtime errors under a power name (#204). The runner
    therefore holds the model to this column.
    """
    targets = {str(m.get("target", "")).strip() for m in metric_defs if m.get("target")}
    if not targets:
        return None
    if len(targets) > 1:
        raise ValueError(f"All metrics must share one target; got {sorted(targets)}.")
    return targets.pop()


def _target_for(metric_defs: list[dict[str, Any]]) -> str:
    """The column a target-configurable model should predict: the recipe's, else runtime."""
    return recipe_target(metric_defs) or "runtime_seconds"


def _require_target(
    predicts: str | set[str], metric_defs: list[dict[str, Any]], *, model: str
) -> str:
    """Fail unless the recipe's metric target is a column this model predicts.

    ``predicts`` is the model's target, or the set it can be pointed at. Returns the target
    in force: the recipe's when it names one, else the model's own.
    """
    allowed = {predicts} if isinstance(predicts, str) else set(predicts)
    target = recipe_target(metric_defs)
    if target is None:
        if len(allowed) != 1:
            raise ValueError(f"{model} needs a metric target, one of {sorted(allowed)}.")
        return next(iter(allowed))
    if target not in allowed:
        raise ValueError(
            f"{model} predicts {' or '.join(repr(t) for t in sorted(allowed))}, but the "
            f"recipe's metrics score {target!r}. Metric targets are what gets scored, not "
            "labels, so this would report one column's errors under another's name."
        )
    return target


def run_fixed_baseline(
    rows: list[dict[str, Any]],
    *,
    split: dict[str, Any],
    metric_defs: list[dict[str, Any]],
    capture_artifacts: bool = False,
) -> tuple[dict[str, float], dict[str, Any], BenchmarkArtifacts]:
    """Run a fixed train/test split benchmark with the baseline model."""
    target = _target_for(metric_defs)
    train_fraction = float(split.get("train_fraction", 0.8))
    n_train = max(1, int(len(rows) * train_fraction))
    train_rows = rows[:n_train]
    test_rows = rows[n_train:] if n_train < len(rows) else rows[:]
    y_true = [float(r[target]) for r in test_rows]

    model = JobRuntimeBaselineModel(target_field=target)
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
    # The runner always builds the default config, so its target is the class default.
    _require_target(
        JobPowerUopcConfig.target_field, metric_defs, model="model.job_power_uopc (fixed)"
    )
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
    metrics_payload: dict[str, Any] = {
        **eval_payload,
        "definitions": metric_defs,
        "run_config": resolved_run_config(model),
    }
    return metrics, metrics_payload, artifacts


def run_cutoff_uopc(
    rows: list[dict[str, Any]],
    *,
    split: dict[str, Any],
    metric_defs: list[dict[str, Any]],
    verbose: bool = False,
    capture_artifacts: bool = False,
) -> tuple[dict[str, float], dict[str, Any], BenchmarkArtifacts]:
    """Run the UoPC paper protocol: score every job submitted on/after ``split.test_start``.

    With ``theta_values``/``k_values`` this is the sensitivity sweep, otherwise one
    reproduction at ``theta``/``k``. The result schema takes one metric set, so the sweep
    reports the classifier's avgpcon-per-node metrics at the ``theta``/``k`` the recipe
    names (the reproduction's configuration by default) as its headline, and keeps the
    whole grid in metrics.json. A headline outside the grid is an error rather than a
    silent pick, since it is what the leaderboard shows.
    """
    model = JobPowerUopcModel()
    # The paper protocol predicts both per-node targets; the recipe's metric target picks
    # which one is the headline (average by default in the bundled recipes).
    target = _require_target(set(PAPER_TARGETS), metric_defs, model="model.job_power_uopc (cutoff)")
    test_start = str(split["test_start"])
    theta = int(split.get("theta", PAPER_THETA))
    k = int(split.get("k", PAPER_K))
    sweep = "theta_values" in split or "k_values" in split
    # Variants that separate the paper's data and target from ours (#222).
    node_count = str(split.get("node_count", "allocated"))
    max_alloc_ratio = (
        float(split["max_alloc_ratio"]) if split.get("max_alloc_ratio") is not None else None
    )
    variant = {
        "node_count": node_count,
        "max_alloc_ratio": max_alloc_ratio,
        "features": str(split.get("uopc_features", UOPC_DEFAULT_FEATURES)),
    }

    if sweep:
        theta_values = tuple(
            sorted({int(v) for v in split.get("theta_values", PAPER_THETA_VALUES)})
        )
        k_values = tuple(sorted({int(v) for v in split.get("k_values", PAPER_K_VALUES)}))
        if theta not in theta_values or k not in k_values:
            raise ValueError(
                f"split.theta={theta} / split.k={k} name the sweep's headline result, so they "
                f"must be in the grid (theta_values={list(theta_values)}, "
                f"k_values={list(k_values)})."
            )
        eval_payload = model.evaluate_paper_sensitivity(
            rows,
            test_start=test_start,
            theta_values=theta_values,
            k_values=k_values,
            **variant,
            metric_defs=metric_defs,
            verbose=verbose,
            capture_artifacts=capture_artifacts,
        )
        headline = eval_payload["results"][str(theta)][str(k)]["classifier"][target]
        if not headline:
            raise ValueError(
                f"No test job had {k} prior jobs at theta={theta}, so the headline is empty."
            )
        run_config: dict[str, Any] = {
            "protocol": "paper_sensitivity",
            "test_start": test_start,
            **variant,
            "theta_values": list(theta_values),
            "k_values": list(k_values),
            "headline": {
                "theta": theta,
                "k": k,
                "predictor": "KNeighborsClassifier",
                "target": target,
            },
        }
    else:
        eval_payload = model.evaluate_paper_reproduction(
            rows,
            test_start=test_start,
            theta=theta,
            k=k,
            **variant,
            metric_defs=metric_defs,
            verbose=verbose,
            capture_artifacts=capture_artifacts,
        )
        headline = eval_payload[target]
        run_config = {
            "protocol": "paper_reproduction",
            "test_start": test_start,
            **variant,
            "theta": theta,
            "k": k,
            "predictor": "KNeighborsClassifier",
            "headline_target": target,
        }

    requested = {str(m.get("name", "")) for m in metric_defs}
    artifacts = pop_eval_artifact_keys(eval_payload) if capture_artifacts else BenchmarkArtifacts()
    metrics = _metrics_from_eval_payload(headline, requested)
    # Never write a stray "_" artifact key into metrics.json: those are per-job arrays (#168).
    metrics_payload: dict[str, Any] = {
        **{key: value for key, value in eval_payload.items() if not key.startswith("_")},
        "definitions": metric_defs,
        "run_config": run_config,
    }
    return metrics, metrics_payload, artifacts


def resolved_run_config(model: Any) -> dict[str, Any]:
    """The configuration the model actually resolved, for the bundle to record (#197).

    Taken from the model rather than from the recipe, deliberately. The recipe states what was
    *asked for*, and a knob the runner failed to pass would still appear there looking
    honoured -- which is precisely how the target encoding in #172 shipped unreachable and an
    A/B measured exactly zero difference, to the decimal. This states what ran.

    Without it a bundle's configuration is only recoverable from its recipe id, so any knob
    not spelled into that string leaves no trace at all, and ``bench-matrix rank`` can only
    tell arms apart along the one axis that happens to be named there.
    """
    config = getattr(model, "config", None)
    if config is None:
        return {}
    if is_dataclass(config) and not isinstance(config, type):
        return to_jsonable(asdict(config))
    return to_jsonable(dict(vars(config)))


def _filter_target_rows(rows: list[dict[str, Any]], target: str) -> list[dict[str, Any]]:
    """Keep only rows with a finite ``target`` value."""
    result: list[dict[str, Any]] = []
    for row in rows:
        raw = row.get(target)
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
    target = _target_for(metric_defs)
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
        train_supervised = _filter_target_rows(train_rows, target)
        test_supervised = _filter_target_rows(test_rows, target)

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

        model = JobRuntimeBaselineModel(target_field=target)
        model.fit(train_supervised)
        y_pred = model.predict(test_supervised)
        y_true = [float(r[target]) for r in test_supervised]

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
        "target_field": target,
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
    # A model that declares no target predicts runtime, as every rolling model did before #204.
    predicts = str(getattr(model, "target_field", "runtime_seconds"))
    _require_target(predicts, metric_defs, model=type(model).__name__)
    requested = _validate_rolling_metric_defs(metric_defs)
    if isinstance(model, RollingTabularModel) and model.artifact_store is None:
        # Every rolling-tabular model on the same rows builds the same daily OHE + SVD, so
        # keep it between runs (#213). HPC_ODA_PREPROCESSING_CACHE moves or disables it.
        model.artifact_store = default_artifact_store()
    eval_payload = model.evaluate(
        rows,
        verbose=verbose,
        metric_defs=metric_defs,
        capture_artifacts=capture_artifacts,
    )
    artifacts = pop_eval_artifact_keys(eval_payload) if capture_artifacts else BenchmarkArtifacts()
    metrics = _metrics_from_eval_payload(eval_payload, requested)
    metrics_payload: dict[str, Any] = {
        **eval_payload,
        "definitions": metric_defs,
        "run_config": resolved_run_config(model),
    }
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
    model = JobRuntimeXGBoostModel(
        config=JobRuntimeXGBoostConfig(
            target_field=_target_for(metric_defs),
            **_rolling_tabular_split_kwargs(split, JobRuntimeXGBoostConfig()),
            objective=str(split.get("objective", JobRuntimeXGBoostConfig.objective)),
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


def _rolling_tabular_split_kwargs(split: dict[str, Any], defaults: Any) -> dict[str, Any]:
    """Config keyword arguments a recipe's ``split`` may set on a rolling-tabular model.

    Centralised because forgetting one is silent and has bitten this project twice: the MoE
    knobs in #134 were rejected at recipe load until the schema named them, and the target
    encoding in #172 shipped unreachable because the runner did not pass it -- an A/B measured
    exactly zero difference, to the decimal, before anyone noticed.

    Anything added here must also be declared in the recipe schema's ``split``, which is
    ``additionalProperties: false``. A test asserts the two stay in step.
    """
    return {
        "n_windows": int(split.get("n_windows", 1000)),
        "test_window_hours": int(split.get("test_window_hours", 6)),
        "training_lookback_days": int(split.get("training_lookback_days", 100)),
        "window_n_jobs": int(split.get("window_n_jobs", 1)),
        "log_target": bool(split.get("log_target", False)),
        "target_encode_min_cardinality": int(
            split.get("target_encode_min_cardinality", defaults.target_encode_min_cardinality)
        ),
        "target_encode_smoothing": float(
            split.get("target_encode_smoothing", defaults.target_encode_smoothing)
        ),
    }


def run_rolling_random_forest(
    rows: list[dict[str, Any]],
    *,
    split: dict[str, Any],
    metric_defs: list[dict[str, Any]],
    verbose: bool = False,
    capture_artifacts: bool = False,
) -> tuple[dict[str, float], dict[str, Any], BenchmarkArtifacts]:
    """Run a rolling benchmark with the Random Forest model."""
    model = JobRuntimeRandomForestModel(
        config=JobRuntimeRandomForestConfig(
            target_field=_target_for(metric_defs),
            **_rolling_tabular_split_kwargs(split, JobRuntimeRandomForestConfig()),
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


def run_rolling_signature_memorizer(
    rows: list[dict[str, Any]],
    *,
    split: dict[str, Any],
    metric_defs: list[dict[str, Any]],
    verbose: bool = False,
    capture_artifacts: bool = False,
) -> tuple[dict[str, float], dict[str, Any], BenchmarkArtifacts]:
    """Run a rolling benchmark with the signature-memorization baseline."""
    from hpc_oda_commons.models.job_runtime_signature_memorizer import (
        JobRuntimeSignatureMemorizerModel,
        SignatureMemorizerConfig,
    )

    defaults = SignatureMemorizerConfig()
    model = JobRuntimeSignatureMemorizerModel(
        config=SignatureMemorizerConfig(
            target_field=_target_for(metric_defs),
            n_windows=int(split.get("n_windows", 1000)),
            test_window_hours=int(split.get("test_window_hours", 6)),
            training_lookback_days=int(split.get("training_lookback_days", 100)),
            window_n_jobs=int(split.get("window_n_jobs", 1)),
            log_target=bool(split.get("log_target", False)),
            backoff_levels=int(split.get("backoff_levels", defaults.backoff_levels)),
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
            target_field=_target_for(metric_defs),
            n_windows=n_windows,
            test_window_hours=test_window_hours,
            training_lookback_days=training_lookback_days,
            window_n_jobs=int(split.get("window_n_jobs", 1)),
            log_target=bool(split.get("log_target", False)),
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
            target_field=_target_for(metric_defs),
            n_windows=int(split.get("n_windows", 1000)),
            test_window_hours=int(split.get("test_window_hours", 6)),
            training_lookback_days=int(split.get("training_lookback_days", 100)),
            k=int(split.get("k", 5)),
            embedding_field=str(split.get("embedding_field", "embedding")),
            backend=str(split.get("backend", "auto")),
            device=str(split.get("device", "auto")),
            weighting=str(split.get("weighting", "similarity")),
            sims_block_bytes=int(split.get("sims_block_bytes", DEFAULT_SIMS_BLOCK_BYTES)),
            log_target=bool(split.get("log_target", False)),
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
            target_field=_target_for(metric_defs),
            n_windows=n_windows,
            test_window_hours=test_window_hours,
            training_lookback_days=training_lookback_days,
            window_n_jobs=int(split.get("window_n_jobs", 1)),
            log_target=bool(split.get("log_target", False)),
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


def run_rolling_uopc(
    rows: list[dict[str, Any]],
    *,
    split: dict[str, Any],
    metric_defs: list[dict[str, Any]],
    verbose: bool = False,
    capture_artifacts: bool = False,
) -> tuple[dict[str, float], dict[str, Any], BenchmarkArtifacts]:
    """Run UoPC on the shared rolling windows, scored like every other model (#204)."""
    defaults = JobPowerUopcRollingConfig()
    model = JobPowerUopcRollingModel(
        config=JobPowerUopcRollingConfig(
            target_field=recipe_target(metric_defs) or defaults.target_field,
            n_windows=int(split.get("n_windows", 1000)),
            test_window_hours=int(split.get("test_window_hours", 6)),
            training_lookback_days=int(split.get("training_lookback_days", 100)),
            theta=int(split.get("theta", defaults.theta)),
            k=int(split.get("k", defaults.k)),
            embedding_field=str(split.get("embedding_field", defaults.embedding_field)),
            features=str(split.get("uopc_features", defaults.features)),
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


def run_rolling_moe_xgboost(
    rows: list[dict[str, Any]],
    *,
    split: dict[str, Any],
    metric_defs: list[dict[str, Any]],
    verbose: bool = False,
    capture_artifacts: bool = False,
) -> tuple[dict[str, float], dict[str, Any], BenchmarkArtifacts]:
    """Run a rolling benchmark with the User+Wallclock MoE XGBoost model."""
    n_windows = int(split.get("n_windows", 1000))
    test_window_hours = int(split.get("test_window_hours", 6))
    training_lookback_days = int(split.get("training_lookback_days", 100))
    defaults = MoEXGBoostConfig()
    edges = split.get("wallclock_bin_edges_hours")
    model = MoEXGBoostModel(
        config=MoEXGBoostConfig(
            target_field=_target_for(metric_defs),
            n_windows=n_windows,
            test_window_hours=test_window_hours,
            training_lookback_days=training_lookback_days,
            window_n_jobs=int(split.get("window_n_jobs", 1)),
            log_target=bool(split.get("log_target", False)),
            time_decay_rate=float(split.get("time_decay_rate", defaults.time_decay_rate)),
            enable_power_users=bool(split.get("enable_power_users", defaults.enable_power_users)),
            power_user_percentile=float(
                split.get("power_user_percentile", defaults.power_user_percentile)
            ),
            min_expert_rows=int(split.get("min_expert_rows", defaults.min_expert_rows)),
            n_wallclock_bins=int(split.get("n_wallclock_bins", defaults.n_wallclock_bins)),
            wallclock_bin_edges_hours=tuple(float(h) for h in edges) if edges else None,
            estimator_n_jobs=int(split.get("estimator_n_jobs", defaults.estimator_n_jobs)),
            objective=str(split.get("objective", defaults.objective)),
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
