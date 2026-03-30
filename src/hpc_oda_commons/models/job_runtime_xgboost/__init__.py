"""
XGBoost model package for job runtime prediction (v0.1).
"""

from __future__ import annotations

from hpc_oda_commons.models.job_runtime_xgboost.model import (
    JobRuntimeXGBoostConfig,
    JobRuntimeXGBoostModel,
)
from hpc_oda_commons.models.job_runtime_xgboost.preprocessing import (
    build_preprocessing_diagnostics,
    detect_categorical_columns,
    profile_categorical_features,
    select_one_hot_config,
    select_svd_components,
    write_preprocessing_diagnostics,
)
from hpc_oda_commons.models.job_runtime_xgboost.split import (
    DailyPreprocessingCache,
    build_hourly_rolling_splits,
    materialize_split_rows,
)

__all__ = [
    "JobRuntimeXGBoostConfig",
    "JobRuntimeXGBoostModel",
    "build_preprocessing_diagnostics",
    "build_hourly_rolling_splits",
    "DailyPreprocessingCache",
    "detect_categorical_columns",
    "materialize_split_rows",
    "profile_categorical_features",
    "select_one_hot_config",
    "select_svd_components",
    "write_preprocessing_diagnostics",
]
