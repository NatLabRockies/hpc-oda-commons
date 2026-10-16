# UoPC — reproducing the paper inside the Commons

This records how the Commons reproduces UoPC, a user-based online framework that predicts a
job's power draw (Antici, Borghesi, Domke, Kiziltan, *ISC High Performance 2025*,
[doi:10.23919/ISC.2025.11017729](https://doi.org/10.23919/ISC.2025.11017729); code at
[francescoantici/UoPC](https://github.com/francescoantici/UoPC)), what it measured, and how
far the numbers can be trusted. Tracking issue:
[#125](https://github.com/NatLabRockies/hpc-oda-commons/issues/125).

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

The adaptation is unchanged by this work; the paper protocol is new.

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
- **Exact values move across machines.** kNN ties and BLAS differences can shift
  individual predictions ([#2](https://github.com/NatLabRockies/hpc-oda-commons/issues/2)),
  so compare to within a tolerance, not to the last digit.

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

<!-- results:sensitivity -->
