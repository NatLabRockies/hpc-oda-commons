# Embedding-based kNN runtime model

`model.job_runtime_embedding_knn` predicts `runtime_seconds` from the *k* nearest
historical jobs in a **precomputed dense embedding space**, under the repo's
rolling-window evaluation. It is the embedding-space counterpart to
`model.job_runtime_tfidf_knn` (which vectorizes text with TF-IDF internally): this
model consumes vectors you supply, so it can use any encoder — including neural
sentence embeddings that capture semantics bag-of-words cannot.

## Input: the embedding column

The model reads an `embedding` field from each job row. Prepare a dataset whose
`oda.job.v0.2.0` table carries, alongside the usual columns
(`job_id`, `submit_time`, `start_time`, `end_time`, `runtime_seconds`, …), a dense
embedding column:

- Type: Arrow `FixedSizeList<float32>[D]` (one fixed-width vector per job).
- Content: the encoder output for that job's features/metadata.
- Normalization: the model L2-normalizes by default (`normalize: true`), so inner
  product equals cosine similarity. Pre-normalizing at write time is fine too.

`oda.job.v0.2.0` allows extra columns, so the embedding rides along in the same
table and flows through `decode → normalize → prepare` unchanged. The column name is
configurable via `embedding_field`.

A deterministic synthetic example (with a real `FixedSizeList` embedding column) is
available for testing:

```python
from hpc_oda_commons.datasets.synthetic import generate_tiny_embedded_runtime_dataset
```

## Run a benchmark

Point a rolling recipe at your embedded dataset and run the benchmark offline:

```bash
HPC_ODA_OFFLINE=1 hpc-oda benchmark --recipe src/hpc_oda_commons/recipes/job-runtime/embedding_knn_rolling.yml
```

The recipe's `model.id` is `model.job_runtime_embedding_knn` with a rolling split.
The model is discoverable via `hpc-oda browse --type model`.

## Backends and devices

Search is an exact dense top-k. The engine is selectable; the default is
dependency-free:

| `backend` | Needs | Notes |
|---|---|---|
| `numpy` (fallback) | — | Zero-dependency; already several× faster than sklearn on dense vectors. |
| `torch` | `.[torch]` | CPU (fastest on Apple Silicon in practice), CUDA, or MPS matmul. |
| `faiss` | `.[faiss]` | `IndexFlatIP` on CPU, or CUDA via a separate faiss-gpu build. **No Apple-GPU (MPS) backend.** |

`backend: auto` + `device: auto` pick a valid, fast combination for the host
(`faiss`+`mps` is rejected — use `torch`+`mps` or `faiss`+`cpu`). GPU is not
automatically faster: for modest batch/corpus sizes the transfer overhead can make
CPU faster, so measure before committing to a device.

## Configuration

`JobRuntimeEmbeddingKnnConfig` knobs (also settable under a recipe's `split`):

- `k` — neighbors (default 5).
- `embedding_field` — column name (default `embedding`).
- `weighting` — `similarity` (weight by clamped cosine, sum-normalized, uniform
  fallback when all similarities are zero) or `uniform`.
- `normalize` — L2-normalize embeddings (default true).
- `log_target` — predict in log1p-space and invert (default false).
- `backend` / `device` / `dtype` — engine selection (see above).
- `n_windows`, `test_window_hours`, `training_lookback_days`,
  `submit_time_field`, `end_time_field` — the rolling schedule (shared with the
  other rolling models via `rolling_tabular.split`).

## Accuracy

Whether neural embeddings beat `tfidf_knn` on job metadata is an empirical question —
run both through the same rolling harness on your embedded dataset and compare MAE /
RMSE. This model exists to make that comparison possible.
