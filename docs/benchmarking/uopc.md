# UoPC — reproducing the paper inside the Commons

This records how the Commons reproduces UoPC, a user-based online framework that predicts a
job's power draw (Antici, Borghesi, Domke, Kiziltan, *ISC High Performance 2025*,
[doi:10.23919/ISC.2025.11017729](https://doi.org/10.23919/ISC.2025.11017729); code at
[francescoantici/UoPC](https://github.com/francescoantici/UoPC)), what it measured, and how
far the numbers can be trusted. Tracking issue:
[#125](https://github.com/NatLabRockies/hpc-oda-commons/issues/125). The
[UoPC audit](uopc-audit.md) checks it against the full paper and the authors' code.

Job-power prediction is outside the runtime benchmark ([methodology](methodology.md)); this
is a one-model study, not a leaderboard.

## Two protocols, one model

`model.job_power_uopc` runs either protocol, chosen by the recipe's `split.method`:

| | `fixed` — the Commons adaptation | `cutoff` — the paper protocol |
|---|---|---|
| Recipe | `job-runtime/uopc_maxpcon.yml` | `job-power/uopc_paper_reproduction.yml`, `uopc_paper_sensitivity.yml` |
| Target | `maxpcon` (W, whole job) | `avgpcon` **and** `maxpcon` divided by allocated nodes |
| Features | job name (label-encoded), cores and nodes requested | F-DATA's job `embedding` plus z-scored cores, nodes and CPU frequency requested (an adaptation; see [Known deviations](#known-deviations)) |
| Predictor | kNN regressor (mean of the k neighbours) | kNN **classifier** (majority vote), as in the authors' tool, on targets rounded to whole watts |
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

- **Features are an adaptation.** The paper describes a job by the string "job name, cores
  requested, nodes requested, requested frequency, environment". It leaves out the user,
  since each model is per-user, and embeds the string with all-MiniLM-L6-v2. The public job
  names are anonymised (`jnam_…`), so that string can't be rebuilt from F-DATA. Instead the
  protocol uses F-DATA's precomputed `embedding` plus cores, nodes and frequency z-scored
  separately.
  - **F-DATA's embedding is the paper's encoder over three fields.** [F-DATA's generation script](https://github.com/francescoantici/F-DATA/blob/main/generation_scripts/generate_derived_features.py) embeds the
    original, unanonymised "user, job name, environment" string with all-MiniLM-L6-v2. So
    it carries the real job name and environment that the public columns hide. It also
    carries the user, which the paper leaves out, but that is constant within UoPC's
    per-user models. It does not change with cores, nodes or frequency, so the protocol
    adds those as numbers.
  - **The z-scoring decides how much each number counts.** One embedding is at most 1.5
    from another, with a median of 0.84 between two job names of one user.
    - Frequency has two values, so its z-scores are at least 2 apart (2.03 here) whatever
      the data. A frequency mismatch therefore outweighs any difference in job name.
    - A few enormous jobs inflate the spread of cores (std. dev. 29,869) and nodes (622).
      So ordinary differences barely count: 48 → 96 cores adds 0.002, and 1 → 16 nodes
      0.024.
    - In practice the neighbours are the user's jobs at the same frequency with the most
      similar job names.
  - The scaling is the Commons' choice (#203); the paper scales nothing. It does hold UoPC
    back: `split.uopc_features: balanced` scores better on every protocol and system tried
    ([Feature modes](#feature-modes)). `balanced` is the model's default since #222. The
    paper-reproduction recipes pin `zscore`, which the results on this page use.
  - **We don't embed F-DATA ourselves.** The paper's string can't be rebuilt from public
    data: the job names and environments are anonymised IDs (`jnam_2111729`), which would
    carry no name meaning and would make unrelated IDs look alike.
- **R² stays below the paper's on its apparent data.** This is a known limitation. Without
  the padded jobs, the best features reach R² 0.766 and 0.753, against the paper's 0.80 and
  0.79. The paper's features rely on the real job names, which public F-DATA doesn't have,
  so the gap may not be closable on public data.
- **Feature scaling sees the test period.** The z-scores use the whole usable dataset,
  test months included: a look-ahead in the feature scale only, with no target leak.
  Fitting on the history before 2024-02-01 instead would barely change anything:
  - frequency's gap would be 2.02 rather than 2.03;
  - the std. devs. of cores and nodes would be about 16% smaller, still negligible next to
    job names.

  A deployment would fit the scaling on history alone.
- **Classifier on rounded targets.** The authors' tool predicts with `KNeighborsClassifier`,
  which accepts only discrete labels. Per-node power isn't whole watts, so it is rounded to
  whole watts first; the rounding is ours. The regressor ablation in the sweep shows what
  voting costs.
- **The paper's data lacks the most padded jobs.** The paper divides by allocated nodes, as
  this protocol does. Its Fig. 4 shows the same small bars at ~11, 15 and 22 W that our
  test period has per allocated node, from jobs allocated 4–8× the nodes they requested.
  But its lowest bar is ~11 W. Our test period has 150,015 jobs below 5 W: 139,074 with
  1 node requested and `nnuma` = 48, and 10,941 at 24×. So this protocol scores ~150k jobs
  (9.4%) the paper apparently did not. The [unpadded variant](#variants-padded-jobs-and-node-count)
  drops them.
- **Exact values move across machines and code paths.** kNN ties and BLAS differences can
  shift individual predictions ([#2](https://github.com/NatLabRockies/hpc-oda-commons/issues/2)).
  Ties are common here (many jobs have identical features), so even the sweep and the
  reproduction differ by ~0.3 MAPE points at the same θ and k. Compare to within a
  tolerance, not to the last digit.

## What it is measured against

The paper's Table I, on Fugaku jobs submitted from 2024-02-01 (more than 1.3 million jobs
from more than 700 users). Its baselines retrain daily on the last 60 days of **all** users'
jobs ("A-"); the "U-" models use only the user's jobs.

| Approach | Avg power MAPE | R² | Peak power MAPE | R² |
|---|---:|---:|---:|---:|
| **UoPC (U-KNN)** | **10%** | **0.80** | **10%** | **0.79** |
| U-RF | — | — | — | — |
| A-RF | 14% | 0.76 | 15% | 0.76 |
| A-KNN | 16% | 0.60 | 17% | 0.58 |

- **U-RF** gave no result within a week.
- **A linear regression on the user's last 5 jobs** scored over 100% MAPE and is left out
  of the table.
- **On PM100** the paper reports UoPC at 18% / 0.11 on average power and 22% / 0.13 on
  peak, against A-RF at 20% / 0.07 and 24% / 0.13.
- **The README's figure is garbled.** It says "10% prediction error on more than 700k job
  data"; the paper's figures are >1.3M jobs and >700 users.

A run counts as a reproduction if it lands within a few points of UoPC's row.

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

**It reproduces.** 9.9% MAPE on average power (10.2% on peak) matches the paper's 10%. R²
is higher than the paper's (0.837 against 0.80, and 0.826 against 0.79). That is
consistent with the ~150k heavily padded jobs this test set contains and the paper's
apparently does not ([Known deviations](#known-deviations)). Those jobs are easy to
predict. But they don't account for the whole gap: with every job allocated more than 12×
its request dropped, R² is 0.751 and 0.737, *below* the paper's
([Variants](#variants-padded-jobs-and-node-count)). Better-balanced features narrow the gap
to 0.766 and 0.753 ([Feature modes](#feature-modes)), but don't close it.

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

### Variants: padded jobs and node count

Two reruns separate what makes our numbers differ from the paper's and from the rolling
benchmark ([#222](https://github.com/NatLabRockies/hpc-oda-commons/issues/222)). Each is
the reproduction above with one setting changed:

| Recipe | Changed setting | Jobs used | Test jobs | Scored |
|---|---|---:|---:|---:|
| `uopc_paper_reproduction.yml` | — | 2,930,414 | 1,591,115 | 1,587,516 |
| `uopc_paper_reproduction_unpadded.yml` | `max_alloc_ratio: 12` | 2,488,780 | 1,443,390 | 1,439,792 |
| `uopc_paper_reproduction_requested.yml` | `node_count: requested` | 2,930,414 | 1,591,115 | 1,587,516 |

They ran on 2026-10-19 at d1e11c8, ~32 minutes each, peaking at 12 and 16 GB.
`max_alloc_ratio: 12` dropped 441,634 jobs from history and test: 410,740 allocated 48× their
request, 30,855 at 24×, and 39 others.

| Target | Run | MAE | RMSE | MAPE | R² | Per-user mean MAPE / R² |
|---|---|---:|---:|---:|---:|---:|
| Average | Paper (Table I) | | | 10% | 0.80 | |
| | Reproduction (per allocated node) | 6.36 | 16.14 | 9.93% | 0.837 | 60.27% / 0.771 |
| | Unpadded (per allocated node) | 7.07 | 17.01 | **10.34%** | **0.751** | 23.02% / 0.693 |
| | Per requested node | 6.30 | 15.97 | **8.65%** | **0.738** | 14.30% / 0.729 |
| | Rolling benchmark UoPC (per requested node, [power.md](power.md)) | 8.01 | 18.13 | 11.36% | 0.660 | — |
| Peak | Paper (Table I) | | | 10% | 0.79 | |
| | Reproduction | 6.72 | 17.77 | 10.17% | 0.826 | 61.77% / 0.769 |
| | Unpadded | 7.41 | 18.62 | **10.54%** | **0.737** | 23.81% / 0.686 |
| | Per requested node | 6.67 | 17.56 | **8.91%** | **0.718** | 15.01% / 0.719 |
| | Rolling benchmark UoPC | 8.60 | 20.04 | 11.73% | 0.629 | — |

What they show:

- **On the paper's apparent data, MAPE still matches and R² falls short.** Dropping the
  padded jobs leaves 1.44M test jobs (the paper reports more than 1.3M). MAPE is 10.3% and
  10.5% against the paper's 10%. R² is 0.75 and 0.74 against 0.80 and 0.79. The padded jobs
  had lifted our R² above the paper's; without them it sits below. Better-balanced features
  narrow that gap but don't close it ([Feature modes](#feature-modes)).
- **Dividing by requested nodes lowers MAPE and R² alike.** It scores the same jobs as the
  reproduction. MAPE drops from 9.93% to 8.65% because the ~2 W padded targets, where a
  small miss is a large percentage, become ~90 W. R² drops from 0.837 to 0.738 because
  those same jobs no longer form an easy, isolated cluster. The per-user mean's 60% MAPE
  falls to 14%, confirming that it came from the padded jobs.
- **The rolling benchmark's day-level cutoff costs UoPC about 2.7 points.** The
  per-requested-node run and the rolling UoPC share a target and features. The reproduction
  sees every job its user finished before submission; the rolling version only sees jobs
  that finished before the day began, within 60 days. That takes MAPE from 8.65% to 11.36%
  and R² from 0.738 to 0.660 (8.91% to 11.73% on peak). The comparison is approximate:
  - the rolling run also gives cold-start users the all-user mean instead of skipping them
    (0.86% of its jobs), and fits its scaling per window;
  - its test set is 1.51M jobs in 85 daily windows against 1.59M here.
- **UoPC on fresh per-job history beats every rolling model on MAPE, but not on R².** At
  8.65% it is below the rolling benchmark's best, MoE XGBoost at 10.07%. Its R² of 0.738 is
  below XGBoost's 0.810, the same pattern as on the rolling windows: small typical errors,
  more large misses. The protocols differ, so this is not a ranking.

### Feature modes

`split.uopc_features` sets how UoPC describes a job to its kNN, in both the cutoff and
rolling protocols ([#222](https://github.com/NatLabRockies/hpc-oda-commons/issues/222)):

| Mode | Features |
|---|---|
| `zscore` | the job embedding + z-scored cores, nodes and frequency requested (the paper-reproduction recipes, which pin it) |
| `embedding` | the job embedding alone |
| `balanced` (default since #222) | the embedding + `0.2 × log2(nodes requested)` + `0.8 × frequency scaled to [0, 1]` |

- **The balanced weights** make one doubling of nodes add 0.2, so 1 → 16 nodes adds 0.8. A
  frequency switch also adds 0.8. Both are about one typical job-name distance on F-DATA,
  where the median between two of a user's job names is 0.84.
- **Its frequency range** is fitted on history only.
- **It leaves cores out**, since on F-DATA they are always 48 × nodes.
- **The whole-machine jobs that inflate z-scored nodes are kept.** Jobs of up to 152,064
  nodes are genuine, completed production runs.

Each run below is a bundled recipe plus one `uopc_features` key. The variant recipes are not
bundled. They ran on 2026-10-19 at 935e58a, and the `zscore` rows are the earlier results.

**Unpadded reproduction** (`uopc_paper_reproduction_unpadded.yml`, the paper's apparent data):

| Target | Features | MAE | RMSE | MAPE | R² |
|---|---|---:|---:|---:|---:|
| Average | Paper (Table I) | | | 10% | 0.80 |
| | `zscore` | 7.07 | 17.01 | 10.34% | 0.751 |
| | `embedding` | 7.83 | 18.31 | 11.62% | 0.711 |
| | **`balanced`** | **6.78** | **16.48** | **9.75%** | **0.766** |
| Peak | Paper (Table I) | | | 10% | 0.79 |
| | `zscore` | 7.41 | 18.62 | 10.54% | 0.737 |
| | `embedding` | 8.26 | 19.97 | 11.93% | 0.697 |
| | **`balanced`** | **7.09** | **18.02** | **9.93%** | **0.753** |

**Rolling benchmark UoPC** (`uopc_rolling_*.yml`, [power.md](power.md),
[power-nlr.md](power-nlr.md)):

| Data | Features | MAE | RMSE | MAPE | R² |
|---|---|---:|---:|---:|---:|
| F-DATA, average | `zscore` | 8.01 | 18.13 | 11.36% | 0.660 |
| | `embedding` | 8.41 | 18.78 | 11.86% | 0.635 |
| | **`balanced`** | **7.71** | **17.55** | **10.80%** | **0.682** |
| F-DATA, peak | `zscore` | 8.60 | 20.04 | 11.73% | 0.629 |
| | `embedding` | 9.05 | 20.81 | 12.29% | 0.600 |
| | **`balanced`** | **8.27** | **19.44** | **11.15%** | **0.651** |
| Eagle, average | `zscore` | 80.94 | 116.87 | 24.15% | −0.141 |
| | `embedding` | 79.02 | 113.94 | 23.66% | −0.084 |
| | **`balanced`** | **78.59** | **113.43** | **23.54%** | **−0.075** |
| Kestrel, average | `zscore` | 125.34 | 190.91 | 26.27% | −0.157 |
| | `embedding` | 114.56 | 179.12 | 24.74% | −0.018 |
| | **`balanced`** | **114.37** | **178.84** | **24.69%** | **−0.015** |

What they show:

- **`balanced` is best everywhere tried.**
  - On F-DATA it gains 0.6 MAPE points and about 0.02 R² over `zscore`, in both protocols
    and on both targets.
  - The reproduction drops below the paper's 10% MAPE.
  - The rolling UoPC reaches 10.80%, between XGBoost (11.05%) and MoE XGBoost (10.07%) on
    average power. Its R² of 0.682 is still well below theirs (0.81 and 0.78).
- **On F-DATA the numbers carry real information.** `embedding` alone is worst there,
  because F-DATA's embedding holds only user, job name and environment. So `zscore` was using the numbers
  badly, not using numbers it shouldn't.
- **On Eagle and Kestrel, `zscore` actively hurts.**
  - `embedding` alone beats it by 0.5 and 1.5 points.
  - Our embedding there already includes the requested nodes in its text, so the z-scored
    columns add distortion rather than information.
  - `balanced` is level with `embedding`.
  - UoPC stays far behind the tree models on both systems either way (R² below zero, ~24%
    against ~20%).
- **The balanced weights were set for F-DATA's embedding.** On Eagle and Kestrel our harrier
  embedding sits much closer: the median within-user distance is ~0.2, against 0.84. One
  doubling of nodes there weighs about as much as a typical job-name difference, roughly
  four times its relative weight on F-DATA.
- **Runs peaked at 15–21 GB.** The first balanced reproduction slowed to a crawl alongside
  another 8 GB process and was rerun.

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
