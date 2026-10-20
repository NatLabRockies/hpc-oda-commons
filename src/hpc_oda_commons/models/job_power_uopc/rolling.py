"""UoPC on the shared rolling protocol, so it is scored like every other model (#204).

The paper protocol (``model.py``) scores every job after a date cutoff, each against the
history it would have had. To compare UoPC with the runtime models pointed at power, it has
to be scored on exactly their windows and rows instead:

- **Windows** come from ``build_rolling_splits``: train on jobs that finished in the
  lookback before the split, test on jobs submitted in the following window.
- **Context.** A test job's context is its user's newest ``theta`` *training* jobs, by end
  time. Within one window every test job of a user shares that context, so one kNN is
  fitted per (window, user) rather than per job.
- **Features** are the paper reproduction's adaptation, not the paper's own: the job
  embedding plus requested cores, nodes and CPU frequency, z-scored on the window's
  training rows. Unlike the paper protocol there is no look-ahead: test-period statistics
  never touch the scaling.
- **Prediction** is the median of the k neighbours' values by default (``predictor``, #241).
  ``vote`` is the authors' ``KNeighborsClassifier`` on targets rounded to whole units.
- **Cold start.** The other models score every test job; UoPC cannot score a user with
  fewer than ``k`` training jobs. Those jobs get the window's mean target, the rolling
  baseline's prediction, so every model is scored on the same rows. How many needed it is
  reported as ``rows_fallback``.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np
from tqdm import tqdm

from hpc_oda_commons.kernel.metrics import compute_regression_metrics_from_defs
from hpc_oda_commons.models.job_power_uopc.model import (
    _FEATURE_LABELS,
    UOPC_DEFAULT_FEATURES,
    UOPC_DEFAULT_K,
    UOPC_DEFAULT_PREDICTOR,
    _one_blas_thread,
    balanced_numeric_features,
    check_uopc_features,
    check_uopc_predictor,
    uopc_predict,
)
from hpc_oda_commons.models.rolling_tabular.split import _epoch_or_nan, build_rolling_splits


@dataclass(frozen=True)
class JobPowerUopcRollingConfig:
    """Configuration for UoPC on the rolling protocol."""

    n_windows: int = 1000
    test_window_hours: int = 6
    training_lookback_days: int = 100
    submit_time_field: str = "submit_time"
    end_time_field: str = "end_time"
    theta: int = 500
    k: int = UOPC_DEFAULT_K
    user_field: str = "user"
    embedding_field: str = "embedding"
    # The reproduction's numeric features: requested cores, nodes and frequency. The paper
    # puts these in the embedded text instead.
    numeric_fields: tuple[str, ...] = ("num_cores_req", "num_nodes_req", "freq_req")
    target_field: str = "avgpcon_per_node"
    # balanced (default: log2 nodes and frequency, weighted), zscore (the numeric_fields
    # above) or embedding (none); see model.UOPC_FEATURE_MODES (#222).
    features: str = UOPC_DEFAULT_FEATURES
    # median (default), mean or vote, the authors' rule; see model.UOPC_PREDICTORS (#241).
    predictor: str = UOPC_DEFAULT_PREDICTOR
    nodes_field: str = "num_nodes_req"
    frequency_field: str = "freq_req"


def _finite(value: Any) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return math.nan
    return out if math.isfinite(out) else math.nan


class JobPowerUopcRollingModel:
    """UoPC per-user kNN, evaluated on the shared rolling windows."""

    _evaluate_desc = "rolling/uopc"

    def __init__(self, config: JobPowerUopcRollingConfig | None = None) -> None:
        self.config = config or JobPowerUopcRollingConfig()
        self.target_field = self.config.target_field
        check_uopc_features(self.config.features)
        check_uopc_predictor(self.config.predictor)
        feature_fields = {
            self.config.embedding_field,
            *self.config.numeric_fields,
            self.config.nodes_field,
            self.config.frequency_field,
        }
        if self.target_field in feature_fields:
            raise ValueError(
                f"{self.target_field!r} is the prediction target, so it cannot be a feature."
            )

    def _arrays(self, rows: list[dict[str, Any]]) -> dict[str, np.ndarray]:
        cfg = self.config
        embeddings = [row.get(cfg.embedding_field) for row in rows]
        if any(e is None for e in embeddings):
            missing = sum(e is None for e in embeddings)
            raise ValueError(
                f"UoPC needs an {cfg.embedding_field!r} on every row; {missing} rows lack one."
            )
        users = np.asarray([str(row.get(cfg.user_field) or "") for row in rows])
        _, user_codes = np.unique(users, return_inverse=True)
        return {
            "embedding": np.ascontiguousarray(np.vstack(embeddings), dtype=np.float32),
            "numeric": np.asarray(
                [[_finite(row.get(f)) for f in cfg.numeric_fields] for row in rows],
                dtype=np.float64,
            ),
            "target": np.asarray([_finite(row.get(self.target_field)) for row in rows]),
            "user": user_codes.astype(np.int64),
            "nodes": np.asarray([_finite(row.get(cfg.nodes_field)) for row in rows]),
            "frequency": np.asarray([_finite(row.get(cfg.frequency_field)) for row in rows]),
            "end": np.asarray([_epoch_or_nan(row.get(cfg.end_time_field)) for row in rows]),
        }

    @_one_blas_thread
    def evaluate(
        self,
        rows: list[dict[str, Any]],
        *,
        verbose: bool = False,
        metric_defs: list[dict[str, Any]] | None = None,
        capture_artifacts: bool = False,
    ) -> dict[str, Any]:
        if not rows:
            raise ValueError("rows must be non-empty")
        cfg = self.config
        resolved_metric_defs = metric_defs or [
            {"name": "mae", "target": self.target_field},
            {"name": "rmse", "target": self.target_field},
        ]
        arrays = self._arrays(rows)
        splits = build_rolling_splits(
            rows,
            n_windows=cfg.n_windows,
            test_window_hours=cfg.test_window_hours,
            training_lookback_days=cfg.training_lookback_days,
            submit_time_field=cfg.submit_time_field,
            end_time_field=cfg.end_time_field,
            verbose=verbose,
        )

        windows: list[dict[str, Any]] = []
        all_true: list[float] = []
        all_pred: list[float] = []
        rows_fallback = 0
        for split in tqdm(splits, desc=self._evaluate_desc, unit="window", disable=not verbose):
            entry = split.to_dict()
            train = split.train_row_indices
            test = split.test_row_indices
            train = train[np.isfinite(arrays["target"][train])]
            test = test[np.isfinite(arrays["target"][test])]
            if len(train) == 0 or len(test) == 0:
                reason = (
                    "insufficient_training_rows" if len(train) == 0 else "insufficient_test_rows"
                )
                windows.append({**entry, "status": "skipped", "reason": reason, "metrics": None})
                continue

            y_true, y_pred, fallback = self._score_window(arrays, train, test)
            rows_fallback += fallback
            all_true.extend(y_true)
            all_pred.extend(y_pred)
            windows.append(
                {
                    **entry,
                    "status": "ok",
                    "reason": None,
                    "train_rows_supervised": int(len(train)),
                    "test_rows_supervised": int(len(test)),
                    "rows_fallback": int(fallback),
                    "metrics": compute_regression_metrics_from_defs(
                        y_true, y_pred, resolved_metric_defs
                    ),
                }
            )

        if not all_true:
            raise ValueError("No rolling splits produced scored predictions.")

        metrics = compute_regression_metrics_from_defs(all_true, all_pred, resolved_metric_defs)
        windows_scored = sum(1 for w in windows if w["status"] == "ok")
        result: dict[str, Any] = {
            **metrics,
            "definitions": resolved_metric_defs,
            "windows": windows,
            "summary": {
                "windows_total": len(splits),
                "windows_scored": windows_scored,
                "windows_skipped": len(splits) - windows_scored,
                "rows_scored": len(all_true),
                "rows_fallback": rows_fallback,
                "n_windows": cfg.n_windows,
                "test_window_hours": cfg.test_window_hours,
                "training_lookback_days": cfg.training_lookback_days,
                "theta": cfg.theta,
                "k": cfg.k,
                "features": _FEATURE_LABELS[cfg.features],
                "predictor": cfg.predictor,
                "target_field": self.target_field,
            },
        }
        if capture_artifacts:
            result["_y_true"] = all_true
            result["_y_pred"] = all_pred
            result["_last_model"] = {"kind": "job_power_uopc_rolling", "config": cfg}
        return result

    def _score_window(
        self, arrays: dict[str, np.ndarray], train: np.ndarray, test: np.ndarray
    ) -> tuple[list[float], list[float], int]:
        """Predict every test job of one window; returns (y_true, y_pred, n_fallback)."""
        cfg = self.config
        target = arrays["target"]
        numeric = arrays["numeric"][train]
        with warnings.catch_warnings():
            # A dataset without one of these columns gives an all-NaN column, whose
            # mean is NaN by definition; it is replaced just below.
            warnings.simplefilter("ignore", RuntimeWarning)
            mu = np.nanmean(numeric, axis=0)
            sd = np.nanstd(numeric, axis=0)
        mu = np.where(np.isfinite(mu), mu, 0.0)
        sd = np.where(np.isfinite(sd) & (sd > 0), sd, 1.0)
        window_mean = float(np.mean(target[train]))

        balanced = None
        if cfg.features == "balanced":
            # Once per window, with frequency's range fitted on its training rows only.
            fit = np.zeros(len(target), dtype=bool)
            fit[train] = True
            balanced = balanced_numeric_features(arrays["nodes"], arrays["frequency"], fit=fit)

        def features(idx: np.ndarray) -> np.ndarray:
            if cfg.features == "embedding":
                return arrays["embedding"][idx]
            if balanced is not None:
                return np.hstack([arrays["embedding"][idx], balanced[idx]])
            scaled = (np.nan_to_num(arrays["numeric"][idx], nan=0.0) - mu) / sd
            return np.hstack([arrays["embedding"][idx], scaled.astype(np.float32)])

        # Training rows grouped by user, each user's newest last; span[user] = (lo, hi).
        train = train[np.lexsort((arrays["end"][train], arrays["user"][train]))]
        users, starts = np.unique(arrays["user"][train], return_index=True)
        stops = np.append(starts[1:], len(train))
        span = {int(u): (int(a), int(b)) for u, a, b in zip(users, starts, stops, strict=True)}

        y_true: list[float] = []
        y_pred: list[float] = []
        fallback = 0
        test_users = arrays["user"][test]
        for user in np.unique(test_users).tolist():
            queries = test[test_users == user]
            lo, hi = span.get(user, (0, 0))
            context = train[max(lo, hi - cfg.theta) : hi]
            if len(context) < cfg.k:
                preds = np.full(len(queries), window_mean)
                fallback += len(queries)
            else:
                (preds,) = uopc_predict(
                    features(context),
                    (target[context],),
                    features(queries),
                    k=cfg.k,
                    predictor=cfg.predictor,
                )
            y_true.extend(float(v) for v in target[queries])
            y_pred.extend(float(v) for v in preds)
        return y_true, y_pred, fallback
