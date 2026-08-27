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
   `cpu` / `gpu` partition names. The loader rejects leftover `your-…` /
   `/path/to/…` placeholders so a half-filled config can't be run by accident.

2. **Provision the cluster env** under `remote_base/env` (a conda env with this package
   `pip install`ed, plus a CUDA-matched `torch` for the embedding jobs). Everything —
   repo clone, env, data, results — lives under `remote_base`.

3. **Pre-stage the embedding model** into `remote_base/hf/hub` (`HF_HOME=remote_base/hf`).
   Compute nodes typically have no internet, so the embed jobs run with `HF_HUB_OFFLINE=1`
   and load the model from this shared cache. Either download it once on a login node, or
   rsync your local Hugging Face cache entry, e.g.:

   ```bash
   rsync -a --partial ~/.cache/huggingface/hub/models--<org>--<model>/ \
     <host>:<remote_base>/hf/hub/models--<org>--<model>/
   ```

   (`stage` creates `remote_base/hf/hub` for you.) Skip this only if you benchmark with
   `--model stub`, which needs no download.

## Pipeline

```
plan ─▶ slice ─▶ stage (rsync) ─▶ embed (GPU) ─▶ benchmark (CPU) ─▶ collect ─▶ aggregate ─▶ rank
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

Each dataset lands at `<out>/<dataset>/data.parquet` with a `slice.json` beside it recording
the source table, the card window, the effective window, and the row count — windowed
parquets are path-identical whatever window they hold, so the sidecar is what tells a recipe
which one it got.

Each dataset is extended back by default by exactly the shortfall its card leaves against
`matrix.SPLIT`'s `training_lookback_days` — `training_lookback_days - card.train_days`,
which is 120 − 60 = 60 days for every current card. You do not pass anything for the fleet
run; `--extra-lookback-days N` overrides the derived value when you want a different window.
The lower bound moves back by that many days and the test region is untouched, so the run
still scores exactly the rows the card window defines.

Deriving this rather than requiring the flag is deliberate. A slice narrower than the split
asks for is invisible in the results — the earliest rolling windows simply train on less
history and score differently, with nothing in the output saying so (#143, #145).

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

Cells go out in batches of `--chunk-size` (50 by default), one SSH per batch rather than one
per cell, and `submitted.json` is rewritten after **every** batch. A 440-job plan once ran
long enough to be killed partway, and because the manifest was written only at the end it
recorded none of the 187 jobs that had started (#189). If a submit is interrupted now, the
manifest still describes what it did.

To recover, or to top up a plan whose cells were submitted in pieces:

```bash
hpc-oda bench-matrix submit --resume --execute
```

`--resume` asks `sacct` which of the plan's job names already exist and submits only the
rest. It is read-only until `--execute`, so a dry run shows you exactly what it would add.

### 5. Status

```bash
hpc-oda bench-matrix status          # sacct over the submitted jobids
```

### 6. Collect → aggregate → rank

```bash
hpc-oda bench-matrix collect         # rsync runs/ back to <plan-dir>/collected-runs
hpc-oda bench-matrix aggregate       # leaderboard over the collected bundles
hpc-oda bench-matrix rank            # walk-forward choice among each cell's lookback arms
```

Each cell writes a result bundle to `runs/<dataset>/<model>/` under `repo_dir`; `collect`
pulls them back and `aggregate` builds the leaderboard (equivalently, `hpc-oda analyze
--runs <plan-dir>/collected-runs`).

`rank` answers the question `aggregate` cannot: with each model run at several training
lookbacks, which arm does a cell get credited with? Taking the best one by test error would
select on the number being reported, so `rank` chooses each window's arm from strictly
earlier windows and scores it on the current one, and prints the best single arm beside the
policy so the selection bias is visible (#190). It reads the same collected bundles — no
extra compute — and writes `arm-ranking.json` next to the leaderboard.

## Resource tiers

Each dataset's cells get a tier from the row count of the **slice they load** — read from
each `slice.json`, not from the card's own narrower window (`plan.json` records the choice).
Every tier runs on the ordinary `cpu` partition; cells take the whole node, so the tier sets
walltime and the window-worker budget, not cores.

| Tier      | Rows loaded   | Partition | Window workers | Walltime |
| --------- | ------------- | --------- | -------------- | -------- |
| `light`   | < 300 k       | `cpu`     | 32             | 8h       |
| `heavy`   | 300 k – 2 M   | `cpu`     | 16             | 1 day    |
| `extreme` | 2 M – 8 M     | `cpu`     | 4              | 2 days   |
| —         | > 8 M         | *skipped* | —              | —        |

Worker counts fall as datasets grow because each concurrent fit holds its own preprocessed
training set. Two measurements on a 250 GB / 104-core node bound the choice: a 532k-row
slice peaked at 14.5 GB with 52 workers, while a 13.9M-row slice peaked at **110 GB with a
single worker** — 20.6 GB of that just holding the rows as Python objects, leaving a
per-window cost near 90 GB. Those points come from different datasets with different column
cardinalities, so they bound the behaviour rather than fitting a curve; the table is
conservative within them.

**Slices above `MAX_NODE_ROWS` are skipped, not relocated.** At 13.9M rows a cell has no
room for concurrency and needs more than a day of serial work. `plan` reports each skip with
its reason. Raising the limit is a deliberate act, and should follow a measurement.

Embedding jobs run on the `gpu` partition (`fp16`, one GPU) with a per-tier walltime.

### Cores are free; workers are not

Benchmark partitions are allocated whole (`OverSubscribe=EXCLUSIVE`), so a cell holds every
core on its node regardless of `--cpus-per-task`. The scripts therefore request
`--exclusive`, omit a core count entirely, and read the real one at runtime
(`OMP_NUM_THREADS=${SLURM_CPUS_ON_NODE:-1}`). Asking for fewer cores never bought anything —
it just left them idle.

`window_n_jobs` is sized separately, because concurrent per-window fits cost **memory**, not
cores: each holds its own preprocessed training set. That is why the bigger tiers get
*fewer* workers, not more. `mlp`, `tfidf_knn`, and `moe_xgboost` are window-parallel (BLAS
pinned to one thread per worker); Random Forest already parallelizes inside each fit, and
the rest run windows sequentially.

MoE XGBoost was added to that set on measurement: window-parallel finished a 532k-row slice
in 7:52 against 11:36 for estimator-parallel at equal cores, with the two arms' MAE agreeing
to 0.02% — float summation order under threading, per [`known-issues.md`](../known-issues.md)
(#2), not a behavioural difference.

## Benchmark configuration

The generated recipes encode the agreed methodology (see [`methodology.md`](methodology.md)):
rolling split, `n_windows=120`, `test_window_hours=6`, `training_lookback_days=120` — the
card's 90-day window (60 days train + 30 days test) extended 60 days earlier so the earliest
windows have their full lookback, with no capping or sampling. Metrics: `mae`, `rmse` on
`runtime_seconds`.

Two models carry extra split keys, from `matrix.MODEL_SPLIT_OVERRIDES`:

| model | overrides | why |
| --- | --- | --- |
| `job_runtime_xgboost` | `objective: reg:absoluteerror` | fit the metric the leaderboard ranks on (#138) |
| `job_runtime_moe_xgboost` | `objective: reg:absoluteerror`, `enable_power_users: false`, `time_decay_rate: 0.05` | the best measured configuration (#134/#136/#141) |

Both XGBoost variants fit absolute error deliberately: if only the MoE did, its margin over
plain XGBoost would bundle an objective effect that has nothing to do with the mixture.
