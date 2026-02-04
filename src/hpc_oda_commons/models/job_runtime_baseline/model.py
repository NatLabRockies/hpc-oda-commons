from __future__ import annotations

from statistics import mean
from typing import Any


class JobRuntimeBaselineModel:
    """
    Deterministic baseline for runtime prediction.

    v0.1 behavior:
    - Fit: compute mean(runtime_seconds) on training rows
    - Predict: return that constant mean for every row
    """

    def __init__(self) -> None:
        self._mean_runtime: float | None = None

    def fit(self, rows: list[dict[str, Any]]) -> None:
        runtimes = [
            float(r["runtime_seconds"]) for r in rows if r.get("runtime_seconds") is not None
        ]
        self._mean_runtime = float(mean(runtimes)) if runtimes else 0.0

    def predict(self, rows: list[dict[str, Any]]) -> list[float]:
        if self._mean_runtime is None:
            raise RuntimeError("Model not fitted. Call fit() first.")
        return [self._mean_runtime for _ in rows]
