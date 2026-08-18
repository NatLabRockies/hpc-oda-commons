"""User-based online power prediction (UoPC) with per-user kNN regression.

Adapted from https://github.com/francescoantici/UoPC:
- Per-user history ordered by end time
- Last ``theta`` jobs used as training context for each prediction
- Categorical job features label-encoded per fit
"""

from __future__ import annotations

import time
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
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

@dataclass
class _PaperPreparedData:
    user_arr: np.ndarray
    submit_arr: np.ndarray
    end_arr: np.ndarray
    features: np.ndarray
    avg_target_arr: np.ndarray
    max_target_arr: np.ndarray
    order: np.ndarray
    user_rows: dict[str, np.ndarray]
    user_ends: dict[str, np.ndarray]
    test_idx: np.ndarray


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
    if isinstance(raw, datetime):
        return raw.timestamp()
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

def _classifier_prediction_from_neighbor_targets(
    neighbor_targets: np.ndarray,
    k: int,
) -> float:
    """Reproduce uniform-weight KNeighborsClassifier voting from ordered neighbors."""
    labels = np.rint(np.asarray(neighbor_targets[:k], dtype=np.float64)).astype(np.int64)
    if labels.size < k:
        raise ValueError(f"Need at least {k} neighbors, got {labels.size}.")
    values, counts = np.unique(labels, return_counts=True)
    return float(values[np.argmax(counts)])


def _regressor_prediction_from_neighbor_targets(
    neighbor_targets: np.ndarray,
    k: int,
) -> float:
    """Reproduce uniform-weight KNeighborsRegressor prediction from ordered neighbors."""
    values = np.asarray(neighbor_targets[:k], dtype=np.float64)
    if values.size < k:
        raise ValueError(f"Need at least {k} neighbors, got {values.size}.")
    return float(np.mean(values))

