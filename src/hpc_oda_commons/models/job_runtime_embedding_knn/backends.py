"""Exact top-k search backends for the embedding kNN model.

All backends take already-(optionally-)L2-normalized float arrays and return
``(sims, idx)`` where ``sims`` are inner products (== cosine on normalized input,
higher = closer) and ``idx`` are positions into ``corpus``. Every backend is
*exact*; they differ only in the engine used for the dense matmul + top-k.

The repo's rolling split uses a bounded lookback (a sliding train window, not a
growing prefix), so each window searches a fresh corpus slice — a per-window
batched matmul is the right primitive and no incremental index is needed. FAISS is
offered for CUDA parity but is not required; numpy is the zero-dependency default.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable

import numpy as np

TopK = Callable[[np.ndarray, np.ndarray, int], tuple[np.ndarray, np.ndarray]]

_TORCH_DTYPES = {"fp32": "float32", "fp16": "float16", "bf16": "bfloat16"}


def _has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _faiss_gpu_available() -> bool:
    if not _has("faiss"):
        return False
    import faiss

    try:
        return faiss.get_num_gpus() > 0
    except Exception:
        return False


def resolve_device(requested: str = "auto") -> str:
    """Pick a compute device. ``auto`` prefers CUDA, then Apple MPS, else CPU."""
    if requested != "auto":
        return requested
    if _has("torch"):
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
    return "cpu"


def resolve_backend(requested: str, device: str) -> str:
    """Pick a search backend valid for ``device``.

    Hard rule: FAISS has no Apple-GPU (MPS) build, so ``faiss`` + ``mps`` is
    rejected with a pointer to the working options. ``auto`` prefers the fastest
    exact engine available for the device (measured: torch-CPU > faiss > numpy on
    CPU; on CUDA, faiss-gpu when present).
    """
    if requested != "auto":
        if requested == "faiss" and device == "mps":
            raise ValueError(
                "faiss has no Apple-GPU (MPS) backend; use backend='torch' with "
                "device='mps', or backend='faiss' with device='cpu'."
            )
        if requested == "torch" and not _has("torch"):
            raise RuntimeError("Missing optional dependency: torch. Install with `.[torch]`.")
        if requested == "faiss" and not _has("faiss"):
            raise RuntimeError("Missing optional dependency: faiss. Install with `.[faiss]`.")
        return requested

    if device == "cuda":
        return "faiss" if _faiss_gpu_available() else ("torch" if _has("torch") else "numpy")
    if device == "mps":
        return "torch"  # the only GPU path on Apple Silicon
    # cpu
    if _has("torch"):
        return "torch"
    return "numpy"


def _topk_numpy(query: np.ndarray, corpus: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    sims = query @ corpus.T
    kk = min(k, corpus.shape[0])
    part = np.argpartition(-sims, kk - 1, axis=1)[:, :kk]
    rows = np.arange(sims.shape[0])[:, None]
    order = np.argsort(-sims[rows, part], axis=1)
    idx = part[rows, order]
    return sims[rows, idx], idx


def _make_topk_torch(device: str, dtype: str) -> TopK:
    import torch

    dev = torch.device(device)
    tdtype = getattr(torch, _TORCH_DTYPES.get(dtype, "float32"))

    def _topk(query: np.ndarray, corpus: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
        q = torch.from_numpy(np.ascontiguousarray(query, dtype=np.float32)).to(dev, tdtype)
        c = torch.from_numpy(np.ascontiguousarray(corpus, dtype=np.float32)).to(dev, tdtype)
        sims = q @ c.T
        vals, idx = torch.topk(sims, min(k, corpus.shape[0]), dim=1)
        if device == "mps":
            torch.mps.synchronize()
        return vals.float().cpu().numpy(), idx.cpu().numpy()

    return _topk


def _make_topk_faiss(device: str) -> TopK:
    import faiss

    use_gpu = device == "cuda"

    def _topk(query: np.ndarray, corpus: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
        index = faiss.IndexFlatIP(int(corpus.shape[1]))
        if use_gpu:
            index = faiss.index_cpu_to_gpu(faiss.StandardGpuResources(), 0, index)
        index.add(np.ascontiguousarray(corpus, dtype=np.float32))
        sims, idx = index.search(
            np.ascontiguousarray(query, dtype=np.float32), min(k, corpus.shape[0])
        )
        return sims, idx

    return _topk


def make_topk(backend: str, device: str, dtype: str = "fp32") -> TopK:
    """Return a ``topk(query, corpus, k) -> (sims, idx)`` callable for the backend."""
    if backend == "numpy":
        return _topk_numpy
    if backend == "torch":
        return _make_topk_torch(device, dtype)
    if backend == "faiss":
        return _make_topk_faiss(device)
    raise ValueError(f"Unknown backend: {backend!r} (expected numpy|torch|faiss)")
