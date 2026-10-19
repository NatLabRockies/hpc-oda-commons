# UoPC — reproducing the paper inside the Commons

This records how the Commons reproduces UoPC, a user-based online framework that predicts a
job's power draw (Antici, Borghesi, Domke, Kiziltan, *ISC High Performance 2025*,
[doi:10.23919/ISC.2025.11017729](https://doi.org/10.23919/ISC.2025.11017729); code at
[francescoantici/UoPC](https://github.com/francescoantici/UoPC)), what it measured, and how
far the numbers can be trusted. Tracking issue:
[#125](https://github.com/NatLabRockies/hpc-oda-commons/issues/125).

> **Audit pending corrections.** [UoPC audit](uopc-audit.md) checks this page against the full
> paper and the authors' code. Some statements here are wrong, chiefly what it attributes to
> "the authors' code". They are being corrected under
> [#222](https://github.com/NatLabRockies/hpc-oda-commons/issues/222).

Job-power prediction is outside the runtime benchmark ([methodology](methodology.md)); this
is a one-model study, not a leaderboard.

## Two protocols, one model

`model.job_power_uopc` runs either protocol, chosen by the recipe's `split.method`:

| | `fixed` — the Commons adaptation | `cutoff` — the paper protocol |
|---|---|---|
| Recipe | `job-runtime/uopc_maxpcon.yml` | `job-power/uopc_paper_reproduction.yml`, `uopc_paper_sensitivity.yml` |
| Target | `maxpcon` (W, whole job) | `avgpcon` **and** `maxpcon` divided by allocated nodes |
| Features | job name (label-encoded), cores and nodes requested | F-DATA's job `embedding` plus z-scored cores, nodes and CPU frequency requested |
| Predictor | kNN regressor (mean of the k neighbours) | kNN **classifier** on rounded targets (majority vote), as the authors' code does |
| Test set | last 20% of jobs by end time | every job submitted on or after `test_start` |
| History for a test job | every earlier job by that user, by end time | that user's jobs that **finished before it was submitted** |
| Context | newest `theta` = 50 | newest `theta` = 500 |
| Data | a hand-placed raw Fugaku file | `dataset.job_power.fdata_fugaku_uopc` via `datasets prepare` |

The adaptation is unchanged by this work; the paper protocol is new. A third mode,
`split.method: rolling`, scores the same paper model on the shared rolling windows next to
every other model ([Power prediction benchmark](power.md)). That mode reads the prepared
`avgpcon_per_node`/`maxpcon_per_node` columns, per requested node, like every other model.
The paper protocol computes its own targets per allocated node (`nnuma`), as the paper does,
so the two modes' numbers are not on the same target
([why](../known-issues.md#note--f-datas-allocated-node-counts-can-be-padded)).

## Running it

```bash
# ~3.9 GB: the five F-DATA monthly files for Dec 2023 - Apr 2024
hpc-oda datasets prepare src/hpc_oda_commons/datasets/descriptors/job-power/fdata_fugaku_uopc.yml

hpc-oda benchmark src/hpc_oda_commons/recipes/job-power/uopc_paper_reproduction.yml
hpc-oda benchmark src/hpc_oda_commons/recipes/job-power/uopc_paper_sensitivity.yml
```

The reproduction writes `predictions.parquet`: one row per scored job with both targets'
truth and prediction, the two baselines' predictions, and the job's history and context
sizes. `metrics.json` holds both targets' metrics, the baselines and, for the sweep, the
whole θ × k grid with coverage and cold-start counts.

The F-DATA window is a separate dataset from the runtime benchmark's `fdata_fugaku`
(Mar–Sep 2023). They cover different months and must never share a prepared table.

## The protocol in detail

- **Rows.** A job is usable when it has `avgpcon`, `maxpcon`, an `embedding`, submit and end
  times, and at least one allocated node. Targets are watts per allocated node.
- **Test set.** Jobs submitted on or after `test_start` (2024-02-01), scored in submission
  order. Everything before the cutoff serves only as history.
- **History.** For a test job, the same user's jobs whose end time is strictly before its
  submit time — the information a scheduler would actually have. A test job with fewer
  than `k` such jobs is skipped (counted in `rows_skipped`).
- **Context.** The newest `theta` jobs of that history, by end time.
- **Prediction.** A `KNeighborsClassifier(k)` fitted on the context, with targets rounded
  to whole watts as classes, as in the authors' implementation. Average and peak power are
  fitted separately.
- **Baselines.** For the same scored jobs: the mean of the user's whole eligible history
  (per-user mean), and the mean of every job anyone finished before submission (global
  mean). Both use only past information.
- **Sensitivity.** θ ∈ {50, 100, 200, 500, 1000, 2000, 5000} × k ∈ {5, 10, 20, 50}. Each
  test job's neighbours are found once per θ, up to the largest k, and reused for every k.
  A cell scores only jobs with at least k prior jobs, so coverage falls as k grows. Each
  cell also reports a kNN-**regressor** prediction (the mean of the same neighbours) as an
  ablation of the classifier vote. The headline is the classifier at θ = 500, k = 5.

## Known deviations

- **Feature scaling sees the test period.** The numeric features are z-scored over the
  whole usable dataset, test months included, because the authors' code does. It is a
  small look-ahead in the feature scale only (no target leaks), kept so the numbers stay
  comparable with the paper. A deployment would fit the scaling on history alone.
- **Classifier on rounded targets.** Treating watts as classes is how the reference code
  works, not a Commons choice. The regressor ablation in the sweep shows what it costs.
- **Exact values move across machines and code paths.** kNN ties and BLAS differences can
  shift individual predictions ([#2](https://github.com/NatLabRockies/hpc-oda-commons/issues/2)).
  Ties are common here (many jobs have identical features), so even the sweep and the
  reproduction differ by ~0.3 MAPE points at the same θ and k. Compare to within a
  tolerance, not to the last digit.

## What it is measured against

Public sources state UoPC "achieves only a 10% prediction error on more than 700k job data
extracted from Supercomputer Fugaku" (the authors' README). The paper's per-target tables
are behind the IEEE paywall and are **not yet recorded here**. Until they are, the
comparison is with that ~10% figure, read as MAPE on average power per node, and a run
counts as a reproduction if it lands within a few points of it.

## Results

Run on 2026-10-16 on an Apple M3 Max (14 cores, 38 GB) with the bundled recipes, at commit
76f4f0f. The reproduction took 28 minutes (about 1 ms per scored job, single-threaded) and
peaked at ~20 GB resident.

### Paper reproduction (θ = 500, k = 5)

1,591,115 test jobs from 764 users were submitted on or after 2024-02-01. 1,587,516 were
scored; 3,599 (0.23%) were skipped as cold starts, with fewer than k = 5 prior jobs by
their user.

| Target (W per allocated node) | Model | MAE | RMSE | MAPE | R² |
|---|---|---:|---:|---:|---:|
| Average (`avgpcon`) | **UoPC** | **6.36** | **16.14** | **9.93%** | **0.837** |
| | Per-user mean | 11.76 | 19.12 | 60.27% | 0.771 |
| | Global mean | 33.39 | 40.56 | 339.5% | −0.029 |
| Peak (`maxpcon`) | **UoPC** | **6.72** | **17.77** | **10.17%** | **0.826** |
| | Per-user mean | 12.49 | 20.46 | 61.77% | 0.769 |
| | Global mean | 35.34 | 43.19 | 358.1% | −0.030 |

**It reproduces.** 9.9% MAPE on average power (10.2% on peak) matches the public "10%
prediction error". It also agrees with the unsourced figure in the original contribution
(MAPE 10.10%, R² 0.833). Our test set is larger than the paper's "more than 700k jobs".
The paper may filter jobs in a way its public description does not state.

The median absolute percentage error is 2.2%, and 85.5% of jobs are within 10%. The mean
is carried by a tail: the 90th percentile is 22%.

**Cold starts and short histories.** 95.4% of scored jobs had a full θ = 500 context.
Error falls as a user's history grows:

| User's prior jobs | Jobs | UoPC MAPE | Per-user mean MAPE |
|---|---:|---:|---:|
| 5–49 | 13,623 | 24.4% | 34.3% |
| 50–499 | 60,094 | 17.0% | 31.0% |
| 500+ | 1,513,799 | 9.5% | 61.7% |

The per-user mean is worst for the longest histories because it averages a user's whole
history. Heavy users run many kinds of jobs, and UoPC's nearest neighbours separate them.

**Padded allocations.** The paper divides by F-DATA's allocated nodes (`nnuma`), and so does
this protocol. That count can be padded. 136,937 scored jobs (8.6%), all from 11 users,
request 1 node and 48 cores, run on 1 node and draw ~91 W, yet show `nnuma` = 48. Their
target reads ~1.9 W per allocated node, and both the job and its neighbours sit in that
cluster. They are easy to predict, so they flatter R² more than MAPE. Without them:

| Target, excluding the padded jobs | Model | MAE | MAPE | R² |
|---|---|---:|---:|---:|
| Average | UoPC | 6.95 | 10.25% | 0.762 |
| | Per-user mean | 12.03 | 21.79% | 0.673 |
| Peak | UoPC | 7.34 | 10.51% | 0.746 |
| | Per-user mean | 12.81 | 22.56% | 0.669 |

UoPC's MAPE barely moves, so the reproduction stands. The per-user mean's 60% MAPE is
mostly those 1.9 W jobs: one heavier job in a user's history inflates their mean by
several times. The Commons' own power targets divide by requested nodes instead
([#204](https://github.com/NatLabRockies/hpc-oda-commons/issues/204)).

### Sensitivity sweep (θ × k)

The full grid took 2 h 15 min (7 to 51 minutes per θ, the most at θ = 5000) and peaked at
~17 GB resident. Each cell shows MAPE / R² on average power per allocated node.

**Classifier** (the paper's predictor, a majority vote over rounded watts):

| θ \ k | 5 | 10 | 20 | 50 |
|---|---:|---:|---:|---:|
| 50 | 19.49% / 0.769 | 15.92% / 0.771 | 14.74% / 0.769 | 15.09% / 0.751 |
| 100 | 15.39% / 0.800 | 19.32% / 0.790 | 14.03% / 0.780 | 14.07% / 0.771 |
| 200 | 11.12% / 0.824 | 13.76% / 0.817 | 19.14% / 0.803 | 13.60% / 0.783 |
| 500 | 9.65% / 0.840 | 9.56% / 0.848 | 10.74% / 0.841 | 18.92% / 0.812 |
| 1000 | 9.56% / 0.841 | 9.40% / 0.850 | 9.71% / 0.849 | 13.30% / 0.823 |
| 2000 | 9.60% / 0.837 | 9.32% / 0.848 | 9.49% / 0.847 | 10.17% / 0.842 |
| 5000 | 10.01% / 0.816 | 9.68% / 0.829 | 9.81% / 0.826 | 10.27% / 0.824 |

**Regressor** (the mean of the same neighbours, an ablation):

| θ \ k | 5 | 10 | 20 | 50 |
|---|---:|---:|---:|---:|
| 50 | 27.65% / 0.806 | 33.24% / 0.805 | 39.34% / 0.800 | 54.75% / 0.788 |
| 100 | 17.36% / 0.832 | 26.06% / 0.826 | 30.93% / 0.819 | 37.57% / 0.810 |
| 200 | 11.21% / 0.851 | 14.62% / 0.849 | 25.02% / 0.840 | 32.57% / 0.828 |
| 500 | 9.15% / 0.870 | 9.70% / 0.872 | 12.24% / 0.868 | 24.43% / 0.852 |
| 1000 | 9.04% / 0.871 | 9.13% / 0.875 | 9.79% / 0.876 | 13.70% / 0.867 |
| 2000 | 9.06% / 0.873 | 9.02% / 0.878 | 9.22% / 0.881 | 10.62% / 0.880 |
| 5000 | 9.50% / 0.859 | 9.40% / 0.865 | 9.57% / 0.867 | 10.21% / 0.865 |

<details>
<summary>Peak power (maxpcon per allocated node)</summary>

Classifier:

| θ \ k | 5 | 10 | 20 | 50 |
|---|---:|---:|---:|---:|
| 50 | 19.21% / 0.769 | 15.97% / 0.765 | 14.79% / 0.767 | 15.50% / 0.741 |
| 100 | 15.52% / 0.790 | 18.48% / 0.782 | 14.14% / 0.778 | 14.25% / 0.768 |
| 200 | 11.30% / 0.816 | 13.52% / 0.808 | 18.50% / 0.795 | 13.82% / 0.776 |
| 500 | 9.85% / 0.831 | 9.86% / 0.835 | 10.89% / 0.830 | 18.60% / 0.804 |
| 1000 | 9.89% / 0.830 | 9.80% / 0.835 | 9.89% / 0.836 | 12.89% / 0.816 |
| 2000 | 9.78% / 0.829 | 9.72% / 0.834 | 9.75% / 0.833 | 10.30% / 0.832 |
| 5000 | 10.21% / 0.805 | 9.79% / 0.816 | 9.83% / 0.814 | 10.32% / 0.810 |

Regressor:

| θ \ k | 5 | 10 | 20 | 50 |
|---|---:|---:|---:|---:|
| 50 | 28.18% / 0.799 | 34.04% / 0.797 | 40.46% / 0.793 | 55.94% / 0.783 |
| 100 | 17.74% / 0.823 | 26.57% / 0.817 | 31.64% / 0.813 | 38.62% / 0.805 |
| 200 | 11.57% / 0.840 | 15.02% / 0.838 | 25.57% / 0.831 | 33.42% / 0.820 |
| 500 | 9.50% / 0.858 | 10.07% / 0.860 | 12.61% / 0.857 | 24.97% / 0.844 |
| 1000 | 9.45% / 0.860 | 9.54% / 0.863 | 10.20% / 0.865 | 14.09% / 0.858 |
| 2000 | 9.43% / 0.862 | 9.40% / 0.867 | 9.59% / 0.871 | 10.98% / 0.871 |
| 5000 | 9.71% / 0.849 | 9.59% / 0.856 | 9.76% / 0.857 | 10.40% / 0.855 |

</details>

**Coverage.** A cell scores only jobs whose user has at least k prior jobs: 99.77% of test
jobs at k = 5, 99.61% at 10, 99.42% at 20 and 98.92% at 50. Of the 1,591,115 test jobs, 812
have no prior job by their user, and 3,599, 6,133, 9,206 and 17,222 have fewer than 5, 10,
20 and 50. The median user history is 28,779 jobs.

What the grid shows:

- **θ matters more than k.** MAPE falls from 15–19% at θ = 50 to 9.3–10.7% for
  θ = 500–2000 with k ≤ 20. θ = 5000 is slightly worse on every metric: the oldest history hurts more
  than it helps.
- **The paper's θ = 500, k = 5 is close to the best.** The best classifier cell is θ = 2000,
  k = 10 (9.32%, R² 0.848), 0.3 points better.
- **Voting on rounded watts costs R².** The mean of the same neighbours has the higher R²
  in every cell (0.79–0.88 against 0.75–0.85). Its MAPE is lower only with a large θ and
  small k; the best cell overall is the regressor at θ = 2000, k = 10 (9.02%, R² 0.878).
  Elsewhere the regressor's MAPE rises quickly with k, because averaging in one normal job
  ruins a 1.9 W target (see padded allocations above).
- **The classifier spikes at k = θ/10**: 19.5% at (50, 5), 19.3% at (100, 10), 19.1% at
  (200, 20) and 18.9% at (500, 50), with R² smooth across those cells. Re-running the sweep's
  own neighbour search and vote on samples of 20,000 test jobs at θ = 100 puts the whole
  spike on the padded users. Their MAPE is 41% at k = 5, 75% at k = 10 and 26% at k = 20.
  A sample of 120 other users stays at 12.8–13.4% for every k. Why those sizes in
  particular is not established; it comes from the vote over these users' mix of ~2 W and
  normal targets, and does not affect the other users.
- **The headline cell differs from the reproduction run** (9.65% against 9.93% MAPE at
  θ = 500, k = 5) because of exact ties. Many jobs have identical features: in the
  samples above, 30% of queries had all 50 nearest neighbours at distance 0. The sweep takes
  the first k of its 50 nearest neighbours, while the reproduction asks scikit-learn for k
  directly, and the two pick different jobs among equally near ones. Both are valid
  readings of the protocol; the spread between them, ~0.3 points, is the tolerance to
  compare within.

## Should power have its own tracked benchmark?

Yes, but not with this protocol. Per-node power is clearly predictable from a user's
history: R² is 0.84–0.88 and MAPE ~9–10%, well ahead of the per-user mean (0.67–0.77). That
headroom is enough to rank models. But this protocol is UoPC's own: it refits a model per
job against that user's history, which most models in the Commons do not support. A
tracked benchmark should use the shared rolling protocol that every model runs on
([power prediction](power.md), #204), with:

- targets per requested node, because F-DATA's allocated counts are padded;
- average power as the headline, because peak means different things across datasets
  ([power sources](../datasets/power-sources.md));
- this reproduction kept as the UoPC reference result.

Whether to make it a leaderboard track should wait for the rolling results.
