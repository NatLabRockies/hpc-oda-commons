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

**Signature memorization joins the roster** (`job_runtime_signature_memorizer`, #171). It
predicts the median runtime of jobs whose submit-time features are identical, taken from the
rolling training window — no fitting, no hyperparameters beyond the lookback the split already
fixes. When nothing matches it drops features one at a time, cheapest first by information cost
measured on the training window, and finally falls back to the window median.

It earns a place because it *wins*: on the 2026-08-25 fleet run it beat all six fitted models on
9 of 20 datasets, including both in-house machines. `job_runtime_baseline` — a rolling mean —
is too weak to reveal that, so the benchmark had no honest "trivial but strong" comparator. Its
**exact-match coverage is reported alongside its metrics**, because a memorization score means
little without knowing how often it could match anything.

Adding a model to the roster is a methodology decision, not a side effect of writing one (the
precedent from #134). This one is recorded here deliberately.

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
(`SLICE_HISTORY_DAYS − train_days`) and the earliest rolling windows get their full lookback.
The test region is untouched, so the scored population is exactly the card's.

> **Limitation.** Thirty days of scoring cannot contain an allocation cycle, a semester
> boundary, or more than one maintenance outage. It also cannot be widened in place: the
> evaluation region can only grow backwards into the 60-day training runway, which would leave
> the earliest windows with less history than the 120d arm asks for — the arm would silently
> decay toward whatever history exists, exactly where the extra evidence was wanted.
> Lengthening the evaluation requires re-slicing with a larger history budget (#191).

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

### Training lookback: a benchmark axis, not a fixed parameter (#170)

`training_lookback_days` was 120 for every dataset. Measured, that is the best value for only
**6 of 20**: twelve want *less* history and two want more. The cost of getting it wrong is not
marginal — on `lassen`, XGBoost scores **3,304 at a 10-day lookback against 4,434 at 120**, a
25% swing, and at 10 days it would have beaten the random forest that won that dataset in the
fleet. **The fixed parameter did not just cost accuracy; it decided which model won.**

**Every model runs at every lookback** — `{10d, 30d, 120d}` — so the comparison is about the
model rather than about a parameter we picked. Cost is ~1.6x, not 3x: a short lookback trains
on proportionally less history, so a 10-day arm costs roughly a fifth of a 120-day one.

An earlier design set the value per dataset from the memorization sweep. The full sweep
showed why that is unsafe: the proxy is exact where the effect is large (`lassen` and
`nlr_eagle` both 10d, worth 21% and 18%) and wrong where it is small — on `mit_supercloud` it
picked 1d, which is XGBoost's *worst* arm there (38,410 against 32,301 at 30d). Running the
axis avoids having to trust it at all.

**Choosing a winner per cell is an analysis step, deliberately.** Reporting each model's best
arm by test MAE would select on the test set — a noisier model gets three draws at the same
target, so the leaderboard would reorder by variance rather than by skill. The rule is
**walk-forward selection** (`bench-matrix rank`, #190): for each window past a burn-in the arm
is chosen from strictly earlier windows and scored on the current one. What gets reported is
the error of a *policy* — use whichever lookback has served best so far — which is something an
operator could actually run, and a wrong pick costs what it costs instead of being edited out.
The best single arm on the same windows is reported beside it, so the size of the selection
bias is visible rather than argued about.

Pooling a bundle's per-window values weighted by row count reproduces its global metric
bit-for-bit, so this is arithmetic over files already on disk and costs no compute. An earlier
design split the windows in half — select on the first 60, score on the last 60. That is also
unbiased, but it spends half of an already-short evaluation on selection; walk-forward keeps
~100 of 120 windows instead of 60. That the evaluation is only 30 days long to begin with is a
separate defect, and not one the ranking rule can fix (#191).

**The sweep is a proxy and was validated as one.** It optimises *memorization*, not a fitted
model, so using it to set a model's training window is an inference. Checked on two datasets
whose predictions point in opposite directions — `lassen` (short is better) and
`alcf_djc_theta` (long is better) — XGBoost followed both, and on `lassen` the magnitude
matched closely (25.5% measured against 20.2% predicted). Directions transfer; treat the
magnitudes as indicative.

**Slicing is now decoupled from the lookback.** The slice cuts a fixed span
(`SLICE_HISTORY_DAYS`); a model's lookback selects within it. Previously the extension was
`lookback − train_days`, which meant changing a dataset's lookback required re-slicing it.
A shorter lookback now simply leaves history unused — disk, not correctness. Raising
`SLICE_HISTORY_DAYS` is what enables lookbacks beyond 120 days; it needs a re-slice but does
not invalidate existing results, since a 120-day lookback selects the same rows regardless of
how much extra history the file holds.

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

## Calibrating the numbers: the error ceiling

A leaderboard MAE is uninterpretable alone. 11,731 on one machine and 4,006 on another says
nothing about how much accuracy was *available* on either. `hpc-oda datasets ceiling` computes
that bound.

**The claim.** Two jobs whose submit-time features are identical cannot be told apart by any
predictor restricted to those features. So for the feature signature `Z` and metric `M`, the
minimum achievable error over the scored rows is `min_f (1/N) Σ M(y_i, f(z_i))`, which
decomposes per group and has a closed form. **The minimising statistic depends on the metric** —
the median for MAE, the mean for RMSE. Pairing them wrongly costs 17% and 12% respectively on
`nlr_kestrel`, so they are computed as a pair.

This is exact, not an estimate. A signature appearing once contributes zero error, correctly:
a function mapping it to that value exists and is a legitimate predictor. That is what makes
it a bound. It also means floors are **monotone in the fineness of `Z`** and reach zero when
every row is its own group, so the analysis reports the group-size distribution alongside —
without it a floor cannot be judged tight or vacuous.

**Reproducibility.** Unlike every fitted-model metric in this repo, the ceiling is exactly
reproducible across machines: no fitting, no BLAS, no thread-order summation. It is not
subject to the caveat in [`known-issues.md`](../known-issues.md).

**What it revealed.** Across the 20 benchmark datasets the best model captures a median **75%**
of the available headroom, and the ordering inverts the raw leaderboard — `pwa_hpc2n` looks
mediocre at MAE 5,821 but has captured 94%, while `nlr_kestrel` sits last at 51%. Alongside the
bound, the tool measures *causal memorization* — predict from same-signature jobs that finished
earlier — which is a deployable strategy rather than a bound, and which beats all six fitted
models on 9 of 20 datasets (#171). Sweeping its lookback also showed the fixed
`training_lookback_days: 120` is optimal for only 6 of 20 datasets (#170).

Per-dataset results are tracked as `datasets/<dataset>.ceiling.json`, with a cross-dataset
summary in [`ceilings.md`](ceilings.md).

**Deliberately not included:** leave-one-out. It is neither the floor (the optimal function has
no "leave out" in its definition) nor achievable (a row's peers include jobs that ran *after*
it, so it is not causal), so it answers neither question.

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
