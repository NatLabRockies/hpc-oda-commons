"""
Mixture-of-Experts model for job runtime prediction.

Routes jobs to specialized per-bin XGBoost models based on user identity
and requested wallclock time. Each bin gets its own model trained only on
jobs from that bin, with exponential time-decay sample weighting.

Bins are formed by:
  - Power users (top 1% by job count): one bin per user × wallclock cluster
  - Non-power users: one bin per wallclock cluster

Wallclock clusters: <=2h, 2-4h, 4-24h, 24-48h, >48h
"""

from __future__ import annotations

import importlib.util
from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np

from hpc_oda_commons.models.rolling_tabular.base import (
    RollingTabularConfig,
    RollingTabularModel,
)

# ---------------------------------------------------------------------------
# Wallclock bin definitions
# ---------------------------------------------------------------------------
BIN_EDGES_H = [0, 2, 4, 24, 48, float("inf")]
BIN_LABELS = ["<=2h", "2-4h", "4-24h", "24-48h", ">48h"]


def _wallclock_label(row: dict) -> str:
    wc_h = (row.get("requested_seconds") or 0) / 3600
    for i in range(len(BIN_EDGES_H) - 1):
        if wc_h <= BIN_EDGES_H[i + 1]:
            return BIN_LABELS[i]
    return BIN_LABELS[-1]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MoEXGBoostConfig(RollingTabularConfig):
    """Config for the User+Wallclock MoE XGBoost model."""

    # XGBoost hyperparameters
    n_estimators: int = 200
    max_depth: int = 12
    learning_rate: float = 0.03
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    min_child_weight: int = 5
    gamma: float = 0.1
    estimator_n_jobs: int = 1

    # MoE routing
    power_user_percentile: float = 0.99
    min_bin_rows: int = 100  # bins with fewer rows use fallback

    # Time decay (default: 0.05 ≈ 3 week half-life)
    time_decay_rate: float = 0.05


# ---------------------------------------------------------------------------
# Per-bin sub-model (reuses RollingTabularModel machinery)
# ---------------------------------------------------------------------------
class _BinXGBoostModel(RollingTabularModel):
    """XGBoost model for a single MoE bin. Not intended for direct use."""

    _evaluate_desc = "moe/bin"
    _log_prefix = "moe_bin"

    def __init__(self, config: MoEXGBoostConfig) -> None:
        super().__init__(config)

    @staticmethod
    def _check_dependencies() -> None:
        missing: list[str] = []
        for package in ("xgboost", "sklearn"):
            if importlib.util.find_spec(package) is None:
                missing.append(package)
        if missing:
            raise RuntimeError(
                f"Missing optional model dependencies: {', '.join(missing)}. "
                'Install with `pip install -e ".[dev]"`.'
            )

    def _new_regressor(self, n_train: int) -> Any:
        from xgboost import XGBRegressor

        _ = n_train
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


