"""
XGBoost model package: predicts the recipe's target (job runtime or power).
"""

from __future__ import annotations

from hpc_oda_commons.models.xgboost.model import (
    XGBoostConfig,
    XGBoostModel,
)

__all__ = [
    "XGBoostConfig",
    "XGBoostModel",
]
