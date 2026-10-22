# Runtime-prediction benchmark — methodology & decisions

This is the tracked decision log for the runtime-prediction benchmark: every runtime model on
every usable dataset. It records **what we decided and why**, so the benchmark is reproducible
and our choices are explainable. Results are on the
[leaderboard](https://natlabrockies.github.io/hpc-oda-commons/leaderboard/) and the generated
[dataset cards](../../datasets/cards/README.md); each dataset's runtime card
(`<id>.card.json`) and error ceiling are in [`../datasets/`](../datasets/).

## The rules today

- **Models:** the eight in `RUNTIME_MODELS` (`benchmarking/hpc/matrix.py`): baseline, the
  signature memorizer, TF-IDF + kNN, random forest, XGBoost, MoE XGBoost, MLP and
  embedding + kNN. The fleet run left MLP out (below).
- **Datasets:** the 24 registered datasets, less four ([roster](#dataset-roster)): 20.
- **Each dataset's window** is set by its runtime card: 60 days of training and 90 of test,
  with 120 days of history for the longest lookback, shortened where the source is short
  ([configuration](#benchmark-configuration)).
- **What the leaderboard counts** is `RUNTIME_PROTOCOL` (`benchmark/tracks.py`): 120 test
  windows of 6 hours, the last 30 days of each card's test period, at lookbacks of 10, 30 and
  120 days, with the lookback chosen walk-forward past a 20-window burn-in. That is the fleet
  that has run (plan `20260826-231908`, 2026-08-26). The cards and `bench-matrix plan` are
  sized for the whole 90 days (360 windows), which no fleet has run yet
  ([#191](https://github.com/NatLabRockies/hpc-oda-commons/issues/191)); until it does, a run
  planned today shows on `runs.html` only.
- **Headroom** is measured against each dataset's [error ceiling](ceilings.md).

## Models in scope

The roster is `RUNTIME_MODELS`. The embedding model additionally needs a one-time
`hpc-oda embed` pass per dataset, reused across runs. UoPC is a power model, on the
[power track](../power/methodology.md).

**Feature eligibility.** Every model sees only submission-time columns — the allowlist in
`models/feature_policy.py`. This matters for comparability: before it existed, the tabular
models fed on whatever the normalized table carried, including `job_state` (near-perfectly
correlated with the target for `TIMEOUT` jobs), `exit_code`, and the `*_alloc` counts, and the
TF-IDF model put `job_state` straight into its document text. **Any leaderboard number produced
before that fix overstates accuracy by an amount that varies per dataset, so it is not
comparable with numbers produced after it** — re-run rather than mix the two.

**Signature memorization joined the roster** (`signature_memorizer`, #171). It predicts the
median runtime of jobs whose submit-time features are identical, taken from the rolling
training window — no fitting, no hyperparameters beyond the lookback the split already fixes.
When nothing matches it drops features one at a time, cheapest first by information cost
measured on the training window, and finally falls back to the window median. It earned its
place by winning: on the 2026-08-25 fleet run it beat all six fitted models then in the roster
on 9 of 20 datasets. `baseline`, a rolling mean, is too weak to reveal that, so the benchmark
had no honest "trivial but strong" comparator. Its **exact-match coverage is reported alongside
its metrics**, because a memorization score means little without knowing how often it could
match anything.

Adding a model to the roster is a methodology decision, not a side effect of writing one (the
precedent from #134).

**MLP was left out of the fleet run** (`--exclude-model mlp`). It remains in the roster; it was
simply not worth its wall-clock at this scale. It measured clearly uncompetitive on every
dataset it ran on, and it owned the matrix's long tail: in the full run before, its cells were
the only ones killed at the walltime limit (three after 14+ hours) while every other model on
the same dataset finished inside two. Leaving it out is a per-run decision on the command
line, not a change to `RUNTIME_MODELS` (#156).

## Benchmark configuration

| | Declared by the runtime card, planned by `bench-matrix` | Counted on the leaderboard today (`RUNTIME_PROTOCOL`) |
|---|---|---|
| test windows | `test_days × 4`: 360 for a 90-day test period | 120 |
| window length | 6 hours | 6 hours |
| training lookback | 10, 30 and 120 days, each capped at the card's `history_days` | 10, 30 or 120 days |

Each runtime card *defines* a window of `train_days` + `test_days` (60 + 90 by default), and
the test period is what gets scored. Behind it the card declares a **history budget**
(`history_days`, 120 by default): the history the earliest scored window must be able to see.
A slice is extended `history_days − train_days` days earlier than the window's start (60 for a
standard card), so the longest lookback is backed by real data.

> **Both numbers are the card's, not the module's** (#191). One value did not suit every
> source. `atlas_opentrinity` holds 80 days in total, so its 120-day arm was training on ~80
> and reporting itself as 120 — a wrong number rather than a weak one. A card now declares
> what its source can afford, the planner caps that dataset's arms at the budget (so
> `atlas_opentrinity`'s longest arm is `lb50d`), and `bench-matrix` derives `n_windows` from
> `test_days`.

Where a source cannot afford `history_days + test_days`, **the test period is shortened before
the history is**, never below 30 days, and the card records `shortfall: true` alongside what
was requested. Three benchmarked datasets run short: `atlas_opentrinity` (50 days of history
and a 30-day test), `pm100` (120 + 40) and `pwa_ricc` (120 + 30).

`bench-matrix slice` derives the extension per dataset rather than taking it as a flag, so the
slice cannot silently disagree with the split (#143, #145). Each slice carries a `slice.json`
recording the window it actually holds.

**No capping or subsampling of training data.** Each window trains on *all* jobs in its
lookback. Capping or sampling would change results in ways we have not measured. Consequence:
high-rate machines produce large per-window training sets and take hours per model, so the
benchmark runs on a cluster ([HPC runner](../hpc-runner.md)).

### Training lookback: a benchmark axis, not a fixed parameter (#170)

`training_lookback_days` was once 120 for every dataset. The memorization sweep of August 2026
found that the best value for only 6 of 20 datasets: twelve wanted *less* history and two
more. (On the current scored windows it is 5 of 20; see [ceilings](ceilings.md#causal-memorization).)
The cost of getting it wrong was not marginal — on `lassen`, XGBoost scored **3,304 at a
10-day lookback against 4,434 at 120**, a 25% swing, and at 10 days it would have beaten the
random forest that won that dataset in that fleet. **The fixed parameter did not just cost
accuracy; it decided which model won.**

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
~100 of 120 windows instead of 60. That the scored test is only 30 days long is a separate
defect, and not one the ranking rule can fix (#191).

**The sweep is a proxy and was validated as one.** It optimises *memorization*, not a fitted
model, so using it to set a model's training window is an inference. Checked on two datasets
whose predictions point in opposite directions — `lassen` (short is better) and
`alcf_djc_theta` (long is better) — XGBoost followed both, and on `lassen` the magnitude
matched closely (25.5% measured against 20.2% predicted). Directions transfer; treat the
magnitudes as indicative.

What the axis measured, and what the fixed value cost, is written up in
[`lookback.md`](lookback.md).

**Slicing is decoupled from the lookback.** A slice holds the card's whole history budget, and
a model's lookback selects within it. Previously the extension was `lookback − train_days`,
which meant changing a dataset's lookback required re-slicing it. A shorter lookback now
simply leaves history unused — disk, not correctness.

## Window selection

For each dataset we pick **one** window, of the card's training and test days, and justify it.

**Rule:** on the dataset's *healthy span* (submit timestamps, outer 0.1% trimmed to drop
corrupt/epoch-era rows), place the window's **end at 80% of the span** — the mature era, after
ramp-up and before wind-down. We deliberately **do not use the last months** (systems wind down
at end-of-life).

**Health gate (missing-block detection):** a **run of ≥3 consecutive days with volume below
5% of the median daily volume** counts as a *missing block* (sustained downtime or lost
records — indistinguishable from the data, and disqualifying either way). If the anchored
window **overlaps any missing block at all** — even clipping its leading/trailing edge — it is
**shifted to the nearest window of the same size clear of every block**, and the shift is
recorded on the card. If no clear window exists at this size, the window is flagged
**unhealthy** and the dataset is escalated (seek other months / widen the window).

**Pinning.** Once a benchmark has run on a window, `characterize --pin-end <date>` keeps it
there when the table is re-characterized, for example after more data is added. F-DATA's
card is pinned this way (to 2023-09-26) since its power months joined the same dataset (#249).

**Reproducibility:** the whole thing is deterministic — `hpc-oda datasets characterize
<parquet>` regenerates the identical card from the prepared table + these parameters.

Exemplar: [`fresco_stampede1`](../../datasets/cards/fresco_stampede1.md) — healthy span
2013-01-11 → 2018-01-17; window **2016-08-20 → 2017-01-16**, test period from 2016-10-19
(gap-free); the one missing block (2018-01-13→15) sits at the span edge, correctly outside the
window.

## Dataset roster

Base: the 24 registered datasets, all of which carry a runtime target.

**Deduplication — `nlr_eagle` only.** `nlr_eagle` and `nrel_eagle` are the **same physical
machine** (NREL's Eagle), ingested from two sources (NLR's own export and NREL's OEDI
submission) with heavily overlapping years. **Use `nlr_eagle`** (more recent, longer span);
**exclude `nrel_eagle`** from all benchmarks and aggregates — including both would
double-count one machine. `nrel_eagle` stays registered as valid data.

**The window is a target, not a hard cutoff.** A dataset is included if its healthy span
supports a meaningful rolling evaluation, using the largest window that fits, shortened as
[above](#benchmark-configuration) and noted on its card. A dataset is excluded only when its
span is too short to form a 30-day test period, or the data is fundamentally unsuitable:

- **Excluded — too short / unsuitable:** `adastra_mi250` (a deliberately-published ~15-day
  sample; measured ~24 days — shorter than the 30-day test period, and unhealthy) and `ic2`
  (3,599 rows total; cloud tasks, not a machine time-series).
- **Excluded — too large for one node:** `ccin2p3_2024`. It covers Sep–Dec 2024, and its card
  window holds 9,969,424 rows, over the planner's `MAX_NODE_ROWS` of 8M. Its earlier, larger
  version (13.9M rows) peaked at ~110 GB per window worker on a 250 GB node, with a cell over
  24 h, so the planner skips it and lists it in each plan's `skipped`
  ([#150](https://github.com/NatLabRockies/hpc-oda-commons/issues/150)). The card is kept,
  so the dataset is ready if a run has the memory for it
  ([#152](https://github.com/NatLabRockies/hpc-oda-commons/pull/152)).
- **Qualify as-is:** the other 20. Some are *thin* (`atlas_mustang`, `pwa_kit_fh2` — sparse
  rolling windows) or *short* (`atlas_opentrinity`, `pm100`, `pwa_ricc`); all flagged on
  their cards.

Dated notes:

- **2026-08 (#153):** `fdata_fugaku` was re-curated from 3 monthly files (2023-07..09) to 7
  (2023-03..09), because its window had started on the first day of the ingested span and the
  lookback extension returned nothing. Since #249 it is one dataset with its power months
  (Dec 2023–Apr 2024) too, and its runtime card is pinned to the window it ran on.
- Measuring real timestamps reclassified two: `mit_supercloud` was re-included (its "~1 month"
  hint was wrong — measured ~9 months, Jan–Oct 2021, healthy), and `atlas_opentrinity` was
  kept on a shortened window (80 healthy days are worth keeping).

## Calibrating the numbers: the error ceiling

A leaderboard MAE means little without knowing how much accuracy was *available*. Each dataset's
error ceiling — the lowest error a predictor restricted to submit-time features could reach —
is defined, and tabulated per dataset, in [error ceilings](ceilings.md). The leaderboard's
headroom is measured against it, and a cell shows headroom only when the floor, the baseline
and the cell cover the same jobs
([#238](https://github.com/NatLabRockies/hpc-oda-commons/issues/238)). Unlike every fitted-model
metric in this repo, a ceiling is exactly reproducible across machines: no fitting, no BLAS,
no thread-order summation.

## The runtime card

`hpc-oda datasets characterize <parquet>` writes, per dataset, `<stem>.card.json` into
`docs/benchmarking/datasets/`: machine-readable, schema `oda.dataset_card.v0.1.0`.
`bench-matrix`, `recipes write`, `datasets ceiling --card` and the leaderboard read it, and
people read it in the dataset's generated card
([dataset cards](../../datasets/cards/README.md), `hpc-oda datasets cards`).

A card records: identity + provenance (git commit, table sha256); characterization (healthy
span, daily-volume profile, job rate, **missing-block analysis**, per-column cardinality +
missingness, runtime distribution); and the **window decision** (dates, anchor, health
verdict, rationale).

## Reproducing a card

```bash
# from a prepared canonical parquet (data/datasets/<id>/data.parquet):
hpc-oda datasets characterize data/datasets/<id>/data.parquet \
  --dataset-id dataset.<id> --system <System> \
  --descriptor dataset.<id> --out docs/benchmarking/datasets
```

The defaults are the agreed methodology; the [CLI reference](../../reference/cli.md) lists
them (`--anchor`, `--train-days`, `--test-days`, `--history-days`, `--gap-min-days`,
`--gap-floor`), and `--pin-end` keeps a window that has been run on.

## Open items

- Run the fleet on the cards' 90-day test periods, and move `RUNTIME_PROTOCOL` with it
  ([#191](https://github.com/NatLabRockies/hpc-oda-commons/issues/191)).
