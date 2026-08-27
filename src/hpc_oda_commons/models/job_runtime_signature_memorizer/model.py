"""Predict a job's runtime from identical jobs that already ran.

The benchmark's only reference point was `job_runtime_baseline`, a rolling mean. Every real
model beats it comfortably, so it confirms the models do *something* without saying whether
they do something hard.

This is the harder trivial baseline: for each test job, take the jobs in the training window
whose **submit-time features are identical** and predict their median runtime. No fitting, no
hyperparameters beyond the lookback the split already fixes. When no identical job exists it
backs off, dropping features one at a time -- cheapest first, by information cost measured on
the training window -- until something matches, and finally to the window median.

It is worth having because it wins. On the fleet run of 2026-08-25 it beat all six fitted
models on 9 of 20 datasets, including both in-house machines (#171). A lookup table has no
capacity advantage over gradient boosting; the only thing it does that the shared pipeline
does not is keep the exact high-cardinality combination that one-hot encoding with a minimum
frequency threshold, followed by truncated SVD, dissolves (#172).

Routing happens inside the shared rolling window: this subclasses ``RollingTabularModel`` and
overrides only the fit/predict seam, so it sees the same grid, the same scored rows and the
same payload shape as every other model. That is what makes its MAE comparable with theirs.

**Coverage is reported alongside its metrics.** A memorization score is uninterpretable
without knowing how often it could match anything at all.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np

from hpc_oda_commons.models.rolling_tabular.base import (
    RollingTabularConfig,
    RollingTabularModel,
    _DailyPreprocessingArtifacts,
)

_MISSING = "\x00"


@dataclass(frozen=True)
class SignatureMemorizerConfig(RollingTabularConfig):
    """Configuration for the signature-memorization baseline."""

    # How many features may be dropped when nothing matches exactly. 0 disables backoff,
    # leaving the window median as the only fallback.
    backoff_levels: int = 3


class JobRuntimeSignatureMemorizerModel(RollingTabularModel):
    """Median runtime of same-signature jobs from the training window."""

    _evaluate_desc = "rolling/signature_memorizer"
    _log_prefix = "signature_memorizer"

    def __init__(self, config: SignatureMemorizerConfig | None = None) -> None:
        super().__init__(config or SignatureMemorizerConfig())
        self._stats_lock = threading.Lock()
        self._stats: list[dict[str, Any]] = []
        self._backoff_order: tuple[tuple[str, ...], tuple[str, ...]] | None = None

    # --- preprocessing this model deliberately skips ------------------------------

    def _build_daily_preprocessing_artifacts(
        self, train_rows: list[dict[str, Any]]
    ) -> _DailyPreprocessingArtifacts:
        """No encoder, no SVD -- and that is the point.

        The shared pipeline one-hot encodes categoricals, drops rare values below a minimum
        frequency, and compresses with truncated SVD. This model exists to keep the exact
        combination that process dissolves, so building those artifacts would cost real time
        per day (SVD over a wide one-hot matrix) to produce something immediately discarded.
        It would also inherit that path's failure modes for free -- see #159, where the SVD
        failed to converge on one dataset under the cluster's BLAS.
        """
        allowed = self.allowed_feature_fields()
        numeric = [
            c for c in self._detect_numeric_columns(train_rows, exclude=set()) if c in allowed
        ]
        # Numeric columns are kept so the shared driver still sees a well-formed feature
        # matrix (it skips windows that have none); they cost a column scan, not an SVD.
        return _DailyPreprocessingArtifacts(
            numeric_columns=tuple(numeric),
            categorical_columns=(),
            one_hot_min_frequency=0,
            one_hot_handle_unknown="infrequent_if_exist",
            encoder=None,
            svd=None,
            svd_components=0,
            svd_coverage=1.0,
        )

    # --- signatures ---------------------------------------------------------------

    def _signature_fields(self, rows: list[dict[str, Any]]) -> list[str]:
        usable, _ignored = self.feature_field_report(rows)
        return sorted(usable)

    @staticmethod
    def _keys(rows: list[dict[str, Any]], fields: list[str]) -> list[tuple[str, ...]]:
        """One hashable key per row. Nulls are a value, not missing data: two jobs that
        both omitted a field are indistinguishable in exactly the way this model is about."""
        return [
            tuple(_MISSING if row.get(f) is None else str(row.get(f)) for f in fields)
            for row in rows
        ]

    def _cached_backoff_order(
        self, train_rows: list[dict[str, Any]], y_train: np.ndarray, fields: list[str]
    ) -> list[str]:
        """Compute the backoff order once per evaluation, not once per window.

        Measuring it costs one grouping per feature, so recomputing it for all 120 windows
        multiplied the model's runtime by roughly the feature count. Which features carry
        the information is a property of the dataset, not of a six-hour window, so the
        first window's answer is reused.
        """
        with self._stats_lock:
            cached = self._backoff_order
        if cached is not None and cached[0] == tuple(fields):
            return list(cached[1])
        order = self._feature_costs(train_rows, y_train, fields)
        with self._stats_lock:
            self._backoff_order = (tuple(fields), tuple(order))
        return order

    def _feature_costs(
        self, train_rows: list[dict[str, Any]], y_train: np.ndarray, fields: list[str]
    ) -> list[str]:
        """Fields ordered by how little the grouping loses when each is dropped.

        Cardinality is the wrong criterion in either direction -- it measures how much a drop
        coarsens the groups, not what is given up. Measure it instead (#169).
        """
        if len(fields) < 2:
            return list(fields)
        base = self._grouping_error(self._keys(train_rows, fields), y_train)
        scored = []
        for field_name in fields:
            others = [f for f in fields if f != field_name]
            cost = self._grouping_error(self._keys(train_rows, others), y_train) - base
            # Ties broken toward the higher-cardinality field: when two drops give up the
            # same information, the coarser one buys more matches per unit given up.
            cardinality = len({row.get(field_name) for row in train_rows})
            scored.append((cost, -cardinality, field_name))
        return [f for _cost, _card, f in sorted(scored, key=lambda s: (s[0], s[1]))]

    @staticmethod
    def _grouping_error(keys: list[tuple[str, ...]], y: np.ndarray) -> float:
        """Mean absolute deviation from each group's median -- the floor for this grouping."""
        groups: dict[tuple[str, ...], list[float]] = defaultdict(list)
        for key, value in zip(keys, y, strict=True):
            groups[key].append(float(value))
        total = 0.0
        for values in groups.values():
            med = float(np.median(values))
            total += float(np.abs(np.asarray(values) - med).sum())
        return total / len(y) if len(y) else 0.0

    # --- the seam -----------------------------------------------------------------

    def _fit_predict(
        self,
        x_train: Any,
        y_train: Any,
        x_test: Any,
        *,
        train_rows: list[dict[str, Any]],
        test_rows: list[dict[str, Any]],
        artifacts: Any,
        sample_weight: Any | None = None,
    ) -> tuple[Any, Any]:
        # The encoded matrices are what this model deliberately does not use: the point is
        # to keep the exact signature that encoding dissolves. sample_weight (recency) is
        # not applied -- a weighted median would make this no longer the trivial baseline.
        del x_train, x_test, artifacts, sample_weight

        y = np.asarray(y_train, dtype=float)
        fields = self._signature_fields(train_rows)
        if not fields or y.size == 0:
            fallback = float(np.median(y)) if y.size else 0.0
            self._record(len(test_rows), 0)
            return {"fields": [], "levels": 0}, np.full(len(test_rows), fallback)

        levels = [fields]
        max_backoff = min(int(self.config.backoff_levels), len(fields) - 1)
        if max_backoff > 0:
            order = self._cached_backoff_order(train_rows, y, fields)
            for k in range(1, max_backoff + 1):
                levels.append([f for f in fields if f not in set(order[:k])])

        window_median = float(np.median(y))
        pred = np.full(len(test_rows), np.nan)
        exact_hits = 0
        for depth, level_fields in enumerate(levels):
            need = np.flatnonzero(~np.isfinite(pred))
            if need.size == 0:
                break
            table: dict[tuple[str, ...], float] = {}
            groups: dict[tuple[str, ...], list[float]] = defaultdict(list)
            for key, value in zip(self._keys(train_rows, level_fields), y, strict=True):
                groups[key].append(float(value))
            for key, values in groups.items():
                table[key] = float(np.median(values))

            wanted_rows = [test_rows[i] for i in need]
            for offset, key in enumerate(self._keys(wanted_rows, level_fields)):
                hit = table.get(key)
                if hit is not None:
                    pred[need[offset]] = hit
                    if depth == 0:
                        exact_hits += 1

        self._record(len(test_rows), exact_hits)
        pred = np.where(np.isfinite(pred), pred, window_median)
        return {"fields": fields, "levels": len(levels)}, pred

    def _record(self, n_test: int, exact_hits: int) -> None:
        with self._stats_lock:
            self._stats.append({"rows": n_test, "exact": exact_hits})

    # --- payload ------------------------------------------------------------------

    def evaluate(
        self,
        rows: list[dict[str, Any]],
        *,
        verbose: bool = False,
        metric_defs: list[dict[str, Any]] | None = None,
        capture_artifacts: bool = False,
    ) -> dict[str, Any]:
        with self._stats_lock:
            self._stats = []
            self._backoff_order = None

        payload = super().evaluate(
            rows,
            verbose=verbose,
            metric_defs=metric_defs,
            capture_artifacts=capture_artifacts,
        )

        with self._stats_lock:
            stats = list(self._stats)
        scored = sum(s["rows"] for s in stats)
        exact = sum(s["exact"] for s in stats)
        summary = {
            "windows": len(stats),
            "rows_scored": scored,
            # Without this the metric is uninterpretable: a good score on 20% coverage and a
            # good score on 90% are different claims.
            "exact_match_coverage": (exact / scored) if scored else 0.0,
            "backoff_levels": int(self.config.backoff_levels),
        }
        payload["summary"]["memorization"] = summary
        if verbose:
            print(
                f"[{self._log_prefix}][verbose] "
                f"exact-match coverage={summary['exact_match_coverage']:.1%} "
                f"over {scored:,} scored rows"
            )
        return payload
