"""
Mixture-of-Experts XGBoost model for job runtime prediction (v0.1).

Routes jobs to specialized per-bin XGBoost models by user identity and
wallclock cluster, with exponential time-decay sample weighting.
"""

from __future__ import annotations

from hpc_oda_commons.models.job_runtime_moe_xgboost.model import (
    MoEXGBoostConfig,
    MoEXGBoostModel,
)

__all__ = [
    "MoEXGBoostConfig",
    "MoEXGBoostModel",
]
