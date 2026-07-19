"""Unit tests for the embedding-based kNN runtime model."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone

import numpy as np
import pyarrow.parquet as pq
import pytest

from hpc_oda_commons.datasets.synthetic import generate_tiny_embedded_runtime_dataset
from hpc_oda_commons.models.job_runtime_embedding_knn.backends import make_topk, resolve_backend
from hpc_oda_commons.models.job_runtime_embedding_knn.model import (
    JobRuntimeEmbeddingKnnConfig,
    JobRuntimeEmbeddingKnnModel,
)

_HAS_TORCH = importlib.util.find_spec("torch") is not None
_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _row(job_id, submit_h, end_h, runtime, embedding):
    submit = _BASE + timedelta(hours=submit_h)
    return {
        "job_id": job_id,
        "submit_time": submit,
        "start_time": submit,
        "end_time": _BASE + timedelta(hours=end_h),
        "runtime_seconds": float(runtime),
        "embedding": [float(x) for x in embedding],
    }


def _embedded_rows(tmp_path):
    table_path, _ = generate_tiny_embedded_runtime_dataset(tmp_path)
    return pq.read_table(table_path).to_pylist()


def test_predicts_clustered_runtime_with_low_error(tmp_path):
    rows = _embedded_rows(tmp_path)
    model = JobRuntimeEmbeddingKnnModel(
        JobRuntimeEmbeddingKnnConfig(
            n_windows=12, test_window_hours=6, training_lookback_days=30, k=3, backend="numpy"
        )
    )
    result = model.evaluate(rows)
    # Neighbors share a cluster's base runtime (+/- small noise), so error is small.
    assert result["mae"] < 100.0
    assert result["summary"]["windows_scored"] >= 1
    assert result["summary"]["rows_scored"] > 0
    assert set(result.keys()) >= {"mae", "rmse", "definitions", "windows", "summary"}


@pytest.mark.skipif(not _HAS_TORCH, reason="torch not installed")
def test_numpy_and_torch_backends_agree(tmp_path):
    rows = _embedded_rows(tmp_path)
    cfg = dict(n_windows=12, test_window_hours=6, training_lookback_days=30, k=3)
    np_res = JobRuntimeEmbeddingKnnModel(
        JobRuntimeEmbeddingKnnConfig(backend="numpy", **cfg)
    ).evaluate(rows)
    torch_res = JobRuntimeEmbeddingKnnModel(
        JobRuntimeEmbeddingKnnConfig(backend="torch", device="cpu", **cfg)
    ).evaluate(rows)
    assert np_res["mae"] == pytest.approx(torch_res["mae"], rel=1e-5)
    assert np_res["rmse"] == pytest.approx(torch_res["rmse"], rel=1e-5)


def test_rolling_window_has_no_future_leakage():
    # Past jobs (cluster P, runtime 1000) finish before the test job; a job that is
    # IDENTICAL to the test job in embedding space (cluster F, runtime 100) finishes
    # AFTER the split. If the model leaked the future, the test job's prediction would
    # be ~100; with a correct end_time < split filter it must come from P (~1000).
    rows = []
    for i in range(5):  # past P jobs: submit 0..4h, end 5..9h
        rows.append(_row(100 + i, submit_h=i, end_h=5 + i, runtime=1000, embedding=[0.0, 1.0]))
    for i in range(2):  # F jobs: similar to T but end at 25h (> split), never eligible
        rows.append(_row(200 + i, submit_h=8 + i, end_h=25 + i, runtime=100, embedding=[1.0, 0.0]))
    # Test job T: latest submit -> defines the single window [20h, 21h); test = {T}.
    rows.append(_row(300, submit_h=20, end_h=20, runtime=100, embedding=[1.0, 0.0]))

    model = JobRuntimeEmbeddingKnnModel(
        JobRuntimeEmbeddingKnnConfig(
            n_windows=1, test_window_hours=1, training_lookback_days=100, k=3, backend="numpy"
        )
    )
    result = model.evaluate(rows, capture_artifacts=True)
    assert result["summary"]["rows_scored"] == 1
    # Prediction must reflect the PAST cluster P (~1000), not the leaked future F (~100).
    assert result["_y_pred"][0] > 500.0


def test_weighting_math():
    model = JobRuntimeEmbeddingKnnModel(JobRuntimeEmbeddingKnnConfig(weighting="similarity"))
    # similarity weights = clamp(sims,0)/sum
    w = model._weights(np.array([[1.0, 0.6]]), 2)
    assert w[0].tolist() == pytest.approx([0.625, 0.375])
    # negative similarities are clamped to zero
    w = model._weights(np.array([[-0.3, 0.8]]), 2)
    assert w[0].tolist() == pytest.approx([0.0, 1.0])
    # all-zero similarity -> uniform fallback
    w = model._weights(np.array([[0.0, 0.0]]), 2)
    assert w[0].tolist() == pytest.approx([0.5, 0.5])
    # uniform weighting ignores similarity
    uni = JobRuntimeEmbeddingKnnModel(JobRuntimeEmbeddingKnnConfig(weighting="uniform"))
    w = uni._weights(np.array([[0.9, 0.1]]), 2)
    assert w[0].tolist() == pytest.approx([0.5, 0.5])


def test_missing_or_ragged_embedding_raises(tmp_path):
    rows = _embedded_rows(tmp_path)
    model = JobRuntimeEmbeddingKnnModel(JobRuntimeEmbeddingKnnConfig(backend="numpy"))
    bad = [{k: v for k, v in r.items() if k != "embedding"} for r in rows]
    with pytest.raises(ValueError, match="embedding"):
        model.evaluate(bad)
    ragged = [dict(r) for r in rows]
    ragged[1]["embedding"] = ragged[1]["embedding"][:-1]
    with pytest.raises(ValueError, match="wrong-length"):
        model.evaluate(ragged)


def test_resolve_backend_rejects_faiss_on_mps():
    with pytest.raises(ValueError, match="faiss has no Apple-GPU"):
        resolve_backend("faiss", "mps")
    # auto on cpu resolves to a real engine
    assert resolve_backend("auto", "cpu") in {"torch", "numpy"}


@pytest.mark.parametrize("backend", ["numpy"] + (["torch"] if _HAS_TORCH else []))
def test_batched_topk_matches_unbatched(backend):
    # Query-dimension batching selects exactly the same neighbors (each query row still
    # sees the full corpus). The similarity *values* match up to floating-point
    # summation order — BLAS uses a different kernel for a small vs large matmul shape,
    # the same caveat documented for fitted models in known-issues #2.
    rng = np.random.default_rng(0)
    corpus = rng.standard_normal((200, 8)).astype(np.float32)
    query = rng.standard_normal((50, 8)).astype(np.float32)
    k = 5

    full = make_topk(backend, "cpu", sims_block_bytes=10**12)  # whole query in one block
    # 2400 bytes / (200 corpus rows * 4) == 3 query rows per block -> ~17 blocks.
    blocked = make_topk(backend, "cpu", sims_block_bytes=200 * 4 * 3)

    sims_full, idx_full = full(query, corpus, k)
    sims_blk, idx_blk = blocked(query, corpus, k)

    np.testing.assert_array_equal(idx_full, idx_blk)  # neighbor selection is exact
    np.testing.assert_allclose(sims_full, sims_blk, rtol=1e-5, atol=1e-5)


def test_sims_block_bytes_preserves_neighbor_selection(tmp_path):
    # A 1-byte budget forces one query row per block; the model output must match the
    # default single-block path up to floating-point rounding (same neighbors, same
    # rows scored), so the memory-bounding fix does not change results meaningfully.
    rows = _embedded_rows(tmp_path)
    cfg = dict(n_windows=12, test_window_hours=6, training_lookback_days=30, k=3, backend="numpy")
    default = JobRuntimeEmbeddingKnnModel(JobRuntimeEmbeddingKnnConfig(**cfg)).evaluate(rows)
    streamed = JobRuntimeEmbeddingKnnModel(
        JobRuntimeEmbeddingKnnConfig(sims_block_bytes=1, **cfg)
    ).evaluate(rows)
    assert default["mae"] == pytest.approx(streamed["mae"], rel=1e-5)
    assert default["rmse"] == pytest.approx(streamed["rmse"], rel=1e-5)
    assert default["summary"]["rows_scored"] == streamed["summary"]["rows_scored"]
