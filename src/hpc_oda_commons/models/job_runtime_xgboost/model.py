"""
XGBoost model for job runtime prediction with rolling evaluation.

Subclasses the neutral RollingTabularModel base (shared rolling evaluation +
OHE/SVD preprocessing) and supplies the XGBoost regressor and hyperparameters.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Any

from hpc_oda_commons.models.rolling_tabular.base import (
    RollingTabularConfig,
    RollingTabularModel,
)


@dataclass(frozen=True)
class JobRuntimeXGBoostConfig(RollingTabularConfig):
    """Rolling/preprocessing config plus XGBoost hyperparameters."""

    n_estimators: int = 100
    max_depth: int = 8
    learning_rate: float = 0.05
    subsample: float = 0.8
    colsample_bytree: float = 0.8


class JobRuntimeXGBoostModel(RollingTabularModel):
    """
    XGBoost model for job runtime prediction with rolling evaluation.

    Public API:
    - evaluate(): rolling train/test evaluation with daily preprocessing cache
    - build_split_plan(): preview split windows without running evaluation
    - analyze_preprocessing(): profile categorical features and preview OHE/SVD config
    """

    _evaluate_desc = "rolling/xgboost"
    _log_prefix = "xgboost"

    def __init__(self, config: JobRuntimeXGBoostConfig | None = None) -> None:
        super().__init__(config or JobRuntimeXGBoostConfig())

    @staticmethod
    def _check_dependencies() -> None:
        missing: list[str] = []
        for package in ("xgboost", "sklearn"):
            if importlib.util.find_spec(package) is None:
                missing.append(package)
        if missing:
            missing_list = ", ".join(missing)
            raise RuntimeError(
                "Missing optional model dependencies: "
                f'{missing_list}. Install with `pip install -e ".[dev]"`.'
            )

    def _new_regressor(self, n_train: int) -> Any:
        from xgboost import XGBRegressor

        _ = n_train  # XGBoost does not size-adapt; the seam is shared with subclasses

        return XGBRegressor(
            n_estimators=self.config.n_estimators,
            max_depth=self.config.max_depth,
            learning_rate=self.config.learning_rate,
            subsample=self.config.subsample,
            colsample_bytree=self.config.colsample_bytree,
            random_state=self.config.random_state,
            n_jobs=1,
            verbosity=0,
        )
