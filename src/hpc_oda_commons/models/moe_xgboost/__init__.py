"""
Mixture-of-Experts XGBoost model: predicts the recipe's target (job runtime or power).

Routes each job to a per-(user, wallclock-bin) XGBoost expert inside the shared
rolling window, with data-derived bin edges, a window-wide fallback expert, and
exponential time-decay sample weighting.
"""

from __future__ import annotations

from hpc_oda_commons.models.moe_xgboost.model import (
    MoEXGBoostConfig,
    MoEXGBoostModel,
)

__all__ = [
    "MoEXGBoostConfig",
    "MoEXGBoostModel",
]
