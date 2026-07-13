import sys
from pathlib import Path

sys.path.insert(0, "src")

import numpy as np

from hpc_oda_commons.models.job_runtime_faiss.eval import evaluate_offline


def test_evaluate_offline_basic():
    rng = np.random.default_rng(0)
    N = 200
    Q = 5
    d = 32
    corpus = rng.normal(size=(N, d)).astype("float32")
    corpus = corpus / np.linalg.norm(corpus, axis=1, keepdims=True)
    end_times = np.arange(N)
    runtimes = rng.random(size=N) * 100
    queries = rng.normal(size=(Q, d)).astype("float32")
    queries = queries / np.linalg.norm(queries, axis=1, keepdims=True)
    split_times = np.linspace(0, N - 1, Q)

    preds = evaluate_offline(corpus, end_times, runtimes, queries, split_times, k=3, backend="torch" if False else "numpy")
    assert len(preds) == Q
    # predictions should be numeric or nan
    for p in preds:
        assert isinstance(p, float)
