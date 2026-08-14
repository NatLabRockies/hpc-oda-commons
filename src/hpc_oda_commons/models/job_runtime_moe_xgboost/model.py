"""
Mixture-of-Experts runtime prediction: per-bin XGBoost experts, routed by user
identity and requested wallclock.

The premise (issue #124): HPC users request wallclock at the limit of the partition
they submit to, so ``requested_seconds`` piles up on a handful of round values that
are really *different job populations* — short debug work, day-long production,
multi-day campaigns. One model fitted across all of them serves none of them well.

How this one works, per rolling window:

1. **Bins come from the data.** The modal values of ``requested_seconds`` in the
   window's *training* rows become the bin edges, so each system gets its own
   partition limits rather than one site's numbers hardcoded. A distribution with
   no clear modes falls back to quantile edges.
2. **Power users get their own experts.** Users above ``power_user_percentile`` by
   job count (again, measured on training rows only) are routed to an expert per
   (user, wallclock bin); everyone else shares a pooled expert per bin.
3. **A fallback expert always exists.** It is fitted on the whole training window,
   and any test row whose bin has fewer than ``min_expert_rows`` training rows is
   scored by it — so a sparse bin costs accuracy, never coverage.
4. **Recency weighting** (``time_decay_rate``, contributed with the original model)
   weights training rows by ``exp(-rate * days_old)``.

Routing happens *inside* the shared rolling window, not by splitting the dataset up
front: the model subclasses ``RollingTabularModel`` and overrides only the
fit/predict seam. It therefore sees the same window grid, the same preprocessing and
the same scored rows as every other model, which is what makes its MAE comparable
with theirs.
"""

from __future__ import annotations

import importlib.util
import math
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass, fields
from typing import Any

import numpy as np

from hpc_oda_commons.models.rolling_tabular.base import (
    RollingTabularConfig,
    RollingTabularModel,
    _DailyPreprocessingArtifacts,
)

# Route key for every non-power user, and for a row whose user is missing.
POOLED_USER = "__pooled__"
# Bin index for a row with no usable requested wallclock.
UNKNOWN_BIN = -1


@dataclass(frozen=True)
class MoEXGBoostConfig(RollingTabularConfig):
    """Configuration for the user + wallclock mixture-of-experts XGBoost model."""

    # --- XGBoost hyperparameters (per expert) ---
    n_estimators: int = 200
    max_depth: int = 8
    learning_rate: float = 0.05
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    min_child_weight: int = 5
    gamma: float = 0.1
    estimator_n_jobs: int = 1

    # --- Routing ---
    # Users at or above this quantile of job count get per-user experts.
    power_user_percentile: float = 0.99
    # A bin needs this many training rows before it gets its own expert; below it,
    # its test rows are scored by the window-wide fallback expert.
    min_expert_rows: int = 100
    # How many wallclock bins to derive, and how large a share of the training window
    # a requested-wallclock value must hold to count as a cluster rather than noise.
    n_wallclock_bins: int = 5
    min_cluster_fraction: float = 0.02
    # Explicit bin edges in hours (upper bounds, ascending). Set this to pin a known
    # partition layout; leave None to derive the edges from each training window.
    wallclock_bin_edges_hours: tuple[float, ...] | None = None

    # Recency weighting is available (0.05 is a ~2 week half-life), but defaults OFF to
    # match the shared base. A model whose defaults differ from the base on a dimension
    # unrelated to what the model *is* makes every comparison against another model
    # bundle two changes at once: routing and reweighting. Enable it from a recipe when
    # you want it, and measure it as its own arm.
    time_decay_rate: float = 0.0


@dataclass(frozen=True)
class _Routing:
    """Where a job goes, derived once per day from training rows only."""

    bin_edges: tuple[float, ...]  # ascending upper bounds in seconds; last is inf
    power_users: frozenset[str]

    def bin_index(self, row: dict[str, Any]) -> int:
        raw = row.get("requested_seconds")
        if raw is None or not isinstance(raw, (int, float)) or isinstance(raw, bool):
            return UNKNOWN_BIN
        value = float(raw)
        if not math.isfinite(value) or value <= 0.0:
            return UNKNOWN_BIN
        for index, edge in enumerate(self.bin_edges):
            if value <= edge:
                return index
        return len(self.bin_edges) - 1

    def key(self, row: dict[str, Any]) -> tuple[str, int]:
        user = row.get("user")
        who = user if isinstance(user, str) and user in self.power_users else POOLED_USER
        return (who, self.bin_index(row))


