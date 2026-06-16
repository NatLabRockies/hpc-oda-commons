"""Feed-forward neural network (MLP) model for job runtime prediction.

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
class JobRuntimeMlpConfig:
    """Configuration for the feed-forward MLP runtime prediction model."""

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

    hidden_layer_sizes: tuple[int, ...] = (128, 64)
    activation: str = "relu"
    alpha: float = 0.0001
    learning_rate_init: float = 0.001
    max_iter: int = 200
    early_stopping: bool = False
    validation_fraction: float = 0.1
    n_iter_no_change: int = 10


def _to_xgboost_config(config: JobRuntimeMlpConfig) -> JobRuntimeXGBoostConfig:
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


class JobRuntimeMlpModel(JobRuntimeXGBoostModel):
    """Feed-forward MLP regressor with rolling evaluation and daily preprocessing cache.

    Public API:
        evaluate(rows, *, verbose=False, metric_defs=None) -> dict
    """

    _evaluate_desc = "rolling/mlp"
    _log_prefix = "mlp"

    def __init__(self, config: JobRuntimeMlpConfig | None = None) -> None:
        self._mlp_config = config or JobRuntimeMlpConfig()
        super().__init__(_to_xgboost_config(self._mlp_config))

    @staticmethod
    def _check_dependencies() -> None:
        if importlib.util.find_spec("sklearn") is None:
            raise RuntimeError(
                'Missing optional model dependencies: sklearn. Install with `pip install -e ".[dev]"`.'
            )

    def _new_xgb_regressor(self) -> Any:
        from sklearn.neural_network import MLPRegressor

        cfg = self._mlp_config
        return MLPRegressor(
            hidden_layer_sizes=cfg.hidden_layer_sizes,
            activation=cfg.activation,
            alpha=cfg.alpha,
            learning_rate_init=cfg.learning_rate_init,
            max_iter=cfg.max_iter,
            early_stopping=cfg.early_stopping,
            validation_fraction=cfg.validation_fraction,
            n_iter_no_change=cfg.n_iter_no_change,
            random_state=cfg.random_state,
        )
