"""
Canonical regression metric computation for HPC ODA Commons.
"""

from __future__ import annotations

from typing import Any


def compute_regression_metrics(y_true: list[float], y_pred: list[float]) -> dict[str, float]:
    """Compute MAE and RMSE from true and predicted values."""
    if len(y_true) != len(y_pred) or not y_true:
        raise ValueError("y_true and y_pred must be the same non-zero length")
    n = float(len(y_true))
    mae = sum(abs(a - b) for a, b in zip(y_true, y_pred)) / n
    rmse = (sum((a - b) ** 2 for a, b in zip(y_true, y_pred)) / n) ** 0.5
    return {"mae": float(mae), "rmse": float(rmse)}


def compute_regression_metrics_from_defs(
    y_true: list[float], y_pred: list[float], metric_defs: list[dict[str, Any]]
) -> dict[str, float]:
    """Compute metrics specified by metric definition objects (mae, rmse, mape, r2)."""
    base = compute_regression_metrics(y_true, y_pred)
    requested = {str(m.get("name", "")) for m in metric_defs}
    metrics: dict[str, float] = {k: v for k, v in base.items() if k in requested}

    if "mape" in requested:
        denom = [abs(v) for v in y_true if v != 0]
        if not denom:
            raise ValueError("MAPE is undefined when all targets are zero.")
        mape = sum(abs(a - b) / abs(a) for a, b in zip(y_true, y_pred) if a != 0) / len(denom)
        metrics["mape"] = float(mape)

    if "r2" in requested:
        mean = sum(y_true) / float(len(y_true))
        ss_tot = sum((v - mean) ** 2 for v in y_true)
        ss_res = sum((a - b) ** 2 for a, b in zip(y_true, y_pred))
        metrics["r2"] = float(1.0 - ss_res / ss_tot) if ss_tot != 0 else 0.0

    return metrics
