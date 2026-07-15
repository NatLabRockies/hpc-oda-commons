"""Embed an ingested job table: serialize each row, encode to vectors, and write an
embedded parquet (original columns + a ``FixedSizeList<float32>[dim]`` ``embedding``
column) alongside a provenance manifest. Embedding is chunk-cached and resumable."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from hpc_oda_commons.embeddings.encoders import Encoder
from hpc_oda_commons.embeddings.serialize import EmbedConfig, included_fields, serialize_rows

ProgressFn = Callable[[int, int, float], None]


def _dedup_texts(texts: list[str]) -> tuple[list[str], np.ndarray]:
    """Collapse identical serialized texts to a unique set (first-occurrence order).

    Returns ``(unique_texts, inverse)`` where ``unique_texts[inverse[i]] == texts[i]``,
    so ``unique_vecs[inverse]`` scatters one embedding per unique text back to every row
    that produced it. Deterministic: same input order -> same unique order -> same output.
    """
    index_of: dict[str, int] = {}
    unique: list[str] = []
    inverse = np.empty(len(texts), dtype=np.int64)
    for i, text in enumerate(texts):
        j = index_of.get(text)
        if j is None:
            j = len(unique)
            index_of[text] = j
            unique.append(text)
        inverse[i] = j
    return unique, inverse


def _run_signature(encoder: Encoder, config: EmbedConfig, unique_texts: list[str]) -> str:
    # Content-addressed: the cache key digests the *unique* corpus that will be embedded,
    # so a re-run of the same dataset resumes and a different dataset never collides.
    corpus_digest = hashlib.sha256("\n\x00\n".join(unique_texts).encode("utf-8")).hexdigest()[:16]
    key = "|".join(
        [
            encoder.info.model_id,
            str(encoder.info.revision),
            str(encoder.info.dim),
            config.text_format,
            config.format_version,
            ",".join(config.extra_text_columns),
            corpus_digest,
        ]
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _embed_cached(
    encoder: Encoder,
    texts: list[str],
    cache_dir: Path | None,
    signature: str,
    chunk_size: int,
    on_progress: ProgressFn | None,
) -> np.ndarray:
    cdir: Path | None = None
    if cache_dir is not None:
        cdir = Path(cache_dir) / f"emb-{signature}"
        cdir.mkdir(parents=True, exist_ok=True)

    parts: list[np.ndarray] = []
    n = len(texts)
    t0 = time.perf_counter()
    for chunk_index, start in enumerate(range(0, n, chunk_size)):
        end = min(start + chunk_size, n)
        cache_file = cdir / f"chunk_{chunk_index:05d}.npy" if cdir is not None else None
        if cache_file is not None and cache_file.exists():
            parts.append(np.load(cache_file))
        else:
            vecs = np.ascontiguousarray(encoder.encode(texts[start:end]), dtype=np.float32)
            if cache_file is not None:
                np.save(cache_file, vecs)
            parts.append(vecs)
        if on_progress is not None:
            on_progress(end, n, time.perf_counter() - t0)

    if not parts:
        return np.zeros((0, encoder.info.dim), dtype=np.float32)
    return np.vstack(parts)


def embed_table(
    input_path: Path,
    output_path: Path,
    encoder: Encoder,
    config: EmbedConfig,
    *,
    cache_dir: Path | None = None,
    chunk_size: int = 1000,
    on_progress: ProgressFn | None = None,
) -> dict:
    """Embed ``input_path`` and write ``output_path`` + ``<output>.manifest.json``.

    Returns the provenance manifest dict.
    """
    table = pq.read_table(input_path)
    columns = table.column_names
    if table.num_rows == 0:
        raise ValueError("input table is empty")
    if "embedding" in columns:
        raise ValueError("input table already has an 'embedding' column")
    missing = [c for c in config.extra_text_columns if c not in columns]
    if missing:
        raise ValueError(f"extra_text_columns not present in table: {missing}")

    rows = table.to_pylist()
    texts = serialize_rows(rows, config)
    # Embed each distinct text once, then scatter its vector to every row that produced
    # it. Real ODA corpora are heavily duplicated on submission-time text, so this is a
    # large speedup; it also makes identical jobs bit-identical (no fp16 batch drift).
    unique_texts, inverse = _dedup_texts(texts)
    signature = _run_signature(encoder, config, unique_texts)
    unique_vecs = _embed_cached(
        encoder, unique_texts, cache_dir, signature, chunk_size, on_progress
    )
    vecs = unique_vecs[inverse]

    dim = encoder.info.dim
    flat = pa.array(vecs.reshape(-1), type=pa.float32())
    embedding = pa.FixedSizeListArray.from_arrays(flat, dim)
    out_table = table.append_column("embedding", embedding)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(out_table, output_path)

    manifest = _build_manifest(
        encoder, config, columns, texts, len(rows), len(unique_texts), dim, output_path
    )
    manifest_path = output_path.with_suffix(output_path.suffix + ".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def _build_manifest(
    encoder: Encoder,
    config: EmbedConfig,
    columns: list[str],
    texts: list[str],
    n_rows: int,
    n_unique: int,
    dim: int,
    output_path: Path,
) -> dict:
    # Fingerprint the serialized corpus (a one-way digest — records *what* was embedded,
    # including any internal extra columns, without storing their content).
    fingerprint = hashlib.sha256("\n\x00\n".join(texts).encode("utf-8")).hexdigest()
    return {
        "schema_version": "oda.embedding.v0.1.0",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "encoder": {
            "model_id": encoder.info.model_id,
            "revision": encoder.info.revision,
            "dim": dim,
            "pooling": encoder.info.pooling,
            "normalize": encoder.info.normalize,
            "device": encoder.info.device,
            "dtype": encoder.info.dtype,
        },
        "serialization": {
            "format": config.text_format,
            "format_version": config.format_version,
            "included_fields": included_fields(config, columns),
            "extra_text_columns": list(config.extra_text_columns),
            "instruction": config.instruction,
        },
        "text_fingerprint": fingerprint,
        "row_count": n_rows,
        "unique_text_count": n_unique,
        "duplicate_ratio": round(1.0 - n_unique / n_rows, 6) if n_rows else 0.0,
        "embedding_column": "embedding",
        "embedding_dim": dim,
        "output": str(output_path),
    }
