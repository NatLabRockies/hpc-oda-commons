"""Random Forest model for job runtime prediction with rolling evaluation.

Reuses the XGBoost package's categorical preprocessing (OHE + SVD) and rolling
split utilities; only the tabular regressor differs.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Any

from hpc_oda_commons.models.job_runtime_xgboost.model import (
    JobRuntimeXGBoostConfig,
    JobRuntimeXGBoostModel,
)


@dataclass(frozen=True)
class JobRuntimeRandomForestConfig:
    """Configuration for the Random Forest runtime prediction model."""

    n_windows: int = 1000
    test_window_hours: int = 6
    training_lookback_days: int = 100
    submit_time_field: str = "submit_time"
    end_time_field: str = "end_time"
    explained_variance_target: float = 0.95
    infrequent_category_fraction: float = 0.001
    min_frequency_floor: int = 2
    target_max_one_hot_width: int = 2048
    max_svd_components: int = 256
    categorical_top_k: int = 10
    random_state: int = 42

    n_estimators: int = 100
    max_depth: int | None = 16
    min_samples_leaf: int = 1
    max_features: str | float = "sqrt"
    n_jobs: int = -1


def _to_xgboost_config(config: JobRuntimeRandomForestConfig) -> JobRuntimeXGBoostConfig:
    return JobRuntimeXGBoostConfig(
        n_windows=config.n_windows,
        test_window_hours=config.test_window_hours,
        training_lookback_days=config.training_lookback_days,
        submit_time_field=config.submit_time_field,
        end_time_field=config.end_time_field,
        explained_variance_target=config.explained_variance_target,
        infrequent_category_fraction=config.infrequent_category_fraction,
        min_frequency_floor=config.min_frequency_floor,
        target_max_one_hot_width=config.target_max_one_hot_width,
        max_svd_components=config.max_svd_components,
        categorical_top_k=config.categorical_top_k,
        random_state=config.random_state,
    )


class JobRuntimeRandomForestModel(JobRuntimeXGBoostModel):
    """Random Forest regressor with rolling evaluation and daily preprocessing cache.

    Public API:
        evaluate(rows, *, verbose=False, metric_defs=None) -> dict
    """

    _evaluate_desc = "rolling/random_forest"
    _log_prefix = "random_forest"

    def __init__(self, config: JobRuntimeRandomForestConfig | None = None) -> None:
        self._rf_config = config or JobRuntimeRandomForestConfig()
        super().__init__(_to_xgboost_config(self._rf_config))

    @staticmethod
    def _check_dependencies() -> None:
        if importlib.util.find_spec("sklearn") is None:
            raise RuntimeError(
                'Missing optional model dependencies: sklearn. Install with `pip install -e ".[dev]"`.'
            )

    def _new_xgb_regressor(self) -> Any:
        from sklearn.ensemble import RandomForestRegressor

        cfg = self._rf_config
        return RandomForestRegressor(
            n_estimators=cfg.n_estimators,
            max_depth=cfg.max_depth,
            min_samples_leaf=cfg.min_samples_leaf,
            max_features=cfg.max_features,
            random_state=cfg.random_state,
            n_jobs=cfg.n_jobs,
        )
