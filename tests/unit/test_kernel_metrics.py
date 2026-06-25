from __future__ import annotations

from hpc_oda_commons.kernel.metrics import compute_regression_metrics_from_defs


def test_underprediction_ratio_counts_strictly_less_than_actual() -> None:
    y_true = [10.0, 20.0, 30.0, 40.0]
    y_pred = [5.0, 20.0, 35.0, 30.0]
    metric_defs = [
        {"name": "mae", "target": "runtime_seconds"},
        {"name": "rmse", "target": "runtime_seconds"},
        {"name": "underprediction_ratio", "target": "runtime_seconds"},
    ]

    metrics = compute_regression_metrics_from_defs(y_true, y_pred, metric_defs)

    assert metrics["underprediction_ratio"] == 50.0
