# HPC benchmark-matrix runner

Runs the full runtime-prediction benchmark — **every model on every usable dataset** — on
a Slurm cluster. It turns the tracked dataset cards
([`methodology.md`](methodology.md), `datasets/*.card.json`) plus a **local, gitignored**
site config into per-cell Slurm recipes and sbatch scripts, then slices each dataset to
its 90-day window ready to stage to the cluster.

The matrix is **6 models × 21 datasets = 126 benchmark cells**, plus **21 GPU embedding
jobs** (the embedded parquet is reused by `job_runtime_embedding_knn`).

## The tracked / untracked split

Nothing cluster-, site-, or user-specific is ever committed. That split is deliberate:

| Tracked (in the repo)                                   | Local only (gitignored, under `.hpc_oda/`)          |
| ------------------------------------------------------- | --------------------------------------------------- |
| `hpc/site.example.yml` — placeholder config             | `.hpc_oda/hpc-site.yml` — your real cluster values  |
| `hpc/templates/*.sbatch.template` — `{{placeholders}}`  | `.hpc_oda/bench-matrix/<plan>/` — rendered scripts  |
| planner + slicer code, cards, methodology               | windowed parquets, results                          |

The runner reads your local site config and fills the tracked templates at plan time. The
generated scripts (which do contain your paths/account) land under `.hpc_oda/`, which is
gitignored — so real hostnames, accounts, users, and paths stay off the repo.

## One-time setup

1. **Copy the example config and fill it in** (keep it under the gitignored `.hpc_oda/`):

   ```bash
   cp src/hpc_oda_commons/benchmarking/hpc/site.example.yml .hpc_oda/hpc-site.yml
   $EDITOR .hpc_oda/hpc-site.yml
   ```

   Set your ssh alias, username, Slurm account, `remote_base`, conda env prefix, and the
   `cpu` / `bigmem` / `gpu` partition names. The loader rejects leftover `your-…` /
   `/path/to/…` placeholders so a half-filled config can't be run by accident.

2. **Provision the cluster env** under `remote_base/env` (a conda env with this package
   `pip install`ed, plus a CUDA-matched `torch` for the embedding jobs). Everything —
   repo clone, env, data, results — lives under `remote_base`.

## Pipeline

```
plan ─▶ slice ─▶ stage (rsync) ─▶ embed (GPU) ─▶ benchmark (CPU/bigmem) ─▶ collect ─▶ aggregate
└──────── local, this repo ───────┘└──────────────── on the cluster ─────────────────┘
```

### 1. Plan

```bash
hpc-oda bench-matrix plan            # reads cards + .hpc_oda/hpc-site.yml
```

Writes `.hpc_oda/bench-matrix/<plan_id>/`:

- `recipes/<dataset>__<model>.yml` — one benchmark recipe per cell (validated against
  `oda.recipe.v0.1.0`).
- `scripts/bench__<dataset>__<model>.sbatch` — one sbatch per cell.
- `scripts/embed__<dataset>.sbatch` — one GPU embed job per dataset.
- `plan.json` — the full manifest (cells, embeds, tiers, paths) that drives staging and
  submission.

Datasets whose card window is flagged unhealthy are skipped (override with
`--include-unhealthy`).

### 2. Slice

```bash
hpc-oda bench-matrix slice           # slices every healthy dataset to its window
```

Writes `.hpc_oda/bench-matrix/data/windows/<dataset>/data.parquet` from each card's
canonical parquet. The slice keeps every job whose `[submit_time, end_time]` interval
**overlaps** the window — long jobs submitted before `window_start` but ending inside it
are training rows, so dropping them would starve the earliest rolling windows. Pinning the
max `submit_time` to `window_end` also anchors the rolling split to exactly the card's
window. (Sliced row counts run slightly above the card's submit-based `n_rows` for this
reason — expected.)

### 3. Stage

```bash
hpc-oda bench-matrix stage           # rsync windows + plan to the cluster
```

Creates the remote dirs (`logs`, `data/windows`, `data/embeddings`, `runs`, cache) and
rsyncs the sliced windows and the plan (recipes + scripts) under `repo_dir`. Add
`--dry-run` to preview the exact ssh/rsync commands first.

### 4. Submit

```bash
# smoke first: one quick cell on the debug partition, actually submitted
hpc-oda bench-matrix submit --only alcf_djc_theta --only-model baseline \
        --partition debug --time 00:20:00 --execute

# then the full fleet
hpc-oda bench-matrix submit --execute
```

Submits each GPU embed job first, then every benchmark cell; `embedding_knn` cells are
submitted with `--dependency=afterok:<embed_jobid>` for their dataset, so they wait for the
embedding to land. **Dry-run by default** — it prints the `sbatch` commands without
submitting; pass `--execute` to actually submit (it charges the allocation). `--only` /
`--only-model` scope the submission; `--partition` / `--time` override the tier defaults
(sbatch CLI flags win over the script directives) for a quick `debug` smoke. A
`submitted.json` (cell → jobid) is written to the plan dir.

### 5. Status

```bash
hpc-oda bench-matrix status          # sacct over the submitted jobids
```

### 6. Collect → aggregate

```bash
hpc-oda bench-matrix collect         # rsync runs/ back to <plan-dir>/collected-runs
hpc-oda bench-matrix aggregate       # leaderboard over the collected bundles
```

Each cell writes a result bundle to `runs/<dataset>/<model>/` under `repo_dir`; `collect`
pulls them back and `aggregate` builds the leaderboard (equivalently, `hpc-oda analyze
--runs <plan-dir>/collected-runs`).

## Resource tiers

Each dataset's cells get a tier from its 90-day-window row count (`plan.json` records the
choice). Peak memory tracks training-set size because of one-hot + SVD of high-cardinality
text/id columns, so the largest datasets move to the big-memory partition.

| Tier      | Window rows        | Partition | CPUs | Walltime   |
| --------- | ------------------ | --------- | ---- | ---------- |
| `light`   | < 300 k            | `cpu`     | 16   | 8h         |
| `heavy`   | 300 k – 2 M        | `cpu`     | 52   | 1 day      |
| `extreme` | ≥ 2 M              | `bigmem`  | 64   | 2 days     |

Embedding jobs run on the `gpu` partition (`fp16`, one GPU) with a per-tier walltime.

## Benchmark configuration

The generated recipes encode the agreed methodology (see [`methodology.md`](methodology.md)):
rolling split, `n_windows=120`, `test_window_hours=6`, `training_lookback_days=60` — a
90-day slice of 60 days train + 30 days test, with no capping or sampling. Metrics: `mae`,
`rmse` on `runtime_seconds`.
