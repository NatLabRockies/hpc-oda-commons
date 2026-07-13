from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Optional imports
try:
    import faiss
except Exception:
    faiss = None

try:
    import torch
except Exception:
    torch = None

from hpc_oda_commons.utils import hardware


def _ensure_float32(x: np.ndarray) -> np.ndarray:
    return x.astype("float32", copy=False)


def search_exact_torch(corpus: np.ndarray, queries: np.ndarray, k: int, device: str = "cpu") -> Tuple[np.ndarray, np.ndarray]:
    """Exact top-k using torch matmul. Returns (scores, indices).

    corpus: (N, d) numpy
    queries: (Q, d) numpy
    """
    if torch is None:
        raise RuntimeError("torch is required for torch matmul path")
    dev = torch.device(device)
    corpus_t = torch.from_numpy(_ensure_float32(corpus)).to(dev)
    queries_t = torch.from_numpy(_ensure_float32(queries)).to(dev)
    # compute inner products
    sims = queries_t @ corpus_t.T
    vals, idx = torch.topk(sims, k=min(k, corpus.shape[0]), dim=-1)
    return vals.cpu().numpy(), idx.cpu().numpy()


def search_exact_faiss(corpus: np.ndarray, queries: np.ndarray, k: int, use_gpu: bool = False) -> Tuple[np.ndarray, np.ndarray]:
    """Exact top-k using FAISS IndexFlatIP. Builds an index on the provided corpus slice.

    This builds an in-memory flat index per call; suitable for offline evaluation and small prefixes.
    """
    if faiss is None:
        raise RuntimeError("faiss is not installed")

    d = int(corpus.shape[1])
    index = faiss.IndexFlatIP(d)
    if use_gpu:
        # try to move to GPU
        try:
            res = faiss.StandardGpuResources()
            index = faiss.index_cpu_to_gpu(res, 0, index)
        except Exception:
            pass

    index.add(_ensure_float32(corpus))
    D, I = index.search(_ensure_float32(queries), min(k, corpus.shape[0]))
    return D, I


def evaluate_offline(
    corpus_embeddings: np.ndarray,
    corpus_end_times: np.ndarray,
    corpus_runtimes: np.ndarray,
    query_embeddings: np.ndarray,
    query_split_times: np.ndarray,
    k: int = 5,
    backend: str = "auto",
    device: Optional[str] = None,
) -> List[float]:
    """Run offline exact k-NN evaluation with temporal rolling-window.

    For each query i, use corpus rows with end_time < query_split_times[i].
    Returns list of predicted runtimes (float) per query.
    """
    N, d = corpus_embeddings.shape
    Q = query_embeddings.shape[0]
    # sort corpus by end_time ascending
    order = np.argsort(corpus_end_times)
    corpus_embeddings = corpus_embeddings[order]
    corpus_end_times = corpus_end_times[order]
    corpus_runtimes = corpus_runtimes[order]

    # decide backend
    hw = hardware.detect_hardware()
    # optionally write hardware config for reproducibility
    try:
        # write to repo root for traceability
        repo_root = Path(os.getcwd())
        hardware.write_yaml(repo_root / ".hpc_oda_hardware.yaml", hw)
        hardware.write_env_file(repo_root / ".hpc_oda_hardware.env", hw)
    except Exception:
        pass
    chosen_backend = backend
    if backend == "auto":
        if faiss is not None and hw.get("summary", {}).get("has_cuda"):
            chosen_backend = "faiss_gpu"
        elif faiss is not None:
            chosen_backend = "faiss_cpu"
        elif torch is not None:
            chosen_backend = "torch"
        else:
            chosen_backend = "numpy"

    preds: List[float] = []

    # Group queries by split time to avoid repeated work
    # For simplicity, process queries in order given
    for i in range(Q):
        q = query_embeddings[i : i + 1]
        split = query_split_times[i]
        # find prefix length p where end_time < split
        p = int(np.searchsorted(corpus_end_times, split, side="left"))
        if p == 0:
            preds.append(float("nan"))
            continue

        corpus_prefix = corpus_embeddings[:p]
        runtimes_prefix = corpus_runtimes[:p]

        if chosen_backend.startswith("faiss"):
            use_gpu = chosen_backend.endswith("gpu")
            D, I = search_exact_faiss(corpus_prefix, q, k=k, use_gpu=use_gpu)
            sims = D[0]
            inds = I[0]
        elif chosen_backend == "torch":
            dev = device or ("cuda" if hw.get("summary", {}).get("has_cuda") else "cpu")
            vals, idx = search_exact_torch(corpus_prefix, q, k=k, device=dev)
            sims = vals[0]
            inds = idx[0]
        else:
            # numpy fallback
            sims = (q @ corpus_prefix.T)[0]
            inds = np.argsort(-sims)[:k]
            sims = sims[inds]

        # apply weighting: original repo used weight = max(1, (d-0.9)*100) assuming similarity in [0,1]
        # Ensure sim is in similarity convention (higher=closer)
        weights = np.maximum(1.0, (sims - 0.9) * 100.0)
        # handle NaN or empty
        if len(inds) == 0:
            preds.append(float("nan"))
            continue

        neighbor_runtimes = runtimes_prefix[inds]
        pred = float(np.sum(weights * neighbor_runtimes) / np.sum(weights))
        preds.append(pred)

    return preds


def smoke_test() -> None:
    """Basic smoke test: random small corpus and queries."""
    import time

    rng = np.random.default_rng(42)
    N = 1000
    Q = 10
    d = 64
    corpus = rng.normal(size=(N, d)).astype("float32")
    # L2-normalize to emulate cosine embeddings
    corpus = corpus / np.linalg.norm(corpus, axis=1, keepdims=True)
    end_times = np.sort(rng.integers(1, 10000, size=N))
    runtimes = rng.random(size=N) * 100

    queries = rng.normal(size=(Q, d)).astype("float32")
    queries = queries / np.linalg.norm(queries, axis=1, keepdims=True)
    split_times = np.linspace(end_times.min(), end_times.max(), Q)

    t0 = time.time()
    preds = evaluate_offline(corpus, end_times, runtimes, queries, split_times, k=5, backend="auto")
    t1 = time.time()
    print(f"smoke_test preds: {preds}")
    print(f"elapsed {t1-t0:.3f}s")


if __name__ == "__main__":
    smoke_test()
