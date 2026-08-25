# Runtime-prediction benchmark — methodology & decisions

This is the tracked decision log for the full runtime-prediction benchmark (all runtime
models × all usable datasets). It records **what we decided and why**, so the benchmark is
reproducible and our choices are explainable. Per-dataset specifics live in the
[dataset cards](datasets/) (`<id>.card.json` + `<id>.md`), which are the single source of
truth consumed by the benchmark runner.

Status: **Phase 1** — characterization + decision records + the `characterize` tool. The
benchmark-matrix runner and the HPC runner are later phases.

## Models in scope

Six runtime-prediction models: `job_runtime_baseline`, `job_runtime_tfidf_knn`,
`job_runtime_random_forest`, `job_runtime_xgboost`, `job_runtime_mlp`,
`job_runtime_embedding_knn`. (`job_power_uopc` is power prediction — out of scope.) The
embedding model additionally requires a one-time `hpc-oda embed` pass per dataset (reused
across runs).

**Feature eligibility.** Every model sees only submission-time columns — the allowlist in
`models/feature_policy.py`. This matters for comparability: before it existed, the tabular
models fed on whatever the normalized table carried, including `job_state` (mapped by 21 of
the 22 prepared datasets, and near-perfectly correlated with the target for `TIMEOUT` jobs),
`exit_code`, and the `*_alloc` counts, and the TF-IDF model put `job_state` straight into its
document text. **Any leaderboard number produced before that fix overstates accuracy by an
amount that varies per dataset, so it is not comparable with numbers produced after it** —
re-run rather than mix the two.

