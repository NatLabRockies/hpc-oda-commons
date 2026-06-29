"""
XGBoost model package for job runtime prediction (v0.1).
"""

from __future__ import annotations

from hpc_oda_commons.models.job_runtime_xgboost.model import (
    JobRuntimeXGBoostConfig,
    JobRuntimeXGBoostModel,
)

__all__ = [
    "JobRuntimeXGBoostConfig",
    "JobRuntimeXGBoostModel",
]
