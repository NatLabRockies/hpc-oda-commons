"""Embedding-based kNN model package for job runtime prediction (v0.1)."""

from hpc_oda_commons.models.job_runtime_embedding_knn.model import (
    JobRuntimeEmbeddingKnnConfig,
    JobRuntimeEmbeddingKnnModel,
)

__all__ = [
    "JobRuntimeEmbeddingKnnConfig",
    "JobRuntimeEmbeddingKnnModel",
]
