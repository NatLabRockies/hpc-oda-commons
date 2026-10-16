from __future__ import annotations

from statistics import mean
from typing import Any


class JobRuntimeBaselineModel:
    """
    Deterministic mean-predictor baseline.

    v0.1 behavior:
    - Fit: compute mean(target) on training rows (``runtime_seconds`` by default)
    - Predict: return that constant mean for every row
    """

    def __init__(self, target_field: str = "runtime_seconds") -> None:
        self.target_field = target_field
        self._mean_runtime: float | None = None

    def fit(self, rows: list[dict[str, Any]]) -> None:
        values = [float(r[self.target_field]) for r in rows if r.get(self.target_field) is not None]
        self._mean_runtime = float(mean(values)) if values else 0.0

    def predict(self, rows: list[dict[str, Any]]) -> list[float]:
        if self._mean_runtime is None:
            raise RuntimeError("Model not fitted. Call fit() first.")
        return [self._mean_runtime for _ in rows]
