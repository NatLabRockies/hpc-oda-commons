"""Embedding-based kNN model package: predicts the recipe's target (job runtime or power)."""

from hpc_oda_commons.models.embedding_knn.model import (
    EmbeddingKnnConfig,
    EmbeddingKnnModel,
)

__all__ = [
    "EmbeddingKnnConfig",
    "EmbeddingKnnModel",
]