def _nearest_neighbor_indices_and_distances(
    context_features: np.ndarray,
    query_features: np.ndarray,
    max_neighbors: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return nearest context-row indices and distances, ordered nearest first."""
    if max_neighbors <= 0:
        raise ValueError("max_neighbors must be positive.")

    n_neighbors = min(max_neighbors, len(context_features))
    if n_neighbors == 0:
        return (
            np.asarray([], dtype=np.int64),
            np.asarray([], dtype=np.float64),
        )

    # Neighbor locations depend only on features, not on the prediction target.
    # Fit once so avg/max power and multiple k values can reuse the same search.
    model = KNeighborsRegressor(n_neighbors=n_neighbors)
    model.fit(
        context_features,
        np.zeros(len(context_features), dtype=np.float64),
    )

    distances, indices = model.kneighbors(
        query_features,
        n_neighbors=n_neighbors,
        return_distance=True,
    )

    return (
        np.asarray(indices[0], dtype=np.int64),
        np.asarray(distances[0], dtype=np.float64),
    )


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



    def _prepare_paper_data(
        self,
        rows: list[dict[str, Any]],
        *,
        test_start: str,
    ) -> _PaperPreparedData:
        cutoff = (
            datetime.fromisoformat(test_start)
            .replace(tzinfo=timezone.utc)
            .timestamp()
        )

        users: list[str] = []
        submits: list[float] = []
        ends: list[float] = []
        embeddings: list[np.ndarray] = []
        numeric: list[list[float]] = []
        avg_targets: list[float] = []
        max_targets: list[float] = []

        for row in rows:
            nnuma_raw = row.get("nnuma")
            avgpcon_raw = row.get("avgpcon")
            maxpcon_raw = row.get("maxpcon")
            emb_raw = row.get("embedding")
            adt_raw = row.get("submit_time")
            edt_raw = row.get("end_time")

            if (
                nnuma_raw in (None, 0)
                or avgpcon_raw is None
                or maxpcon_raw is None
                or emb_raw is None
                or adt_raw is None
                or edt_raw is None
            ):
                continue

            submit = _end_time_sort_key({"ts": adt_raw}, field="ts")
            end = _end_time_sort_key({"ts": edt_raw}, field="ts")

            try:
                nnuma = float(nnuma_raw)
                avgpcon = float(avgpcon_raw)
                maxpcon = float(maxpcon_raw)
                emb = np.asarray(emb_raw, dtype=np.float32)
            except (TypeError, ValueError):
                continue

            avg_target = avgpcon / nnuma
            max_target = maxpcon / nnuma

            if (
                not math.isfinite(submit)
                or not math.isfinite(end)
                or not math.isfinite(avg_target)
                or not math.isfinite(max_target)
                or nnuma <= 0
                or emb.ndim != 1
                or emb.size == 0
            ):
                continue

            users.append(str(row.get("user") or ""))
            submits.append(submit)
            ends.append(end)
            embeddings.append(emb)
            numeric.append(
                [
                    _feature_float(row.get("num_cores_req")),
                    _feature_float(row.get("num_nodes_req")),
                    _feature_float(row.get("freq_req")),
                ]
            )
            avg_targets.append(avg_target)
            max_targets.append(max_target)

        if not avg_targets:
            raise ValueError("No usable rows for UoPC paper reproduction.")

        user_arr = np.asarray(users)
        submit_arr = np.asarray(submits, dtype=np.float64)
        end_arr = np.asarray(ends, dtype=np.float64)
        emb_arr = np.ascontiguousarray(
            np.vstack(embeddings),
            dtype=np.float32,
        )
        num_arr = np.asarray(numeric, dtype=np.float32)
        avg_target_arr = np.asarray(avg_targets, dtype=np.float64)
        max_target_arr = np.asarray(max_targets, dtype=np.float64)

        # Match Phase 1 exactly: standardize over the complete usable dataset.
        mu = num_arr.mean(axis=0)
        sd = num_arr.std(axis=0)
        sd[sd == 0] = 1.0

        features = np.hstack(
            [emb_arr, (num_arr - mu) / sd]
        ).astype(np.float32)

        # Pre-sort each user's rows by completion time.
        order = np.argsort(end_arr, kind="stable")

        by_user: dict[str, list[int]] = {}
        for idx in order:
            by_user.setdefault(user_arr[idx], []).append(int(idx))

        user_rows = {
            user: np.asarray(indices, dtype=np.int64)
            for user, indices in by_user.items()
        }
        user_ends = {
            user: end_arr[indices]
            for user, indices in user_rows.items()
        }

        test_idx = np.where(submit_arr >= cutoff)[0]
        test_idx = test_idx[
            np.argsort(submit_arr[test_idx], kind="stable")
        ]

        return _PaperPreparedData(
            user_arr=user_arr,
            submit_arr=submit_arr,
            end_arr=end_arr,
            features=features,
            avg_target_arr=avg_target_arr,
            max_target_arr=max_target_arr,
            order=order,
            user_rows=user_rows,
            user_ends=user_ends,
            test_idx=test_idx,
        )


    def evaluate_paper_reproduction(
        self,
        rows: list[dict[str, Any]],
        *,
        test_start: str = "2024-02-01",
        theta: int = 500,
        k: int = 5,
        metric_defs: list[dict[str, Any]] | None = None,
        verbose: bool = False,
        capture_artifacts: bool = False,
    ) -> dict[str, Any]:
        """Evaluate the verified Phase-1 reproduction of Antici et al. UoPC.

        This path intentionally remains separate from ``evaluate_fixed`` so the
        existing HPC ODA UoPC adaptation and its defaults are unchanged.

        Reproduction protocol:
        - targets: avgpcon / nnuma and maxpcon / nnuma
        - features: embedding + globally z-scored (cnumr, nnumr, freq_req)
        - test jobs: adt >= test_start
        - history: same-user jobs with edt < query adt
        - context: newest ``theta`` eligible jobs by completion time
        - predictor: KNeighborsClassifier with rounded integer targets
        """
        resolved_metric_defs = metric_defs or [
            {"name": "mape", "target": "avgpcon_per_node"},
            {"name": "r2", "target": "avgpcon_per_node"},
        ]

        avg_metric_defs = [
            {**metric_def, "target": "avgpcon_per_node"}
            for metric_def in resolved_metric_defs
        ]

        max_metric_defs = [
            {**metric_def, "target": "maxpcon_per_node"}
            for metric_def in resolved_metric_defs
        ]

        prepared = self._prepare_paper_data(
            rows,
            test_start=test_start,
        )

        user_arr = prepared.user_arr
        submit_arr = prepared.submit_arr
        end_arr = prepared.end_arr
        features = prepared.features
        avg_target_arr = prepared.avg_target_arr
        max_target_arr = prepared.max_target_arr
        order = prepared.order
        user_rows = prepared.user_rows
        user_ends = prepared.user_ends
        test_idx = prepared.test_idx

        
        avg_y_true: list[float] = []
        avg_y_pred: list[float] = []
        max_y_true: list[float] = []
        max_y_pred: list[float] = []
        user_mean_avg_y_pred: list[float] = []
        user_mean_max_y_pred: list[float] = []
        global_mean_avg_y_pred: list[float] = []
        global_mean_max_y_pred: list[float] = []
        rows_skipped = 0

        iterator = tqdm(
            test_idx,
            desc="fixed/uopc-paper-repro",
            unit="job",
            disable=not verbose,
        )

        for j in iterator:
            user = user_arr[j]
            ends_for_user = user_ends.get(user)

            if ends_for_user is None:
                rows_skipped += 1
                continue

            # Strict paper history rule: completed BEFORE submission.
            pos = int(
                np.searchsorted(
                    ends_for_user,
                    submit_arr[j],
                    side="left",
                )
            )

            if pos < k:
                rows_skipped += 1
                continue

            # All same-user jobs completed before this query.
            user_history = user_rows[user][:pos]

            # UoPC itself uses only the newest theta eligible jobs.
            context = user_history[max(0, len(user_history) - theta) :]

            # Trivial per-user baseline: mean over all eligible prior jobs for
            # this user, with no future information.
            user_mean_avg_pred = float(np.mean(avg_target_arr[user_history]))
            user_mean_max_pred = float(np.mean(max_target_arr[user_history]))

            # Trivial global baseline: mean over all jobs completed before this
            # query's submission time, with no future information.
            global_pos = int(
                np.searchsorted(
                end_arr[order],
                submit_arr[j],
                side="left",
                )
            )
            global_history = order[:global_pos]

            global_mean_avg_pred = float(np.mean(avg_target_arr[global_history]))
            global_mean_max_pred = float(np.mean(max_target_arr[global_history]))

            # Match the authors' implementation used in Phase 1. Their KNN
            # wraps KNeighborsClassifier, so continuous per-node power labels
            # are rounded to integer classes before fitting. Fit the two paper
            # targets independently on the same eligible history context.
            avg_model = KNeighborsClassifier(n_neighbors=k)
            avg_model.fit(
                features[context],
                np.rint(avg_target_arr[context]).astype(np.int64),
            )
            avg_pred = avg_model.predict(features[j : j + 1])

            max_model = KNeighborsClassifier(n_neighbors=k)
            max_model.fit(
                features[context],
                np.rint(max_target_arr[context]).astype(np.int64),
            )
            max_pred = max_model.predict(features[j : j + 1])

            avg_y_true.append(float(avg_target_arr[j]))
            avg_y_pred.append(float(avg_pred[0]))
            max_y_true.append(float(max_target_arr[j]))
            max_y_pred.append(float(max_pred[0]))
            user_mean_avg_y_pred.append(user_mean_avg_pred)
            user_mean_max_y_pred.append(user_mean_max_pred)
            global_mean_avg_y_pred.append(global_mean_avg_pred)
            global_mean_max_y_pred.append(global_mean_max_pred)

        if not avg_y_true or not max_y_true:
            raise ValueError("No test rows produced scored predictions in paper reproduction.")

        avg_metric_defs = [
            {**metric_def, "target": "avgpcon_per_node"} for metric_def in resolved_metric_defs
        ]
        max_metric_defs = [
            {**metric_def, "target": "maxpcon_per_node"} for metric_def in resolved_metric_defs
        ]

        avg_metrics = compute_regression_metrics_from_defs(
            avg_y_true,
            avg_y_pred,
            avg_metric_defs,
        )
        max_metrics = compute_regression_metrics_from_defs(
            max_y_true,
            max_y_pred,
            max_metric_defs,
        )

        user_mean_avg_metrics = compute_regression_metrics_from_defs(
            avg_y_true,
            user_mean_avg_y_pred,
            avg_metric_defs,
        )
        user_mean_max_metrics = compute_regression_metrics_from_defs(
            max_y_true,
            user_mean_max_y_pred,
            max_metric_defs,
        )

        global_mean_avg_metrics = compute_regression_metrics_from_defs(
            avg_y_true,
            global_mean_avg_y_pred,
            avg_metric_defs,
        )
        global_mean_max_metrics = compute_regression_metrics_from_defs(
            max_y_true,
            global_mean_max_y_pred,
            max_metric_defs,
        )

        result: dict[str, Any] = {
            "avgpcon_per_node": {
                **avg_metrics,
                "definitions": avg_metric_defs,
            },
            "maxpcon_per_node": {
                **max_metrics,
                "definitions": max_metric_defs,
            },
            "baselines": {
                "per_user_mean": {
                    "avgpcon_per_node": {
                        **user_mean_avg_metrics,
                        "definitions": avg_metric_defs,
                    },
                    "maxpcon_per_node": {
                        **user_mean_max_metrics,
                        "definitions": max_metric_defs,
                    },
                },
                "global_mean": {
                    "avgpcon_per_node": {
                        **global_mean_avg_metrics,
                        "definitions": avg_metric_defs,
                    },
                    "maxpcon_per_node": {
                        **global_mean_max_metrics,
                        "definitions": max_metric_defs,
                    },
                },
            },
            "summary": {
                "rows_total": len(avg_target_arr),
                "rows_test": len(test_idx),
                "rows_scored": len(avg_y_true),
                "rows_skipped": rows_skipped,
                "theta": theta,
                "k": k,
                "test_start": test_start,
                "targets": [
                    "avgpcon/nnuma",
                    "maxpcon/nnuma",
                ],
                "features": "emb+znum",
                "predictor": "KNeighborsClassifier",
            },
        }

        if capture_artifacts:
            result["_avgpcon_y_true"] = avg_y_true
            result["_avgpcon_y_pred"] = avg_y_pred
            result["_maxpcon_y_true"] = max_y_true
            result["_maxpcon_y_pred"] = max_y_pred
            result["_last_model"] = {
                "kind": "job_power_uopc_paper_reproduction",
                "theta": theta,
                "k": k,
                "test_start": test_start,
                "targets": [
                    "avgpcon/nnuma",
                    "maxpcon/nnuma",
                ],
            }

        return result

    

    def evaluate_paper_sensitivity(
        self,
        rows: list[dict[str, Any]],
        *,
        test_start: str = "2024-02-01",
        theta_values: tuple[int, ...] = (
            50,
            100,
            200,
            500,
            1000,
            2000,
            5000,
        ),
        k_values: tuple[int, ...] = (5, 10, 20, 50),
        metric_defs: list[dict[str, Any]] | None = None,
        verbose: bool = False,
        capture_artifacts: bool = False,
    ) -> dict[str, Any]:
        """Evaluate UoPC theta/k sensitivity with reusable neighbor searches.

        For each theta and query job, nearest neighbors are retrieved once up to
        max(k_values). Those ordered neighbors are then reused for every k.

        Classifier voting is the faithful UoPC prediction rule. A mean-based
        regressor prediction is reported separately as an ablation.
        """
        if not theta_values:
            raise ValueError("theta_values must not be empty.")
        if not k_values:
            raise ValueError("k_values must not be empty.")
        if any(theta <= 0 for theta in theta_values):
            raise ValueError(
                "theta_values must contain only positive integers."
            )
        if any(k <= 0 for k in k_values):
            raise ValueError(
                "k_values must contain only positive integers."
            )

        theta_values = tuple(sorted(set(theta_values)))
        k_values = tuple(sorted(set(k_values)))
        max_k = max(k_values)

        resolved_metric_defs = metric_defs or [
            {"name": "mape", "target": "avgpcon_per_node"},
            {"name": "r2", "target": "avgpcon_per_node"},
        ]

        avg_metric_defs = [
            {**metric_def, "target": "avgpcon_per_node"}
            for metric_def in resolved_metric_defs
        ]

        max_metric_defs = [
            {**metric_def, "target": "maxpcon_per_node"}
            for metric_def in resolved_metric_defs
        ]

        prepared = self._prepare_paper_data(
            rows,
            test_start=test_start,
        )

        user_arr = prepared.user_arr
        submit_arr = prepared.submit_arr
        features = prepared.features
        avg_target_arr = prepared.avg_target_arr
        max_target_arr = prepared.max_target_arr
        user_rows = prepared.user_rows
        user_ends = prepared.user_ends
        test_idx = prepared.test_idx

        # One history count per test job. This is independent of theta and k
        # and can later be used for cold-start/coverage analysis.
        history_counts: list[int] = []

        # Results are accumulated independently for every theta/k pair because
        # coverage differs with k: a job with 7 prior jobs is valid for k=5
        # but not for k=10, 20, or 50.
        accumulators: dict[
            tuple[int, int],
            dict[str, dict[str, list[float]]],
        ] = {}

        for theta in theta_values:
            for k in k_values:
                accumulators[(theta, k)] = {
                    "classifier": {
                        "avg_true": [],
                        "avg_pred": [],
                        "max_true": [],
                        "max_pred": [],
                    },
                    "regressor": {
                        "avg_true": [],
                        "avg_pred": [],
                        "max_true": [],
                        "max_pred": [],
                    },
                }

        theta_timings: dict[int, float] = {}
        total_start = time.perf_counter()

        # Process one theta at a time. For each query, retrieve up to max_k
        # neighbors once and reuse them for all requested k values.
        for theta in theta_values:
            theta_start = time.perf_counter()

            iterator = tqdm(
                test_idx,
                desc=f"uopc-sensitivity/theta={theta}",
                unit="job",
                disable=not verbose,
            )

            for j in iterator:
                user = user_arr[j]
                ends_for_user = user_ends.get(user)

                if ends_for_user is None:
                    if theta == theta_values[0]:
                        history_counts.append(0)
                    continue

                pos = int(
                    np.searchsorted(
                        ends_for_user,
                        submit_arr[j],
                        side="left",
                    )
                )

                if theta == theta_values[0]:
                    history_counts.append(pos)

                if pos == 0:
                    continue

                user_history = user_rows[user][:pos]
                context = user_history[
                    max(0, len(user_history) - theta) :
                ]

                if len(context) == 0:
                    continue

                neighbor_indices, _neighbor_distances = (
                    _nearest_neighbor_indices_and_distances(
                        features[context],
                        features[j].reshape(1, -1),
                        max_neighbors=max_k,
                    )
                )

                if len(neighbor_indices) == 0:
                    continue

                # kneighbors() indices are relative to context.
                neighbor_rows = context[neighbor_indices]

                avg_neighbor_targets = avg_target_arr[neighbor_rows]
                max_neighbor_targets = max_target_arr[neighbor_rows]

                for k in k_values:
                    if len(neighbor_rows) < k:
                        continue

                    bucket = accumulators[(theta, k)]

                    avg_classifier_pred = (
                        _classifier_prediction_from_neighbor_targets(
                            avg_neighbor_targets,
                            k,
                        )
                    )
                    max_classifier_pred = (
                        _classifier_prediction_from_neighbor_targets(
                            max_neighbor_targets,
                            k,
                        )
                    )

                    avg_regressor_pred = (
                        _regressor_prediction_from_neighbor_targets(
                            avg_neighbor_targets,
                            k,
                        )
                    )
                    max_regressor_pred = (
                        _regressor_prediction_from_neighbor_targets(
                            max_neighbor_targets,
                            k,
                        )
                    )

                    avg_true = float(avg_target_arr[j])
                    max_true = float(max_target_arr[j])

                    bucket["classifier"]["avg_true"].append(avg_true)
                    bucket["classifier"]["avg_pred"].append(
                        avg_classifier_pred
                    )
                    bucket["classifier"]["max_true"].append(max_true)
                    bucket["classifier"]["max_pred"].append(
                        max_classifier_pred
                    )

                    bucket["regressor"]["avg_true"].append(avg_true)
                    bucket["regressor"]["avg_pred"].append(
                        avg_regressor_pred
                    )
                    bucket["regressor"]["max_true"].append(max_true)
                    bucket["regressor"]["max_pred"].append(
                        max_regressor_pred
                    )

            theta_timings[theta] = time.perf_counter() - theta_start

        total_seconds = time.perf_counter() - total_start

        results: dict[str, Any] = {}

        for theta in theta_values:
            theta_result: dict[str, Any] = {}

            for k in k_values:
                bucket = accumulators[(theta, k)]
                configuration: dict[str, Any] = {}

                for predictor in ("classifier", "regressor"):
                    values = bucket[predictor]

                    avg_true = values["avg_true"]
                    avg_pred = values["avg_pred"]
                    max_true = values["max_true"]
                    max_pred = values["max_pred"]

                    predictor_result: dict[str, Any] = {
                        "rows_scored": len(avg_true),
                        "coverage": (
                            len(avg_true) / len(test_idx)
                            if len(test_idx)
                            else 0.0
                        ),
                    }

                    if avg_true:
                        predictor_result["avgpcon_per_node"] = (
                            compute_regression_metrics_from_defs(
                                avg_true,
                                avg_pred,
                                avg_metric_defs,
                            )
                        )
                        predictor_result["maxpcon_per_node"] = (
                            compute_regression_metrics_from_defs(
                                max_true,
                                max_pred,
                                max_metric_defs,
                            )
                        )
                    else:
                        predictor_result["avgpcon_per_node"] = {}
                        predictor_result["maxpcon_per_node"] = {}

                    configuration[predictor] = predictor_result

                theta_result[str(k)] = configuration

            results[str(theta)] = theta_result

        history_arr = np.asarray(history_counts, dtype=np.int64)

        cold_start = {
            "rows_test": int(len(test_idx)),
            "history_count_min": (
                int(history_arr.min()) if history_arr.size else 0
            ),
            "history_count_max": (
                int(history_arr.max()) if history_arr.size else 0
            ),
            "history_count_mean": (
                float(history_arr.mean()) if history_arr.size else 0.0
            ),
            "history_count_median": (
                float(np.median(history_arr))
                if history_arr.size
                else 0.0
            ),
            "rows_with_0_history": int(
                np.sum(history_arr == 0)
            ),
            "rows_with_lt_5_history": int(
                np.sum(history_arr < 5)
            ),
            "rows_with_lt_10_history": int(
                np.sum(history_arr < 10)
            ),
            "rows_with_lt_20_history": int(
                np.sum(history_arr < 20)
            ),
            "rows_with_lt_50_history": int(
                np.sum(history_arr < 50)
            ),
        }

        result: dict[str, Any] = {
            "summary": {
                "rows_total": len(rows),
                "rows_test": int(len(test_idx)),
                "theta_values": list(theta_values),
                "k_values": list(k_values),
                "max_neighbors": max_k,
                "test_start": test_start,
                "primary_predictor": "KNeighborsClassifier",
                "ablation_predictor": "KNeighborsRegressor",
                "targets": [
                    "avgpcon/nnuma",
                    "maxpcon/nnuma",
                ],
                "features": "emb+znum",
                "history_rule": "same user with edt < query adt",
            },
            "results": results,
            "cold_start": cold_start,
            "timing": {
                "total_seconds": total_seconds,
                "theta_seconds": {
                    str(theta): seconds
                    for theta, seconds in theta_timings.items()
                },
            },
        }

        if capture_artifacts:
            result["_history_counts"] = history_counts

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
