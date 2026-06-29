"""Random Forest model for job runtime prediction with rolling evaluation.

Subclasses the neutral RollingTabularModel base (shared rolling evaluation +
OHE/SVD preprocessing); only the tabular regressor differs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hpc_oda_commons.models.rolling_tabular.base import (
    RollingTabularConfig,
    RollingTabularModel,
)


@dataclass(frozen=True)
class JobRuntimeRandomForestConfig(RollingTabularConfig):
    """Rolling/preprocessing config plus Random Forest hyperparameters."""

    n_estimators: int = 100
    max_depth: int | None = 16
    min_samples_leaf: int = 1
    max_features: str | float = "sqrt"
    n_jobs: int = -1


class JobRuntimeRandomForestModel(RollingTabularModel):
    """Random Forest regressor with rolling evaluation and daily preprocessing cache.

    Public API:
        evaluate(rows, *, verbose=False, metric_defs=None) -> dict
    """

    _evaluate_desc = "rolling/random_forest"
    _log_prefix = "random_forest"

    def __init__(self, config: JobRuntimeRandomForestConfig | None = None) -> None:
        super().__init__(config or JobRuntimeRandomForestConfig())

    def _new_regressor(self, n_train: int) -> Any:
        from sklearn.ensemble import RandomForestRegressor

        _ = n_train  # RandomForest does not size-adapt
        cfg = self.config
        return RandomForestRegressor(
            n_estimators=cfg.n_estimators,
            max_depth=cfg.max_depth,
            min_samples_leaf=cfg.min_samples_leaf,
            max_features=cfg.max_features,
            random_state=cfg.random_state,
            n_jobs=cfg.n_jobs,
        )
