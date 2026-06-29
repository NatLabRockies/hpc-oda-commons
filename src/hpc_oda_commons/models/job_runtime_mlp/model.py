"""Feed-forward neural network (MLP) model for job runtime prediction.

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
class JobRuntimeMlpConfig(RollingTabularConfig):
    """Rolling/preprocessing config plus feed-forward MLP hyperparameters."""

    hidden_layer_sizes: tuple[int, ...] = (128, 64)
    activation: str = "relu"
    alpha: float = 0.0001
    learning_rate_init: float = 0.001
    max_iter: int = 200
    # early_stopping=True activates the validation_fraction / n_iter_no_change
    # group below; without it sklearn ignores validation_fraction entirely.
    early_stopping: bool = True
    validation_fraction: float = 0.1
    n_iter_no_change: int = 10


class JobRuntimeMlpModel(RollingTabularModel):
    """Feed-forward MLP regressor with rolling evaluation and daily preprocessing cache.

    Public API:
        evaluate(rows, *, verbose=False, metric_defs=None) -> dict
    """

    _evaluate_desc = "rolling/mlp"
    _log_prefix = "mlp"

    def __init__(self, config: JobRuntimeMlpConfig | None = None) -> None:
        super().__init__(config or JobRuntimeMlpConfig())

    def _new_regressor(self, n_train: int) -> Any:
        from sklearn.neural_network import MLPRegressor

        cfg = self.config
        # Early stopping carves off a validation split, which sklearn rejects when
        # it would hold fewer than 2 samples. Rolling windows can be small, so fall
        # back to no early stopping when this window's training set is too small.
        use_early_stopping = cfg.early_stopping and int(n_train * cfg.validation_fraction) >= 2
        return MLPRegressor(
            hidden_layer_sizes=cfg.hidden_layer_sizes,
            activation=cfg.activation,
            alpha=cfg.alpha,
            learning_rate_init=cfg.learning_rate_init,
            max_iter=cfg.max_iter,
            early_stopping=use_early_stopping,
            validation_fraction=cfg.validation_fraction,
            n_iter_no_change=cfg.n_iter_no_change,
            random_state=cfg.random_state,
        )
