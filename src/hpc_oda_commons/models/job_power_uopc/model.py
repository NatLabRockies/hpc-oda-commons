"""User-based online power prediction (UoPC) with per-user kNN regression.

Adapted from https://github.com/francescoantici/UoPC:
- Per-user history ordered by end time
- Last ``theta`` jobs used as training context for each prediction
- Categorical job features label-encoded per fit
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
from sklearn.neighbors import KNeighborsRegressor
from sklearn.preprocessing import LabelEncoder
from tqdm import tqdm

from hpc_oda_commons.kernel.metrics import compute_regression_metrics_from_defs

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "maxpcon": ("maxpcon",),
    "user": ("user", "usr"),
    "name": ("name", "jnam"),
    "processors_requested": ("processors_requested", "cnumr"),
    "nodes_requested": ("nodes_requested", "nnumr"),
    "end_time": ("end_time", "edt"),
}


@dataclass(frozen=True)
class JobPowerUopcConfig:
    """Configuration for the UoPC user-based kNN power model."""

    target_field: str = "maxpcon"
    user_field: str = "user"
    order_by_field: str = "end_time"
    feature_fields: tuple[str, ...] = ("name", "processors_requested", "nodes_requested")
    categorical_fields: frozenset[str] = frozenset({"name"})
    theta: int = 50
    k: int = 5


def _first_present(row: dict[str, Any], field: str) -> Any:
    for key in _FIELD_ALIASES.get(field, (field,)):
        if key in row and row[key] is not None:
            return row[key]
    return None


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    for canonical in _FIELD_ALIASES:
        value = _first_present(row, canonical)
        if value is not None:
            normalized[canonical] = value
    return normalized


def _end_time_sort_key(row: dict[str, Any], *, field: str) -> float:
    raw = row.get(field)
    if raw is None:
        return float("-inf")
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    if not text:
        return float("-inf")
    normalized = text
    if len(normalized) > 5 and normalized[-3] in "+-" and normalized[-2:].isdigit():
        normalized = f"{normalized[:-3]}{normalized[-3]}{normalized[-2:]}:00"
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return float("-inf")


def _finite_target(row: dict[str, Any], target_field: str) -> float | None:
    raw = _first_present(row, target_field)
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def _feature_value(row: dict[str, Any], field: str) -> Any:
    return _first_present(row, field)


def _feature_float(raw: Any) -> float:
    """Coerce a numeric feature value to float, falling back to 0.0.

    SLURM-derived fields (e.g. processors/nodes requested) may arrive as
    non-numeric strings; mirror the XGBoost preprocessing convention of
    tolerating them rather than crashing the whole benchmark.
    """
    if raw is None:
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


class _LabelFeatureEncoder:
    """Per-column label encoders fit on the user's training history."""

    def __init__(self, categorical_fields: frozenset[str]) -> None:
        self.categorical_fields = categorical_fields
        self._encoders: dict[str, LabelEncoder] = {}

    def fit_transform_row_matrix(
        self,
        history: list[dict[str, Any]],
        query: dict[str, Any],
        feature_fields: tuple[str, ...],
    ) -> tuple[np.ndarray, np.ndarray]:
        x_train = np.zeros((len(history), len(feature_fields)), dtype=np.float64)
        x_query = np.zeros((1, len(feature_fields)), dtype=np.float64)

        for col_idx, field in enumerate(feature_fields):
            if field in self.categorical_fields:
                encoder = LabelEncoder()
                train_values = [str(_feature_value(row, field) or "") for row in history]
                encoder.fit(train_values)
                self._encoders[field] = encoder
                x_train[:, col_idx] = encoder.transform(train_values)
                query_value = str(_feature_value(query, field) or "")
                if query_value in encoder.classes_:
                    x_query[0, col_idx] = encoder.transform([query_value])[0]
                else:
                    x_query[0, col_idx] = -1.0
            else:
                train_numeric = [_feature_float(_feature_value(row, field)) for row in history]
                x_train[:, col_idx] = np.asarray(train_numeric, dtype=np.float64)
                x_query[0, col_idx] = _feature_float(_feature_value(query, field))

        return x_train, x_query


