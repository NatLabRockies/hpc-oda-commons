"""TF-IDF + kNN model package for job runtime prediction (v0.1)."""

from hpc_oda_commons.models.job_runtime_tfidf_knn.model import (
    JobRuntimeTfidfKnnConfig,
    JobRuntimeTfidfKnnModel,
)
from hpc_oda_commons.models.job_runtime_tfidf_knn.vectorization import (
    build_text_column,
    detect_text_columns,
)

__all__ = [
    "JobRuntimeTfidfKnnConfig",
    "JobRuntimeTfidfKnnModel",
    "build_text_column",
    "detect_text_columns",
]