**MLP is excluded from the fleet run** (`--exclude-model mlp`). `job_runtime_mlp` remains a
registered, in-scope model — it is simply not worth its wall-clock at this scale. It has
measured clearly uncompetitive on every dataset we have run it on, and it owns the matrix's
long tail: in the last full run its cells were the only ones killed at the walltime wall
(three of them after 14+ hours) while every other model on the same dataset finished inside
two. Excluding it is a *per-run* decision expressed on the command line, not a change to the
roster in `RUNTIME_MODELS` (#156); a future run that wants it back passes no flag.

## Benchmark configuration

Fixed rolling-window evaluation for every dataset:

| parameter | value | meaning |
|---|---|---|
| `n_windows` | 120 | number of rolling test windows |
| `test_window_hours` | 6 | → 120 × 6h = **30 days of test coverage** |
| `training_lookback_days` | 120 | **120 days of training** per window |

Each dataset card still *defines* a **90-day (3-month) window**: 60 days train + 30 days test,
and that window is what gets scored. The split asks for 120 days of lookback, more history
than the card window holds, so the slice is extended 60 days earlier than `window_start`
(`training_lookback_days − train_days`) and the earliest rolling windows get their full
lookback. The test region is untouched, so the scored population is exactly the card's.

`bench-matrix slice` derives that extension per dataset rather than taking it as a flag, so
the slice cannot silently disagree with the split (#143, #145). Each slice carries a
`slice.json` recording the window it actually holds.

> **Changed in #145**, from 60 days. The earlier value made the lookback exactly equal to the
> card's `train_days`, which needed no slice extension but left the fleet inconsistent with
> the ablation runs and the published reference recipe, both at 120. Numbers produced at 60
> are not comparable with numbers produced at 120.

**No capping or subsampling of training data.** Each window trains on *all* jobs in its
120-day lookback. Rationale: this is the first pass and must be rigorous and interpretable;
capping/sampling would change results in ways we have not measured, so it is out of scope
here. Consequence: high-rate machines produce large per-window training sets and are
multi-hour per model — this benchmark is an **HPC
job** (runner: later phase). Three months is the *minimum* we're confident in; future passes
should use more.

## Window selection

For each dataset we pick **one** 90-day window and justify it.

**Rule:** on the dataset's *healthy span* (submit timestamps, outer 0.1% trimmed to drop
corrupt/epoch-era rows), place the 90-day window's **end at 80% of the span** — the mature
era, after ramp-up and before wind-down. We deliberately **do not use the last 3 months**
(systems wind down at end-of-life).

**Health gate (missing-block detection):** a **run of ≥3 consecutive days with volume below
5% of the median daily volume** counts as a *missing block* (sustained downtime or lost
records — indistinguishable from the data, and disqualifying either way). If the anchored
window **overlaps any missing block at all** — even clipping its leading/trailing edge — it is
**shifted to the nearest 90-day window clear of every block**, and the shift is recorded on
the card. (The ≥3-day rule defines what a block *is*; the window must not touch one, so it
never ends inside the start of an outage.) If no clear window exists at this size, the window
is flagged **unhealthy** and the dataset is escalated (seek other months / widen the window).

**Reproducibility:** the whole thing is deterministic — `hpc-oda datasets characterize
<parquet>` regenerates the identical card from the prepared table + these parameters.

Exemplar: [`fresco_stampede1`](datasets/fresco_stampede1.md) — healthy span 2013-01-11 →
2018-01-17; chosen window **2016-10-19 → 2017-01-16** (gap-free); the one missing block
(2018-01-13→15) sits at the span edge, correctly outside the window.

## Dataset roster

Base: the 23 registered runtime datasets, filtered for this benchmark.

**Deduplication — `nlr_eagle` only.** `nlr_eagle` and `nrel_eagle` are the **same physical
machine** (NREL's Eagle), ingested from two sources (NLR home-lab export vs. NREL's OEDI
submission) with heavily overlapping years. **Use `nlr_eagle`** (more recent, longer span);
**exclude `nrel_eagle`** from all benchmarks and aggregates — including both would
double-count one machine. `nrel_eagle` stays registered as valid data; it is only excluded
from the benchmark roster.

**Targets a 90-day window** (60d train + 30d test) — a *soft* target, not a hard cutoff. A
dataset is included if it has a healthy span that supports a meaningful rolling evaluation,
using the largest window that fits; a span shorter than 90 days is used as-is and the reduced
coverage is noted on the card (its earliest rolling windows get reduced lookback). A dataset is
excluded only when its span is too short to even form the 30-day test period, or the data is
fundamentally unsuitable. Under this:

- **Excluded — too short / unsuitable:** `adastra_mi250` (a deliberately-published ~15-day
  sample; measured ~24 days — shorter than the 30-day test period, and unhealthy) and `ic2`
  (3,599 rows total; cloud tasks, not a machine time-series).
- **Re-curate to 3 months** (data is available; a small curation task): `ccin2p3_2024`
  (currently Dec-2024 only → pull ~3 months from its 12 monthly files).
- **Re-curated (#153):** `fdata_fugaku` went from 3 monthly files (2023-07..09) to 7
  (2023-03..09). Its window had started on the first day of the ingested span, so the
  slice's 60-day lookback extension returned nothing and every rolling window trained on
  less history than the split asks for. The longer span moves the anchored window to
  2023-05-21..2023-08-18 with 81 days behind it, so the extension is now fully backed.
- **Qualify as-is:** the remaining datasets. Some are *thin* (`atlas_mustang`, `pwa_kit_fh2` —
  sparse rolling windows) or *short* (`atlas_opentrinity` — a healthy 80-day span < the 90-day
  target, included with an 80-day window and reduced early-window lookback); all flagged on
  their cards.

Net benchmark roster: ~20 datasets (18 as-is + 2 after re-curation). Each dataset's final
window, health, and any caveats are recorded on its card; measuring real timestamps reclassified
several — **re-included `mit_supercloud`** (its "~1 month" hint was wrong — measured ~9 months,
Jan–Oct 2021, healthy) and **kept `atlas_opentrinity`** on an 80-day window (the 90-day target
is soft, and 80 healthy days are worth keeping).

## The dataset card

`hpc-oda datasets characterize <parquet>` emits, per dataset, into `docs/benchmarking/datasets/`:

- `<stem>.card.json` — machine-readable, schema `oda.dataset_card.v0.1.0`; the benchmark
  runner reads the chosen window from here.
- `<stem>.md` — the human-readable rendering.

A card records: identity + provenance (git commit, table sha256); characterization (healthy
span, daily-volume profile, job rate, **missing-block analysis**, per-column cardinality +
missingness, runtime distribution); and the **window decision** (dates, anchor, health
verdict, rationale). It reuses the existing quality report's missingness definition and adds
the temporal-health analysis that did not previously exist.

## Reproducing a card

```
# from a prepared canonical parquet (data/datasets/<id>/data.parquet):
hpc-oda datasets characterize data/datasets/<id>/data.parquet \
  --dataset-id dataset.job_runtime.<id> --system <System> \
  --descriptor dataset.job_runtime.<id> --out docs/benchmarking/datasets
```

Knobs (defaults are the agreed methodology): `--anchor 0.80`, `--train-days 60`,
`--test-days 30`, `--gap-min-days 3`, `--gap-floor 0.05`.

## Open items / next phases

- Prepare + characterize the remaining datasets (surfaces per-dataset health); re-curate
  `ccin2p3`.
- Benchmark-matrix runner that consumes the cards' windows.
- HPC runner (scheduler + GPU for the `embed` step and the heavy datasets).
