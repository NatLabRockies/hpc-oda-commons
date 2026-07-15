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

## Embedding a dataset (`hpc-oda embed`)

`hpc-oda embed` produces that column: it serializes each job row to text and encodes
it, writing an embedded parquet + a provenance manifest.

```bash
# offline / CI: deterministic stub encoder, no model download
hpc-oda embed data/ingested/jobs_parquet/<id>/data.parquet \
  --out data/ingested/jobs_parquet/<id>_embedded/data.parquet --model stub

# a real model (needs the `embed` extra: pip install -e ".[embed]")
hpc-oda embed <in.parquet> --out <out.parquet> \
  --model microsoft/harrier-oss-v1-0.6b --format prose --cache-dir .hpc_oda/embed-cache
```

**What gets embedded (leakage rule):** only **submission-time** fields — job name,
partition/queue, account, user, requested walltime/nodes/cores/GPUs/memory, science
field, machine, submit time. The target and post-hoc fields (`runtime_seconds`,
`end_time`, `start_time`, state, *actual* usage) are **excluded** and refused if
requested — embedding them would leak the prediction target. Two formats: `prose`
(default) and `kv`.

**Models** (swap via `--model`, all model-agnostic):

| model | license | notes |
|---|---|---|
| `stub` | — | deterministic hashing, no download — offline/CI/pipeline checks (not semantic) |
| `microsoft/harrier-oss-v1-0.6b` | **MIT** | **recommended default** — 1024-d, laptop-scale full runs |
| `nvidia/llama-embed-nemotron-8b` | research/gated | 4096-d max quality; GPU for scale |

**Performance** (measured, this-laptop Apple MPS): harrier ≈ 78 rows/s (prose) → a
full 1M-row table in ~3.5 h; nemotron-8b ≈ 9 rows/s → days locally, i.e. a GPU-node
job. `--cache-dir` makes runs resumable (embedding is chunk-cached), so a long run
survives interruption.

**De-duplication:** ODA corpora are heavily duplicated on submission-time text — on a
representative 60-day production slice, 72% of jobs serialized to a text some other job
already had. `hpc-oda embed` embeds each *distinct* text once and scatters its vector to
every row that produced it, so wall-clock scales with the number of **unique** texts, not
rows (~3.4× fewer forward passes on that slice). Output is unchanged, and identical jobs
get bit-identical vectors (no fp16 batch-order drift). The manifest reports `row_count`,
`unique_text_count`, and `duplicate_ratio`. Note this does **not** remove the duplicate
*vectors* from the kNN corpus, so it is not a fix for cross-backend neighbour-tie
variance (see [Known Issues](../known-issues.md)).

**Internal columns (e.g. job scripts):** name extra text columns in a **local
(gitignored) config**, never on the command line, so sensitive content stays off the
repo — the manifest records column *names* + a corpus fingerprint, never content:

```yaml
# .hpc_oda/embed.yml  (local, gitignored)
extra_text_columns: [script]
extra_char_limit: 2000
```
```bash
hpc-oda embed <in.parquet> --out <out.parquet> --model microsoft/harrier-oss-v1-0.6b --config .hpc_oda/embed.yml
```

Note: appending internal columns (raw job scripts, script *diffs*, or the `work_dir`
path) as embedded text was **measured to degrade accuracy** on real ODA data — see
[Accuracy](#accuracy) below. The capability exists for experimentation, but is **not**
recommended by default; keep the serialization to submission-time prose.

## Run a benchmark

Point a rolling recipe at your embedded dataset and run the benchmark offline:

```bash
HPC_ODA_OFFLINE=1 hpc-oda benchmark src/hpc_oda_commons/recipes/job-runtime/embedding_knn_rolling.yml
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

Run both this model and `tfidf_knn` through the same rolling harness on your embedded
dataset and compare MAE / RMSE — accuracy is dataset-dependent. What we found on a
representative 60-day production slice (~632k SLURM jobs, `microsoft/harrier-oss-v1-0.6b`)
is a useful starting point:

**Recommended default: `prose` serialization with `log_target: true`.** It was the
strongest configuration in every experiment (MAE ≈ 10,600 s), and neural embeddings beat
the tf-idf baseline by ~11–15% MAE on the representative sample. `log_target` alone
improved MAE ~8% (heavy-tailed runtimes).

**What did *not* help: appending non-linguistic text.** Adding job-script diffs or the
`work_dir` path to the embedded text *degraded* accuracy, even though it sharply cut the
serialized-text duplicate rate:

| variant | effect vs prose[log] |
|---|---|
| `work_dir` (whole path) | MAE flat (within noise), **RMSE +6%** |
| `work_dir` tail-residual | MAE +3%, RMSE +5% |
| script diff, on the 111k jobs it targets | **MAE +17% (log) to +46% (non-log), RMSE up to +70%** |

The cause is fundamental: a natural-language embedder can't read `T300` as a temperature
or a run index as a magnitude. The extra path/code tokens dominate the vector and break
the (already good) prose neighbour structure, so kNN starts matching on path/code-token
similarity, which correlates poorly with runtime. On real HPC data most duplicate jobs are
**parameter sweeps** — identical submission and script, differing only in an input file or
directory — so the runtime-determining information lives in file *contents* the export
doesn't capture. Using that signal would require **numeric/structured feature extraction**
(site-specific), not text embedding. Keep the serialization to submission-time prose.