# ---------------------------------------------------------------------------
# MoE model
# ---------------------------------------------------------------------------
class MoEXGBoostModel:
    """
    Mixture-of-Experts runtime prediction model.

    Routes jobs to per-bin XGBoost models by user identity and wallclock
    cluster. Each bin is evaluated independently using the rolling
    train/test framework with time-decay sample weighting.

    Public API matches the rolling model interface:
      - evaluate(rows, *, verbose, metric_defs, capture_artifacts) -> dict
    """

    def __init__(self, config: MoEXGBoostConfig | None = None) -> None:
        self.config = config or MoEXGBoostConfig()

    def _build_bins(
        self, rows: list[dict[str, Any]]
    ) -> tuple[dict[str, list[dict[str, Any]]], set[str]]:
        """Assign rows to bins. Returns (bins_dict, power_users_set)."""
        user_counts = Counter(r.get("user") for r in rows)
        threshold = np.percentile(
            list(user_counts.values()),
            self.config.power_user_percentile * 100,
        )
        power_users = {u for u, c in user_counts.items() if c >= threshold}

        bins: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            user = row.get("user")
            wc = _wallclock_label(row)
            if user in power_users:
                key = f"power {user[:7]}/{wc}"
            else:
                key = f"non-power/{wc}"
            bins.setdefault(key, []).append(row)

        return bins, power_users

    def evaluate(
        self,
        rows: list[dict[str, Any]],
        *,
        verbose: bool = False,
        metric_defs: list[dict[str, Any]] | None = None,
        capture_artifacts: bool = False,
    ) -> dict[str, Any]:
        """Run MoE evaluation across all bins.

        Each bin gets its own rolling XGBoost evaluation. Results are
        aggregated into a single payload matching the standard interface.
        """
        if not rows:
            raise ValueError("rows must be non-empty")

        resolved_metric_defs = metric_defs or [
            {"name": "mae", "target": "runtime_seconds"},
            {"name": "rmse", "target": "runtime_seconds"},
        ]

        bins, power_users = self._build_bins(rows)
        valid_bins = {k: v for k, v in bins.items() if len(v) >= self.config.min_bin_rows}
        sorted_bins = sorted(valid_bins.items(), key=lambda x: -len(x[1]))

        if verbose:
            print(f"[moe] Power users: {len(power_users)}")
            print(f"[moe] Valid bins: {len(valid_bins)} (min_rows={self.config.min_bin_rows})")
            for name, bin_rows in sorted_bins:
                print(f"[moe]   {name:<35} {len(bin_rows):>10,} rows")

        # Evaluate each bin independently
        all_y_true: list[float] = []
        all_y_pred: list[float] = []
        all_windows: list[dict[str, Any]] = []
        bin_summaries: list[dict[str, Any]] = []
        total_scored = 0

        for bin_idx, (bin_name, bin_rows) in enumerate(sorted_bins):
            if verbose:
                print(
                    f"[moe] [{bin_idx + 1}/{len(sorted_bins)}] "
                    f"{bin_name} ({len(bin_rows):,} rows)..."
                )

            model = _BinXGBoostModel(self.config)
            try:
                payload = model.evaluate(
                    bin_rows,
                    verbose=False,
                    metric_defs=resolved_metric_defs,
                    capture_artifacts=capture_artifacts,
                )
                scored = payload["summary"]["rows_scored"]
                total_scored += scored

                bin_summaries.append(
                    {
                        "bin": bin_name,
                        "rows": len(bin_rows),
                        "scored": scored,
                        "mae": payload["mae"],
                        "rmse": payload["rmse"],
                    }
                )

                if capture_artifacts and "_y_true" in payload:
                    all_y_true.extend(payload["_y_true"])
                    all_y_pred.extend(payload["_y_pred"])

                # Collect window entries tagged with bin name
                for w in payload["windows"]:
                    w["bin"] = bin_name
                    all_windows.append(w)

                if verbose:
                    print(
                        f"[moe]   -> scored={scored:,}, "
                        f"MAE={payload['mae']:,.0f}s, "
                        f"RMSE={payload['rmse']:,.0f}s"
                    )

            except Exception as e:
                if verbose:
                    print(f"[moe]   -> FAILED: {e}")
                bin_summaries.append(
                    {
                        "bin": bin_name,
                        "rows": len(bin_rows),
                        "scored": 0,
                        "mae": None,
                        "rmse": None,
                        "error": str(e),
                    }
                )

        if total_scored == 0:
            raise ValueError("No bins produced scored predictions.")

        # Compute weighted global metrics
        weighted_mae = (
            sum(b["mae"] * b["scored"] for b in bin_summaries if b["mae"] is not None)
            / total_scored
        )

        weighted_rmse = (
            sum((b["rmse"] ** 2) * b["scored"] for b in bin_summaries if b["rmse"] is not None)
            / total_scored
        ) ** 0.5

        global_metrics = {"mae": weighted_mae, "rmse": weighted_rmse}

        summary = {
            "windows_total": len(all_windows),
            "windows_scored": sum(1 for w in all_windows if w.get("status") == "ok"),
            "windows_skipped": sum(1 for w in all_windows if w.get("status") != "ok"),
            "rows_scored": total_scored,
            "bins_total": len(sorted_bins),
            "bins_scored": sum(1 for b in bin_summaries if b["scored"] > 0),
            "power_users": len(power_users),
            "bin_details": bin_summaries,
            "n_windows": self.config.n_windows,
            "test_window_hours": self.config.test_window_hours,
            "training_lookback_days": self.config.training_lookback_days,
        }

        if verbose:
            print(
                f"[moe] Overall: MAE={weighted_mae:,.0f}s, "
                f"RMSE={weighted_rmse:,.0f}s, "
                f"scored={total_scored:,}"
            )

        result: dict[str, Any] = {
            **global_metrics,
            "definitions": resolved_metric_defs,
            "windows": all_windows,
            "summary": summary,
        }
        if capture_artifacts:
            result["_y_true"] = all_y_true
            result["_y_pred"] = all_y_pred
        return result
