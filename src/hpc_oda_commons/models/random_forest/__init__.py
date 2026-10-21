"""Random Forest model with rolling evaluation: predicts the recipe's target (runtime or power)."""

from hpc_oda_commons.models.random_forest.model import (
    RandomForestConfig,
    RandomForestModel,
)

__all__ = [
    "RandomForestConfig",
    "RandomForestModel",
]
