"""Unit tests for the embedding module (serializer, stub encoder, runner)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pytest

from hpc_oda_commons.embeddings import (
    EmbedConfig,
    HashingEncoder,
    LeakageError,
    embed_table,
    included_fields,
    serialize_row,
)

_ROW = {
    "job_id": 7,
    "name": "train_gnn",
    "partition": "gpu",
    "qos": "normal",
    "account": "matsci",
    "nodes_requested": 4,
    "processors_requested": 128,
    "gpus_requested": 8,
    "wallclock_requested": 7200,
    "submit_time": datetime(2026, 1, 6, 14, 0, tzinfo=timezone.utc),
    "runtime_seconds": 3600.0,
    "end_time": datetime(2026, 1, 6, 15, 0, tzinfo=timezone.utc),
    "state": "COMPLETED",
    "script": "#!/bin/bash\nmodule load foo\nsrun ./a.out",
}


def test_serialize_excludes_target_and_posthoc_fields():
    for fmt in ("prose", "kv"):
        text = serialize_row(_ROW, EmbedConfig(text_format=fmt))
        # submission-time fields present
        assert "gpu" in text and "matsci" in text and "7200" in text
        # target / post-hoc fields absent
        assert "3600" not in text  # runtime_seconds
        assert "COMPLETED" not in text  # state
        assert "15:00" not in text  # end_time


def test_prose_and_kv_differ_but_both_carry_features():
    prose = serialize_row(_ROW, EmbedConfig(text_format="prose"))
    kv = serialize_row(_ROW, EmbedConfig(text_format="kv"))
    assert prose != kv
    assert prose.startswith("An HPC batch job")
    assert "partition: gpu" in kv


def test_submit_time_feature_and_instruction():
    text = serialize_row(_ROW, EmbedConfig(text_format="kv", instruction="Represent this job"))
    assert text.startswith("Instruct: Represent this job\nQuery:")
    assert "Tuesday 14:00" in text  # 2026-01-06 is a Tuesday


def test_extra_columns_included_but_forbidden_rejected():
    text = serialize_row(_ROW, EmbedConfig(extra_text_columns=("script",), extra_char_limit=20))
    assert "module load foo"[:5] in text  # script content folded in (truncated)
    with pytest.raises(LeakageError, match="leak"):
        EmbedConfig(extra_text_columns=("runtime_seconds",))


def test_included_fields_reports_labels():
    labels = included_fields(EmbedConfig(extra_text_columns=("script",)), list(_ROW.keys()))
    assert "partition" in labels and "requested walltime" in labels
    assert "submitted" in labels and "script" in labels
    assert "runtime_seconds" not in labels


def test_hashing_encoder_is_deterministic_and_normalized():
    enc = HashingEncoder(dim=64)
    a = enc.encode(["partition gpu account matsci", "partition cpu"])
    b = enc.encode(["partition gpu account matsci", "partition cpu"])
    assert a.shape == (2, 64)
    assert np.array_equal(a, b)  # deterministic
    assert np.allclose(np.linalg.norm(a, axis=1), 1.0)  # L2-normalized


def test_embed_table_writes_embedding_column_and_manifest(tmp_path):
    import pyarrow as pa

    table = pa.table(
        {
            "job_id": [1, 2, 3],
            "partition": ["gpu", "cpu", "gpu"],
            "account": ["a", "b", "a"],
            "submit_time": [datetime(2026, 1, 1, tzinfo=timezone.utc)] * 3,
            "runtime_seconds": [10.0, 20.0, 30.0],
        }
    )
    src = tmp_path / "in.parquet"
    pq.write_table(table, src)
    out = tmp_path / "out.parquet"

    manifest = embed_table(
        src, out, HashingEncoder(dim=32), EmbedConfig(), cache_dir=tmp_path / "cache"
    )

    result = pq.read_table(out)
    assert "embedding" in result.column_names
    assert result.schema.field("embedding").type.list_size == 32
    assert result.num_rows == 3
    # returned manifest + written provenance file agree
    assert manifest["encoder"]["model_id"] == "stub.hashing"
    assert manifest["embedding_dim"] == 32
    assert manifest["serialization"]["format"] == "prose"
    assert "partition" in manifest["serialization"]["included_fields"]
    mpath = Path(str(out) + ".manifest.json")
    assert mpath.exists()
    assert json.loads(mpath.read_text()) == manifest


class _CountingEncoder:
    """Wraps an encoder to count how many texts are actually pushed through it."""

    def __init__(self, inner):
        self.inner = inner
        self.encoded = 0

    @property
    def info(self):
        return self.inner.info

    def encode(self, texts):
        self.encoded += len(texts)
        return self.inner.encode(texts)


def test_embed_table_embeds_each_unique_text_once(tmp_path):
    import pyarrow as pa

    # 6 rows, 2 distinct submission-time texts (gpu/a vs cpu/b), 3 each.
    table = pa.table(
        {
            "job_id": [1, 2, 3, 4, 5, 6],
            "partition": ["gpu", "cpu", "gpu", "cpu", "gpu", "cpu"],
            "account": ["a", "b", "a", "b", "a", "b"],
            "submit_time": [datetime(2026, 1, 1, tzinfo=timezone.utc)] * 6,
            "runtime_seconds": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        }
    )
    src = tmp_path / "in.parquet"
    pq.write_table(table, src)
    out = tmp_path / "out.parquet"

    enc = _CountingEncoder(HashingEncoder(dim=16))
    manifest = embed_table(src, out, enc, EmbedConfig(), cache_dir=None)

    # duplicates are embedded once: 2 unique texts, not 6 rows
    assert enc.encoded == 2
    assert manifest["row_count"] == 6
    assert manifest["unique_text_count"] == 2
    assert manifest["duplicate_ratio"] == round(1.0 - 2 / 6, 6)

    vecs = pq.read_table(out).column("embedding").to_pylist()
    assert pq.read_table(out).num_rows == 6
    # rows sharing a text share a vector; the two groups differ
    assert vecs[0] == vecs[2] == vecs[4]
    assert vecs[1] == vecs[3] == vecs[5]
    assert vecs[0] != vecs[1]


def test_dedup_output_matches_per_row_reference(tmp_path):
    """Dedup is output-preserving: identical to embedding every row (stub is a pure fn)."""
    import pyarrow as pa

    from hpc_oda_commons.embeddings.serialize import serialize_rows

    table = pa.table(
        {
            "partition": ["gpu", "cpu", "gpu", "gpu", "cpu"],
            "account": ["a", "b", "a", "a", "b"],
            "submit_time": [datetime(2026, 1, 1, tzinfo=timezone.utc)] * 5,
            "runtime_seconds": [1.0] * 5,
        }
    )
    src = tmp_path / "in.parquet"
    pq.write_table(table, src)
    out = tmp_path / "out.parquet"
    embed_table(src, out, HashingEncoder(dim=16), EmbedConfig(), cache_dir=None)

    got = np.array(pq.read_table(out).column("embedding").to_pylist(), dtype=np.float32)
    rows = pq.read_table(src).to_pylist()
    ref = HashingEncoder(dim=16).encode(serialize_rows(rows, EmbedConfig()))
    assert np.array_equal(got, ref)


def test_script_residual_column_must_be_in_extra_text_columns():
    with pytest.raises(ValueError, match="extra_text_columns"):
        EmbedConfig(script_residual_column="script")  # not listed in extra_text_columns


def test_embed_table_script_residual_distinguishes_prose_twins(tmp_path):
    import pyarrow as pa

    # rows 0,1: identical prose, scripts differ by one line -> residual distinguishes them.
    # rows 2,3: identical prose AND identical scripts -> residual empty -> still duplicates.
    common = "#SBATCH -N 4\nmodule load foo\nsrun ./run.sh"
    table = pa.table(
        {
            "partition": ["gpu", "gpu", "cpu", "cpu"],
            "account": ["a", "a", "b", "b"],
            "submit_time": [datetime(2026, 1, 1, tzinfo=timezone.utc)] * 4,
            "script": [
                common + "\nINPUT=a.dat",
                common + "\nINPUT=b.dat",
                "#SBATCH -N 1\nsrun ./x",
                "#SBATCH -N 1\nsrun ./x",
            ],
            "runtime_seconds": [1.0, 2.0, 3.0, 4.0],
        }
    )
    src = tmp_path / "in.parquet"
    pq.write_table(table, src)
    out = tmp_path / "out.parquet"

    cfg = EmbedConfig(extra_text_columns=("script",), script_residual_column="script")
    manifest = embed_table(src, out, HashingEncoder(dim=16), cfg, cache_dir=None)

    vecs = pq.read_table(out).column("embedding").to_pylist()
    assert vecs[0] != vecs[1]  # prose-twins distinguished by their script residual
    assert vecs[2] == vecs[3]  # identical prose + identical script -> identical vector
    assert vecs[0] != vecs[2]
    # 3 unique of 4 rows
    assert manifest["unique_text_count"] == 3
    assert manifest["duplicate_ratio"] == round(1.0 - 3 / 4, 6)
    sr = manifest["serialization"]["script_residual"]
    assert sr["column"] == "script"
    assert sr["sbatch_stripped"] and sr["common_line_stripped"]
    assert sr["empty_residual_rows"] == 2  # rows 2,3


def test_embed_table_cache_resumes(tmp_path):
    import pyarrow as pa

    table = pa.table({"partition": ["gpu"] * 5, "runtime_seconds": [1.0] * 5})
    src = tmp_path / "in.parquet"
    pq.write_table(table, src)
    cache = tmp_path / "cache"
    embed_table(
        src,
        tmp_path / "o1.parquet",
        HashingEncoder(dim=16),
        EmbedConfig(),
        cache_dir=cache,
        chunk_size=2,
    )
    # cache chunks exist; a second run reuses them and produces identical vectors
    v1 = pq.read_table(tmp_path / "o1.parquet").column("embedding").to_pylist()
    embed_table(
        src,
        tmp_path / "o2.parquet",
        HashingEncoder(dim=16),
        EmbedConfig(),
        cache_dir=cache,
        chunk_size=2,
    )
    v2 = pq.read_table(tmp_path / "o2.parquet").column("embedding").to_pylist()
    assert v1 == v2
    assert list(cache.glob("emb-*/chunk_*.npy"))
