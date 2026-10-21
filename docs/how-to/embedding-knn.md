# Embedding-based kNN model

`model.embedding_knn` predicts its recipe's target (job runtime or power) from the *k* nearest
historical jobs in a **precomputed dense embedding space**, under the repo's
rolling-window evaluation. It is the embedding-space counterpart to
`model.tfidf_knn` (which vectorizes text with TF-IDF internally): this
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
table. A source that ships one, such as F-DATA, maps it in its descriptor like any column
(`embedding: { from: embedding }`). The column name is configurable via `embedding_field`.

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

Install the `embed` extra in its own environment. On macOS, torch and XGBoost crash in one
process, and torch changes the backend `backend: auto` picks
([known issues](../known-issues.md#note--on-macos-torch-and-xgboost-crash-in-one-process)).

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
| `microsoft/harrier-oss-v1-0.6b` | **MIT** | **recommended real model** — 1024-d, laptop-scale full runs |
| `nvidia/llama-embed-nemotron-8b` | research/gated | 4096-d max quality; GPU for scale |

**Time:** with harrier, a table of a million distinct jobs takes hours on a laptop;
nemotron-8b needs a GPU node. `--cache-dir` makes runs resumable (embedding is chunk-cached),
so a long run survives interruption.

**De-duplication:** ODA corpora are heavily duplicated on submission-time text: many jobs
serialize to a text some other job already had. `hpc-oda embed` embeds each *distinct* text
once and scatters its vector to every row that produced it, so wall-clock scales with the
number of **unique** texts, not rows. Output is unchanged, and identical jobs
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

The bundled example recipe reads `data/ingested/jobs_parquet/embedded_jobs/data.parquet`, so
embed to that path (or copy the recipe and change its `table_path`):

```bash
hpc-oda embed data/ingested/jobs_parquet/<id>/data.parquet \
  --out data/ingested/jobs_parquet/embedded_jobs/data.parquet --model stub
HPC_ODA_OFFLINE=1 hpc-oda benchmark src/hpc_oda_commons/recipes/job-runtime/embedding_knn_rolling.yml
```

The recipe's `model.id` is `model.embedding_knn` with a rolling split. For a dataset of your
own, `hpc-oda recipes write` writes the embedding model's recipes and prints the embed command
([Benchmark your own data](benchmark-your-data.md)).
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

The [model card](../models/embedding_knn.md) lists every setting and its default; each can be
set under a recipe's `split`. Two need explaining:

- `weighting` — `similarity` (weight by clamped cosine, sum-normalized, uniform fallback when
  all similarities are zero) or `uniform`.
- `sims_block_bytes` — peak bytes for one dense similarity block. Search streams the query in
  blocks sized to this budget, so per-window memory is `block × N_train` instead of
  `N_test × N_train`: the difference between a bounded footprint and an out-of-memory kill on
  large corpora. Neighbor selection is unaffected; similarity values match up to
  floating-point summation order (the reproducibility caveat in
  [known-issues](../known-issues.md)).

## Accuracy

Run this model and `tfidf_knn` through the same rolling harness on your embedded dataset and
compare their MAE and RMSE: accuracy depends on the dataset. The leaderboard and the
[model card](../models/embedding_knn.md) give the benchmark's results. What our experiments on
production data suggest:

- **Use `prose` serialization with `log_target: true`.** It was the strongest configuration
  we tried, and `log_target` helps on heavy-tailed runtimes.
- **Don't append non-linguistic text.** Adding job-script diffs or the `work_dir` path to the
  embedded text made accuracy worse, even though it cut the duplicate rate. A natural-language
  embedder can't read `T300` as a temperature or a run index as a magnitude, so the extra
  tokens dominate the vector and kNN starts matching on them. On real HPC data most duplicate
  jobs are parameter sweeps, differing only in an input file the export doesn't capture. Using
  that signal would take numeric, site-specific feature extraction, not text embedding.
