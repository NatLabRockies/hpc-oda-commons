"""
Shared infrastructure for rolling tabular runtime-prediction models.

Holds the rolling split utilities and the OHE+SVD categorical preprocessing
reused by the XGBoost, Random Forest, and MLP models (and the rolling split
helper used by TF-IDF kNN).
"""

from __future__ import annotations

from hpc_oda_commons.models.rolling_tabular.preprocessing import (
    build_preprocessing_diagnostics,
    detect_categorical_columns,
    profile_categorical_features,
    select_one_hot_config,
    select_svd_components,
    write_preprocessing_diagnostics,
)
from hpc_oda_commons.models.rolling_tabular.split import (
    DailyPreprocessingCache,
    build_rolling_splits,
    materialize_split_rows,
)

__all__ = [
    "DailyPreprocessingCache",
    "build_preprocessing_diagnostics",
    "build_rolling_splits",
    "detect_categorical_columns",
    "materialize_split_rows",
    "profile_categorical_features",
    "select_one_hot_config",
    "select_svd_components",
    "write_preprocessing_diagnostics",
]
