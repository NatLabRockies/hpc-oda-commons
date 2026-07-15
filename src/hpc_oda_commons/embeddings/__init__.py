"""Embedding module: serialize job rows to text and embed them for the embedding kNN model."""

from hpc_oda_commons.embeddings.encoders import (
    Encoder,
    EncoderInfo,
    HashingEncoder,
    SentenceTransformerEncoder,
    build_encoder,
)
from hpc_oda_commons.embeddings.runner import embed_table
from hpc_oda_commons.embeddings.serialize import (
    EmbedConfig,
    LeakageError,
    included_fields,
    serialize_row,
    serialize_rows,
)

__all__ = [
    "Encoder",
    "EncoderInfo",
    "HashingEncoder",
    "SentenceTransformerEncoder",
    "build_encoder",
    "embed_table",
    "EmbedConfig",
    "LeakageError",
    "included_fields",
    "serialize_row",
    "serialize_rows",
]