@dataclass(frozen=True)
class _MoEDailyArtifacts(_DailyPreprocessingArtifacts):
    """The shared daily preprocessing artifacts, plus that day's routing."""

    routing: _Routing


@dataclass
class _MoEWindowModel:
    """What one window fitted: the fallback plus whichever experts earned their keep."""

    fallback: Any
    experts: dict[tuple[str, int], Any]
    routing: _Routing


class MoEXGBoostModel(RollingTabularModel):
    """Mixture-of-experts XGBoost over the shared rolling-window framework."""

    _evaluate_desc = "rolling/moe_xgboost"
    _log_prefix = "moe_xgboost"

    def __init__(self, config: MoEXGBoostConfig | None = None) -> None:
        super().__init__(config or MoEXGBoostConfig())
        self._routing_lock = threading.Lock()
        self._routing_stats: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ deps
    @staticmethod
    def _check_dependencies() -> None:
        missing = [pkg for pkg in ("xgboost", "sklearn") if importlib.util.find_spec(pkg) is None]
        if missing:
            raise RuntimeError(
                f"Missing optional model dependencies: {', '.join(missing)}. "
                'Install with `pip install -e ".[dev]"`.'
            )

    def _new_regressor(self, n_train: int) -> Any:
        from xgboost import XGBRegressor

        del n_train
        cfg: MoEXGBoostConfig = self.config  # type: ignore[assignment]
        return XGBRegressor(
            n_estimators=cfg.n_estimators,
            max_depth=cfg.max_depth,
            learning_rate=cfg.learning_rate,
            subsample=cfg.subsample,
            colsample_bytree=cfg.colsample_bytree,
            min_child_weight=cfg.min_child_weight,
            gamma=cfg.gamma,
            random_state=cfg.random_state,
            n_jobs=cfg.estimator_n_jobs,
            verbosity=0,
        )

    # --------------------------------------------------------------- routing
    def _wallclock_edges(self, train_rows: list[dict[str, Any]]) -> tuple[float, ...]:
        """Bin edges in seconds, from the training window's requested-wallclock modes."""
        cfg: MoEXGBoostConfig = self.config  # type: ignore[assignment]
        if cfg.wallclock_bin_edges_hours:
            edges = sorted({float(h) * 3600.0 for h in cfg.wallclock_bin_edges_hours})
            return (*edges, math.inf)

        values = np.array(
            [
                float(v)
                for row in train_rows
                if isinstance(v := row.get("requested_seconds"), (int, float))
                and not isinstance(v, bool)
                and math.isfinite(float(v))
                and float(v) > 0.0
            ],
            dtype=float,
        )
        if values.size == 0:
            return (math.inf,)

        # Requested wallclock clusters hard on partition limits, so the modal values
        # *are* the class boundaries. Keep only modes that hold a real share of the
        # window; anything rarer is noise, not a partition.
        counts = Counter(values.tolist())
        floor = cfg.min_cluster_fraction * values.size
        modes = sorted(
            value for value, count in counts.most_common(cfg.n_wallclock_bins) if count >= floor
        )
        if len(modes) >= 2:
            # Each mode is the top of a class ("everything that asked for <= 2h"), and
            # the last bin catches whatever sits above the largest cluster. Keep at most
            # n_wallclock_bins bins in total.
            return (*modes[: cfg.n_wallclock_bins - 1], math.inf)

        # No partition structure to find (continuous or single-valued requests):
        # fall back to quantiles so the bins at least split the population.
        quantiles = np.quantile(
            values, [i / cfg.n_wallclock_bins for i in range(1, cfg.n_wallclock_bins)]
        )
        edges = sorted({float(q) for q in quantiles})
        return (*edges, math.inf)

    def _power_users(self, train_rows: list[dict[str, Any]]) -> frozenset[str]:
        cfg: MoEXGBoostConfig = self.config  # type: ignore[assignment]
        counts = Counter(
            row["user"] for row in train_rows if isinstance(row.get("user"), str) and row["user"]
        )
        if not counts:
            return frozenset()
        threshold = float(np.quantile(list(counts.values()), cfg.power_user_percentile))
        return frozenset(user for user, count in counts.items() if count >= threshold)

    def _build_daily_preprocessing_artifacts(
        self, train_rows: list[dict[str, Any]]
    ) -> _MoEDailyArtifacts:
        """Shared preprocessing plus the day's routing, both from training rows only.

        Deriving the routing here — rather than once over the whole table — is what
        keeps it honest: a window never sees who the heavy users turn out to be later,
        or which wallclock values a future partition will popularise.
        """
        base = super()._build_daily_preprocessing_artifacts(train_rows)
        shared = {field.name: getattr(base, field.name) for field in fields(base)}
        return _MoEDailyArtifacts(
            **shared,
            routing=_Routing(
                bin_edges=self._wallclock_edges(train_rows),
                power_users=self._power_users(train_rows),
            ),
        )

    # ----------------------------------------------------------- fit/predict
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
        cfg: MoEXGBoostConfig = self.config  # type: ignore[assignment]
        routing: _Routing = artifacts.routing
        targets = np.asarray(y_train, dtype=float)

        # The fallback is fitted first and predicts every test row, so coverage never
        # depends on routing: an expert only ever overwrites rows it is qualified for.
        fallback = self._new_regressor(x_train.shape[0])
        self._fit_estimator(fallback, x_train, targets, sample_weight)
        predictions = np.asarray(fallback.predict(x_test), dtype=float)

        train_by_key: dict[tuple[str, int], list[int]] = defaultdict(list)
        for index, row in enumerate(train_rows):
            train_by_key[routing.key(row)].append(index)
        test_by_key: dict[tuple[str, int], list[int]] = defaultdict(list)
        for index, row in enumerate(test_rows):
            test_by_key[routing.key(row)].append(index)

        experts: dict[tuple[str, int], Any] = {}
        routed_rows = 0
        # Only bins that actually appear in this window's test rows are worth fitting.
        for key, test_indices in test_by_key.items():
            train_indices = train_by_key.get(key, [])
            if len(train_indices) < cfg.min_expert_rows:
                continue
            rows_idx = np.asarray(train_indices, dtype=int)
            expert = self._new_regressor(len(train_indices))
            self._fit_estimator(
                expert,
                x_train[rows_idx],
                targets[rows_idx],
                None if sample_weight is None else sample_weight[rows_idx],
            )
            experts[key] = expert
            test_idx = np.asarray(test_indices, dtype=int)
            predictions[test_idx] = np.asarray(expert.predict(x_test[test_idx]), dtype=float)
            routed_rows += len(test_indices)

        with self._routing_lock:
            self._routing_stats.append(
                {
                    "experts": len(experts),
                    "test_rows": len(test_rows),
                    "routed_rows": routed_rows,
                    "bins": len(routing.bin_edges),
                    "power_users": len(routing.power_users),
                    "bin_edges_hours": [
                        None if math.isinf(edge) else round(edge / 3600.0, 3)
                        for edge in routing.bin_edges
                    ],
                }
            )
        return _MoEWindowModel(fallback=fallback, experts=experts, routing=routing), predictions

    # ------------------------------------------------------------- evaluate
    def evaluate(
        self,
        rows: list[dict[str, Any]],
        *,
        verbose: bool = False,
        metric_defs: list[dict[str, Any]] | None = None,
        capture_artifacts: bool = False,
    ) -> dict[str, Any]:
        with self._routing_lock:
            self._routing_stats = []

        payload = super().evaluate(
            rows,
            verbose=verbose,
            metric_defs=metric_defs,
            capture_artifacts=capture_artifacts,
        )

        summary = self._routing_summary()
        payload["summary"]["moe_routing"] = summary
        if verbose and summary["windows"]:
            print(
                f"[{self._log_prefix}][verbose] routing "
                f"experts/window={summary['experts_per_window_mean']:.1f} "
                f"routed={summary['routed_row_fraction']:.1%} "
                f"power_users={summary['power_users_last']} "
                f"bin_edges_hours={summary['bin_edges_hours_last']}"
            )
        return payload

    def _routing_summary(self) -> dict[str, Any]:
        with self._routing_lock:
            stats = list(self._routing_stats)
        if not stats:
            return {
                "windows": 0,
                "experts_per_window_mean": 0.0,
                "routed_row_fraction": 0.0,
                "power_users_last": 0,
                "bin_edges_hours_last": [],
            }
        test_rows = sum(s["test_rows"] for s in stats)
        routed = sum(s["routed_rows"] for s in stats)
        return {
            "windows": len(stats),
            "experts_per_window_mean": sum(s["experts"] for s in stats) / len(stats),
            "routed_row_fraction": (routed / test_rows) if test_rows else 0.0,
            "fallback_rows": test_rows - routed,
            "power_users_last": stats[-1]["power_users"],
            "bin_edges_hours_last": stats[-1]["bin_edges_hours"],
        }