class JobPowerUopcModel:
    """UoPC-style per-user kNN model for fixed chronological evaluation."""

    def __init__(self, config: JobPowerUopcConfig | None = None) -> None:
        self.config = config or JobPowerUopcConfig()

    def evaluate_fixed(
        self,
        rows: list[dict[str, Any]],
        *,
        split: dict[str, Any],
        metric_defs: list[dict[str, Any]] | None = None,
        verbose: bool = False,
        capture_artifacts: bool = False,
    ) -> dict[str, Any]:
        cfg = self.config
        resolved_metric_defs = metric_defs or [
            {"name": "mae", "target": cfg.target_field},
            {"name": "rmse", "target": cfg.target_field},
        ]

        supervised = [
            _normalize_row(row) for row in rows if _finite_target(row, cfg.target_field) is not None
        ]
        if not supervised:
            raise ValueError("No rows with a finite target value.")

        supervised.sort(key=lambda row: _end_time_sort_key(row, field=cfg.order_by_field))

        train_fraction = float(split.get("train_fraction", 0.8))
        n_train = max(1, int(len(supervised) * train_fraction))
        train_rows = supervised[:n_train]
        test_rows = supervised[n_train:] if n_train < len(supervised) else []

        history_by_user: dict[str, list[dict[str, Any]]] = {}
        for row in train_rows:
            user = str(_feature_value(row, cfg.user_field) or "")
            history_by_user.setdefault(user, []).append(row)

        y_true: list[float] = []
        y_pred: list[float] = []
        rows_skipped = 0

        test_iter = tqdm(
            test_rows,
            desc="fixed/uopc",
            unit="job",
            disable=not verbose,
        )

        for test_row in test_iter:
            user = str(_feature_value(test_row, cfg.user_field) or "")
            history = list(history_by_user.get(user, []))
            history.sort(
                key=lambda row: _end_time_sort_key(row, field=cfg.order_by_field),
                reverse=True,
            )
            context = history[: cfg.theta]

            # Online evaluation: every test job is appended to its user's history
            # after being seen, so it becomes context for that user's later jobs --
            # whether or not it was scored. This mirrors the streaming UoPC design
            # and is intentional, not train/test leakage.
            if len(context) < cfg.k:
                rows_skipped += 1
                history_by_user.setdefault(user, []).append(test_row)
                continue

            pred = self._predict_one(context, test_row)
            y_true.append(float(_finite_target(test_row, cfg.target_field)))
            y_pred.append(pred)
            history_by_user.setdefault(user, []).append(test_row)

        if not y_true:
            raise ValueError("No test rows produced scored predictions.")

        metrics = compute_regression_metrics_from_defs(y_true, y_pred, resolved_metric_defs)
        summary = {
            "rows_total": len(supervised),
            "rows_train": len(train_rows),
            "rows_test": len(test_rows),
            "rows_scored": len(y_true),
            "rows_skipped": rows_skipped,
            "theta": cfg.theta,
            "k": cfg.k,
            "train_fraction": train_fraction,
        }

        result: dict[str, Any] = {
            **metrics,
            "definitions": resolved_metric_defs,
            "summary": summary,
        }
        if capture_artifacts:
            result["_y_true"] = y_true
            result["_y_pred"] = y_pred
            # UoPC has no single persistent estimator -- each prediction fits a
            # fresh per-user kNN on its own context window. The captured artifact
            # is therefore the configuration needed to reproduce the run, not a
            # fitted model (so save_model pickles this config rather than an estimator).
            result["_last_model"] = {"kind": "job_power_uopc", "config": cfg}
        return result

    def _predict_one(
        self,
        history: list[dict[str, Any]],
        query: dict[str, Any],
    ) -> float:
        """Fit a fresh per-user kNN on this query's context window and predict.

        Note: a LabelEncoder and KNeighborsRegressor are refit for every test
        row. This is inherent to the per-user sliding-context design (each query
        sees a different history window) and is acceptable for v0.1 power
        datasets; it is a known scaling limitation for very large test sets.
        """
        cfg = self.config
        encoder = _LabelFeatureEncoder(cfg.categorical_fields)
        x_train, x_query = encoder.fit_transform_row_matrix(history, query, cfg.feature_fields)
        y_train = np.asarray(
            [float(_finite_target(row, cfg.target_field)) for row in history],
            dtype=np.float64,
        )

        k_eff = min(cfg.k, len(history))
        model = KNeighborsRegressor(n_neighbors=k_eff)
        model.fit(x_train, y_train)
        return float(model.predict(x_query)[0])
