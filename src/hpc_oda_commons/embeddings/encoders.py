"""Text encoders for the embedding module.

Model-agnostic: an ``Encoder`` produces L2-normalized dense vectors from text, plus
metadata for provenance. ``HashingEncoder`` is a deterministic, dependency-free stub
(for tests / offline use — not semantic). ``SentenceTransformerEncoder`` wraps any
HuggingFace sentence-transformers model; its heavy deps are optional and imported
lazily, so this module imports fine without them.
"""

from __future__ import annotations

import hashlib
import importlib.util
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np


@dataclass(frozen=True)
class EncoderInfo:
    """Provenance metadata describing how vectors were produced."""

    model_id: str
    dim: int
    normalize: bool
    pooling: str
    device: str
    dtype: str
    revision: str | None = None


@runtime_checkable
class Encoder(Protocol):
    """Produces an ``(len(texts), dim)`` float32 array of L2-normalized row vectors."""

    info: EncoderInfo

    def encode(self, texts: list[str]) -> np.ndarray: ...


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return (matrix / norms).astype(np.float32, copy=False)


class HashingEncoder:
    """Deterministic feature-hashing stub encoder (no dependencies, not semantic).

    Hashes whitespace tokens into a fixed-width vector, then L2-normalizes. Reproducible
    across machines/runs (stable BLAKE2b hashing). Intended for pipeline validation,
    offline runs, and CI where downloading a real model isn't possible.
    """

    def __init__(self, dim: int = 256) -> None:
        self.info = EncoderInfo(
            model_id="stub.hashing",
            dim=dim,
            normalize=True,
            pooling="hash",
            device="cpu",
            dtype="fp32",
            revision=None,
        )

    def encode(self, texts: list[str]) -> np.ndarray:
        dim = self.info.dim
        out = np.zeros((len(texts), dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for token in text.split():
                h = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                out[i, int.from_bytes(h, "little") % dim] += 1.0
        return _l2_normalize(out)


class SentenceTransformerEncoder:
    """Wraps a HuggingFace sentence-transformers model (optional dependency).

    Requires the ``embed`` extra (``sentence-transformers`` + ``torch``). Uses sdpa
    attention (no flash-attn) so it runs on CPU / CUDA / Apple MPS.
    """

    _DTYPES = {"fp32": "float32", "fp16": "float16", "bf16": "bfloat16"}

    def __init__(
        self,
        model_id: str,
        *,
        device: str = "auto",
        dtype: str = "fp16",
        normalize: bool = True,
        batch_size: int = 32,
        revision: str | None = None,
        trust_remote_code: bool = False,
    ) -> None:
        if importlib.util.find_spec("sentence_transformers") is None:
            raise RuntimeError(
                "Missing optional dependency: sentence-transformers. Install with `.[embed]`."
            )
        import torch
        from sentence_transformers import SentenceTransformer

        resolved = _resolve_device(device)
        torch_dtype = getattr(torch, self._DTYPES.get(dtype, "float16"))
        self._model = SentenceTransformer(
            model_id,
            device=resolved,
            revision=revision,
            trust_remote_code=trust_remote_code,
            model_kwargs={"torch_dtype": torch_dtype, "attn_implementation": "sdpa"},
        )
        self._batch_size = batch_size
        self._normalize = normalize
        self.info = EncoderInfo(
            model_id=model_id,
            dim=int(self._model.get_sentence_embedding_dimension()),
            normalize=normalize,
            pooling="model",
            device=resolved,
            dtype=dtype,
            revision=revision,
        )

    def encode(self, texts: list[str]) -> np.ndarray:
        vecs = self._model.encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=self._normalize,
            show_progress_bar=False,
        )
        return np.asarray(vecs, dtype=np.float32)


def _resolve_device(requested: str) -> str:
    if requested != "auto":
        return requested
    if importlib.util.find_spec("torch") is not None:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
    return "cpu"


def build_encoder(model: str, **kwargs) -> Encoder:
    """Construct an encoder: ``stub`` → HashingEncoder, else a sentence-transformers model."""
    if model in ("stub", "stub.hashing"):
        dim = int(kwargs.get("dim", 256))
        return HashingEncoder(dim=dim)
    return SentenceTransformerEncoder(
        model,
        device=kwargs.get("device", "auto"),
        dtype=kwargs.get("dtype", "fp16"),
        normalize=kwargs.get("normalize", True),
        batch_size=int(kwargs.get("batch_size", 32)),
        revision=kwargs.get("revision"),
        trust_remote_code=bool(kwargs.get("trust_remote_code", False)),
    )
