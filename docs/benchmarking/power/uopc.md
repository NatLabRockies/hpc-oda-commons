# UoPC — reproducing the paper inside the Commons

This records how the Commons reproduces UoPC, a user-based online framework that predicts a
job's power draw (Antici, Borghesi, Domke, Kiziltan, *ISC High Performance 2025*,
[doi:10.23919/ISC.2025.11017729](https://doi.org/10.23919/ISC.2025.11017729); code at
[francescoantici/UoPC](https://github.com/francescoantici/UoPC)), what it measured, and how
far the numbers can be trusted. Tracking issue:
[#125](https://github.com/NatLabRockies/hpc-oda-commons/issues/125). The
[UoPC audit](uopc-audit.md) checks it against the full paper and the authors' code.

Our reproduction keeps the paper's protocol but uses only choices we can defend, even where
the authors' differ ([#228](https://github.com/NatLabRockies/hpc-oda-commons/issues/228),
[#241](https://github.com/NatLabRockies/hpc-oda-commons/issues/241)). It divides power by **nodes requested**, not allocated,
uses **balanced** features, and predicts the **median** of the neighbours' values rather than
the authors' vote ([Our choices, and why](#our-choices-and-why)). The authors' exact setup runs separately, as a
labelled [comparison with the paper](#comparison-with-the-paper-the-authors-setup), not as our
result.

Job-power prediction is outside the runtime benchmark ([methodology](../runtime/methodology.md)); this
is a one-model study, not a leaderboard.

## Two protocols, one model

`model.uopc` runs either protocol, chosen by the recipe's `split.method`:

| | `fixed` — the Commons adaptation | `cutoff` — the paper protocol |
|---|---|---|
| Recipe | `job-runtime/uopc_maxpcon.yml` | `job-power/uopc_paper_reproduction.yml`, `uopc_paper_sensitivity.yml` |
| Target | `maxpcon` (W, whole job) | `avgpcon` **and** `maxpcon` per **requested** node (the paper: per allocated node) |
| Features | job name (label-encoded), cores and nodes requested | F-DATA's job `embedding` + `balanced` log2 nodes and frequency (the paper: one embedded string) |
| Predictor | kNN regressor (mean of the k neighbours) | the **median** of the k neighbours (the authors' tool: a kNN classifier's vote over whole watts) |
| Test set | last 20% of jobs by end time | every job submitted on or after `test_start` |
| History for a test job | every earlier job by that user, by end time | that user's jobs that **finished before it was submitted** |
| Context | newest `theta` = 50 | newest `theta` = 500 |
| Data | a hand-placed raw Fugaku file | `dataset.fdata_fugaku` via `datasets prepare`, its Dec 2023–Apr 2024 window |

The adaptation is unchanged by this work. A third mode, `split.method: rolling`, scores the
same model on the shared rolling windows next to every other model
([Power prediction benchmark](results.md)). It uses the same target and features as the
reproduction, so their numbers differ only by protocol.

## Our choices, and why

### Nodes requested, not allocated

**The paper divides by allocated nodes** (F-DATA's `nnuma`); its text and figures both show
it. **We divide by requested nodes** (`nnumr`), because on the public F-DATA files the
allocated count is often padded past the nodes a job ran on. Power is summed over only the
nodes the job ran on (all five months, 2.93M jobs):

| | Jobs with `nnuma` > requested (727,508, 24.8%) |
|---|---:|
| Nodes the job ran on (`nnumu`) = requested | 95.3% |
| Nodes the job ran on = allocated | 0.0% |
| Median W per requested / used / allocated node | 91.8 / 91.9 / **1.9** |
| Share below 20 W per allocated node | 71.6% |

- **The clearest case:** 410,740 jobs request 1 node and 48 cores, run on 1 node and draw
  ~92 W, but record `nnuma` = 48. Per allocated node they read 1.9 W, which no Fugaku node
  draws even idle. Per requested node they read ~92 W, like every other job.
- **Requested nodes are the right count:**
  - they match the nodes a job ran on for ~96% of all jobs;
  - they are known at submission, so a per-node prediction × requested nodes gives the
    job's total before it runs;
  - they are the divisor every other model in the Commons uses ([power results](results.md)).
- **Dividing by allocated nodes would flatter the result.** The padded jobs become an
  isolated, easy-to-predict cluster at ~2 W. On the same jobs and features, that lifts R²
  from 0.738 to 0.837. It also wrecks percentage baselines: the per-user mean scores 60%
  MAPE per allocated node against 14% per requested node
  ([Variants](#variants-padded-jobs-and-node-count)).
- **We keep these jobs.** They are real production jobs. Dividing by requested nodes gives
  them their real ~90 W per node; dropping them would make the test easier.
- **It isn't the paper's data either.** The paper's figures show no jobs below ~10 W per
  allocated node, so its export appears to lack these jobs. Dividing the public files by
  allocated nodes therefore isn't the paper's setup
  ([Known deviations](#known-deviations-from-the-paper)).

### Balanced features

F-DATA's `embedding` is the paper's encoder (all-MiniLM-L6-v2) over the original user, job
name and environment ([F-DATA's generation script](https://github.com/francescoantici/F-DATA/blob/main/generation_scripts/generate_derived_features.py)). It does not include cores, nodes or frequency, so UoPC adds
them as numbers.
- **The earlier `zscore` scaling** let frequency decide every neighbour (its two values sit
  2.03 apart, more than any two job names) and made the node count invisible: a few
  whole-machine jobs inflate its spread, so 1 → 16 nodes added 0.024.
- **`balanced`** adds `0.2 × log2(nodes)` and frequency scaled to 0–0.8, each about one
  typical job-name distance (0.84). Frequency's range is fitted on history only.
- It scored best everywhere tried ([Feature modes](#feature-modes)).

### The median of the neighbours, not a vote

The authors' tool predicts with `KNeighborsClassifier`: the most common value among the k
neighbours, with power rounded to whole watts so it can be a class label. **We predict the
median of the k neighbours' values instead** ([#241](https://github.com/NatLabRockies/hpc-oda-commons/issues/241)), in this protocol and in the
rolling benchmark.

- **The vote is usually a tie.** When the neighbours' values differ, each gets one vote, and
  scikit-learn breaks the tie with `scipy.stats.mode`, which returns the smallest. So the
  vote picks the lowest neighbour wherever a user's jobs vary.
- **On F-DATA that is mostly hidden,** because a user's repeated jobs share values, but it
  still costs about 0.3 W of MAE (below). On PM100, where a user's jobs vary over hundreds
  of watts, it under-predicted 73% of jobs on the rolling benchmark, by 129 W on average
  ([#241](https://github.com/NatLabRockies/hpc-oda-commons/issues/241)).
- **Median or mean** of the same neighbours was chosen on this protocol alone, as k was;
  choosing on the benchmark datasets would tune on their test sets. The rule, fixed before
  the runs: the lower MAE, the benchmark's metric, on both targets.

Our reproduction with each predictor, on the same 1,581,909 jobs (θ = 500, k = 20, per
requested node, `balanced`):

| Predictor | Average MAE | RMSE | MAPE | R² | Peak MAE | RMSE | MAPE | R² |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Vote (the authors' rule) | 5.71 | 14.98 | 7.82% | 0.770 | 6.00 | 16.41 | 8.06% | 0.754 |
| Mean | 5.58 | **13.93** | 7.82% | **0.801** | 5.90 | **15.31** | 8.08% | **0.785** |
| **Median** | **5.44** | 14.44 | **7.63%** | 0.786 | **5.72** | 15.86 | **7.84%** | 0.770 |

- **The median has the lowest MAE and MAPE on both targets.** The mean has the higher R²
  and lower RMSE: it minimises squared error, the median absolute error.
- **k = 20 still holds for the median** ([sweep](#sensitivity-sweep-θ--k)).
- **The paper-comparison recipes keep the vote** (`predictor: vote`), as the authors' rule.

### What we keep from the paper

- the test set (jobs submitted from 2024-02-01);
- the history rule (the user's jobs finished before submission, newest θ = 500);
- skipping users with fewer than k such jobs;
- a per-user kNN over the newest θ jobs.

The paper's k = 5 is not kept. Its θ = 500 and k = 5 were chosen on the authors' setup. On
our settings the [sweep](#sensitivity-sweep-θ--k) confirms θ = 500 but puts k = 20 about 0.4
points of MAPE ahead of k = 5, so we use **k = 20**, in this protocol and in the rolling
benchmark. The paper-comparison recipes keep k = 5.

## Running it

```bash
# ~9.7 GB: the twelve F-DATA monthly files; the recipes read Dec 2023 - Apr 2024
hpc-oda datasets prepare src/hpc_oda_commons/datasets/descriptors/fdata_fugaku.yml

# Our reproduction, and the theta x k sweep, on our settings
hpc-oda benchmark src/hpc_oda_commons/recipes/job-power/uopc_paper_reproduction.yml
hpc-oda benchmark src/hpc_oda_commons/recipes/job-power/uopc_paper_sensitivity.yml

# The authors' setup, for comparison with the paper only
hpc-oda benchmark src/hpc_oda_commons/recipes/job-power/uopc_paper_reproduction_paper_setup.yml
hpc-oda benchmark src/hpc_oda_commons/recipes/job-power/uopc_paper_reproduction_unpadded.yml
```

| Recipe | Node count | Features | k | Predictor | Jobs |
|---|---|---|---:|---|---|
| `uopc_paper_reproduction.yml` (**ours**) | requested | `balanced` | 20 | median | all |
| `uopc_paper_sensitivity.yml` | requested | `balanced` | 20 | all three; median is the headline | all |
| `uopc_paper_reproduction_paper_setup.yml` | allocated | `zscore` | 5 | vote | all |
| `uopc_paper_reproduction_unpadded.yml` | allocated | `zscore` | 5 | vote | without jobs allocated >12× their request |

The reproduction writes `predictions.parquet`: one row per scored job with both targets'
truth and prediction, the two baselines' predictions, and the job's history and context
sizes. `metrics.json` holds both targets' metrics, the baselines and, for the sweep, the
whole θ × k grid with coverage and cold-start counts.

The F-DATA window is a separate dataset from the runtime benchmark's `fdata_fugaku`
(Mar–Sep 2023). They cover different months and must never share a prepared table.

## The protocol in detail

- **Rows.** A job is usable when it has `avgpcon`, `maxpcon`, an `embedding`, submit and end
  times, and a positive node count. Targets are watts per requested node (`node_count`;
  `allocated` divides by `nnuma` instead).
- **Test set.** Jobs submitted on or after `test_start` (2024-02-01), scored in submission
  order. Everything before the cutoff serves only as history.
- **History.** For a test job, the same user's jobs whose end time is strictly before its
  submit time — the information a scheduler would actually have. A test job with fewer
  than `k` such jobs is skipped (counted in `rows_skipped`).
- **Context.** The newest `theta` jobs of that history, by end time.
- **Prediction.** The median of the k nearest context jobs' values (`predictor: median`).
  `mean` takes their mean; `vote` fits a `KNeighborsClassifier(k)` with targets rounded to
  whole watts as classes, as in the authors' tool. All three see the same neighbours, and
  average and peak power share them.
- **Baselines.** For the same scored jobs: the mean of the user's whole eligible history
  (per-user mean), and the mean of every job anyone finished before submission (global
  mean). Both use only past information.
- **Sensitivity.** θ ∈ {50, 100, 200, 500, 1000, 2000, 5000} × k ∈ {5, 10, 20, 50}. Each
  test job's neighbours are found once per θ, up to the largest k, and reused for every k.
  A cell scores only jobs with at least k prior jobs, so coverage falls as k grows. Each
  cell is scored by all three predictors from the same neighbours, under the columns
  `classifier` (the vote), `regressor` (the mean) and `median`. The headline is the median
  at θ = 500, k = 20.

## Known deviations from the paper

- **Node count (deliberate).** We divide by requested nodes; the paper divides by allocated
  nodes. See [Nodes requested, not allocated](#nodes-requested-not-allocated).
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
    ([Feature modes](#feature-modes)). `balanced` has been the default since #222, and our
    reproduction uses it (#228). `zscore` remains only in the paper-comparison recipes.
  - **We don't embed F-DATA ourselves.** The paper's string can't be rebuilt from public
    data: the job names and environments are anonymised IDs (`jnam_2111729`), which would
    carry no name meaning and would make unrelated IDs look alike.
- **R² stays below the paper's on its apparent data.** This is a known limitation. Without
  the padded jobs, the best features reach R² 0.766 and 0.753, against the paper's 0.80 and
  0.79. The paper's features rely on the real job names, which public F-DATA doesn't have,
  so the gap may not be closable on public data.
- **`zscore` scaling sees the test period.** This applies only to the paper-comparison
  recipes; `balanced` fits frequency's range on history only. The z-scores use the whole usable dataset,
  test months included: a look-ahead in the feature scale only, with no target leak.
  Fitting on the history before 2024-02-01 instead would barely change anything:
  - frequency's gap would be 2.02 rather than 2.03;
  - the std. devs. of cores and nodes would be about 16% smaller, still negligible next to
    job names.

  A deployment would fit the scaling on history alone.
- **Predictor (deliberate).** The authors' tool predicts with `KNeighborsClassifier`, which
  accepts only discrete labels, so the paper-comparison recipes round per-node power to
  whole watts first; the rounding is ours. We predict the median of the same neighbours
  instead. See [The median of the neighbours, not a vote](#the-median-of-the-neighbours-not-a-vote).
- **The paper's data lacks the most padded jobs.** The paper divides by allocated nodes, as
  the paper-setup recipe does. Its Fig. 4 shows the same small bars at ~11, 15 and 22 W that our
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

### Our reproduction (θ = 500, k = 20)

`uopc_paper_reproduction.yml`: per requested node, `balanced` features, k = 20, the median of
the neighbours, all jobs. It ran on 2026-10-20 on an Apple M3 Max (14 cores, 38 GB) with the
code committed as 4ee97bb (the run came first; the commit changed only the default and
comments). It took 11 minutes.

1,591,115 test jobs from 764 users were submitted on or after 2024-02-01. 1,581,909 were
scored; 9,206 (0.58%) were skipped as cold starts, with fewer than k = 20 prior jobs by
their user.

| Target (W per requested node) | Model | MAE | RMSE | MAPE | R² |
|---|---|---:|---:|---:|---:|
| Average (`avgpcon`) | **UoPC** | **5.44** | **14.44** | **7.63%** | **0.786** |
| | Per-user mean | 9.53 | 16.20 | 14.27% | 0.731 |
| | Global mean | 25.84 | 31.25 | 37.30% | −0.002 |
| Peak (`maxpcon`) | **UoPC** | **5.72** | **15.86** | **7.84%** | **0.770** |
| | Per-user mean | 10.21 | 17.48 | 14.98% | 0.720 |
| | Global mean | 26.23 | 33.06 | 36.31% | −0.001 |

**Against the paper (10% / 0.80 and 10% / 0.79).** MAPE is lower and R² is a little lower. The
target is not the paper's: per requested node, not per allocated node, so the two can't be
compared exactly.

**What each of our choices adds**, on this target and all jobs:

| Features, k, predictor | Average MAPE / R² | Peak MAPE / R² |
|---|---:|---:|
| `zscore`, k = 5, vote ([Variants](#variants-padded-jobs-and-node-count)) | 8.65% / 0.738 | 8.91% / 0.718 |
| `balanced`, k = 5, vote (run at 8d914e7) | 8.29% / 0.753 | 8.47% / 0.737 |
| `balanced`, k = 20, vote (run at cd78524) | 7.82% / 0.770 | 8.06% / 0.754 |
| **`balanced`, k = 20, median** | **7.63% / 0.786** | **7.84% / 0.770** |

k = 20 also skips 5,607 more short-history jobs than k = 5. Those are hard jobs (about 20%
MAPE), but too few to account for more than ~0.05 points of the gain.

**Padded jobs no longer matter.** Per requested node, the 147,671 scored jobs allocated more
than 12× their request have their real target, a median of 91.7 W. They are still easy to
predict (1.0% MAPE): they are uniform one- and two-node jobs from 11 users. Without them
UoPC scores 8.31% / 0.786 on average power and 8.53% / 0.770 on peak. MAPE rises because
easy jobs are gone, but R² doesn't move. Per allocated node, excluding the padded jobs
lowered R² from 0.837 to 0.762 ([padded allocations](#comparison-with-the-paper-the-authors-setup)).

The median absolute percentage error is 1.4%, and 88.4% of jobs are within 10%. As with the
authors' setup, the mean is carried by a tail: the 90th percentile is 13%.

**Cold starts and short histories.** 95.7% of scored jobs had a full θ = 500 context.
Error falls as a user's history grows:

| User's prior jobs | Jobs | UoPC MAPE | Per-user mean MAPE |
|---|---:|---:|---:|
| 20–49 | 8,016 | 20.0% | 22.9% |
| 50–499 | 60,094 | 14.3% | 20.4% |
| 500+ | 1,513,799 | 7.3% | 14.0% |

### Comparison with the paper: the authors' setup

The results below use the authors' setup, `uopc_paper_reproduction_paper_setup.yml`: per
allocated node, with `zscore` features. They were the published headline until #228. They
show that the method reproduces, but they aren't our result.

They ran on 2026-10-16 on an Apple M3 Max (14 cores, 38 GB) at commit 76f4f0f, as
`uopc_paper_reproduction.yml` with those settings. The run took 28 minutes (about 1 ms per
scored job, single-threaded) and peaked at ~20 GB resident.

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
apparently does not ([Known deviations](#known-deviations-from-the-paper)). Those jobs are easy to
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

`uopc_paper_sensitivity.yml`, on our settings: per requested node, `balanced` features, all
jobs. It ran on 2026-10-19 at 8d914e7, with k = 5 as the headline; the grid itself doesn't depend
on the headline. It predates the median column ([below](#the-median-θ--500)). The full grid took 2 h 12 min (8 to 51 minutes per θ, the most at
θ = 5000). Each cell shows MAPE / R² on average power per requested node. The paper's
θ = 500, k = 5 and ours, θ = 500, k = 20 (also the best classifier cell), are in bold.

**Classifier** (the paper's predictor, a majority vote over rounded watts):

| θ \ k | 5 | 10 | 20 | 50 |
|---|---:|---:|---:|---:|
| 50 | 9.58% / 0.710 | 9.59% / 0.715 | 9.67% / 0.713 | 10.30% / 0.681 |
| 100 | 9.21% / 0.722 | 9.11% / 0.730 | 9.07% / 0.732 | 9.33% / 0.713 |
| 200 | 8.71% / 0.736 | 8.49% / 0.750 | 8.45% / 0.751 | 8.77% / 0.734 |
| 500 | **8.12% / 0.757** | 7.73% / 0.775 | **7.70% / 0.776** | 7.85% / 0.767 |
| 1000 | 8.23% / 0.752 | 7.80% / 0.776 | 7.72% / 0.776 | 7.81% / 0.768 |
| 2000 | 8.30% / 0.744 | 7.82% / 0.773 | 7.83% / 0.772 | 7.84% / 0.774 |
| 5000 | 8.62% / 0.725 | 8.00% / 0.756 | 7.91% / 0.760 | 8.07% / 0.756 |

**Regressor** (the mean of the same neighbours, an ablation):

| θ \ k | 5 | 10 | 20 | 50 |
|---|---:|---:|---:|---:|
| 50 | 9.45% / 0.745 | 9.48% / 0.746 | 9.62% / 0.744 | 10.53% / 0.727 |
| 100 | 9.01% / 0.759 | 8.96% / 0.763 | 9.03% / 0.761 | 9.29% / 0.753 |
| 200 | 8.50% / 0.779 | 8.39% / 0.784 | 8.37% / 0.785 | 8.56% / 0.778 |
| 500 | 7.83% / 0.802 | 7.70% / 0.808 | 7.70% / 0.809 | 7.81% / 0.805 |
| 1000 | 7.92% / 0.803 | 7.79% / 0.811 | 7.70% / 0.816 | 7.77% / 0.815 |
| 2000 | 7.93% / 0.804 | 7.79% / 0.813 | 7.70% / 0.819 | 7.73% / 0.822 |
| 5000 | 8.14% / 0.790 | 8.04% / 0.798 | 7.94% / 0.804 | 8.01% / 0.805 |

<details>
<summary>Peak power (maxpcon per requested node)</summary>

Classifier:

| θ \ k | 5 | 10 | 20 | 50 |
|---|---:|---:|---:|---:|
| 50 | 9.71% / 0.699 | 9.81% / 0.697 | 9.81% / 0.700 | 10.70% / 0.657 |
| 100 | 9.37% / 0.703 | 9.27% / 0.714 | 9.24% / 0.717 | 9.45% / 0.703 |
| 200 | 8.84% / 0.721 | 8.73% / 0.730 | 8.67% / 0.732 | 8.92% / 0.722 |
| 500 | 8.20% / 0.744 | 7.92% / 0.757 | 7.87% / 0.758 | 8.07% / 0.751 |
| 1000 | 8.39% / 0.740 | 8.10% / 0.756 | 7.97% / 0.758 | 7.98% / 0.755 |
| 2000 | 8.21% / 0.743 | 8.07% / 0.756 | 8.04% / 0.756 | 7.96% / 0.759 |
| 5000 | 8.42% / 0.723 | 8.00% / 0.741 | 7.83% / 0.746 | 7.92% / 0.745 |

Regressor:

| θ \ k | 5 | 10 | 20 | 50 |
|---|---:|---:|---:|---:|
| 50 | 9.68% / 0.731 | 9.71% / 0.732 | 9.91% / 0.729 | 10.97% / 0.710 |
| 100 | 9.18% / 0.745 | 9.16% / 0.748 | 9.24% / 0.747 | 9.52% / 0.741 |
| 200 | 8.70% / 0.763 | 8.63% / 0.768 | 8.62% / 0.769 | 8.82% / 0.764 |
| 500 | 8.04% / 0.785 | 7.92% / 0.792 | 7.95% / 0.792 | 8.08% / 0.789 |
| 1000 | 8.21% / 0.785 | 8.09% / 0.793 | 8.01% / 0.798 | 8.10% / 0.799 |
| 2000 | 8.16% / 0.791 | 8.03% / 0.801 | 7.94% / 0.807 | 7.99% / 0.809 |
| 5000 | 8.21% / 0.775 | 8.11% / 0.784 | 8.03% / 0.790 | 8.13% / 0.791 |

</details>

**Coverage.** A cell scores only jobs whose user has at least k prior jobs: 99.77% of test
jobs at k = 5, 99.61% at 10, 99.42% at 20 and 98.92% at 50. Of the 1,591,115 test jobs, 812
have no prior job by their user, and 3,599, 6,133, 9,206 and 17,222 have fewer than 5, 10,
20 and 50. The median user history is 28,779 jobs.

What the grid shows:

- **θ = 500 still holds.** MAPE falls from 9.6% at θ = 50 to 7.7–8.3% for θ = 500–2000, and
  θ = 5000 is slightly worse again. Going past 500 gains nothing on average power.
- **k = 5 does not, so we use k = 20.** At θ = 500, k = 10 and k = 20 score 7.73% / 0.775
  and 7.70% / 0.776, against 8.12% / 0.757 at k = 5. The best classifier cell is θ = 500,
  k = 20. On peak power, k = 20 is also ~0.3 points better than k = 5. We chose k = 20 from
  this grid alone and use it on every dataset, including Eagle and Kestrel, where it was not
  tuned ([Eagle and Kestrel](results.md#eagle-and-kestrel)).
- **The spike at k = θ/10 is gone.** On the authors' setup the classifier jumped to ~19% at
  (50, 5), (100, 10), (200, 20) and (500, 50), all from the padded users' ~2 W targets
  (below). Per requested node every row is smooth.
- **Voting on rounded watts still costs R², but not MAPE.** The regressor has the higher R²
  in every cell (0.73–0.82 against 0.68–0.78). The two MAPEs are within 0.5 points either
  way. Without the ~2 W targets, the regressor's MAPE no longer climbs with k; its best R² is
  0.822, at θ = 2000, k = 50.
- **The grid's cells differ slightly from the reproduction runs** because of exact ties, as
  on the authors' setup (below): 7.70% against 7.82% at θ = 500, k = 20, and 8.12% against
  8.29% at k = 5.

#### The median (θ = 500)

The grid above predates the median predictor ([#241](https://github.com/NatLabRockies/hpc-oda-commons/issues/241)). To check k for
it, the sweep reran at θ = 500 only, on 2026-10-20 with the code committed as 4ee97bb
(13 minutes). Its vote and mean columns match the grid above to the last digit. MAE /
MAPE / R² per requested node:

| k | Average | Peak |
|---:|---:|---:|
| 5 | 5.51 / 7.79% / 0.782 | 5.78 / 7.97% / 0.765 |
| 10 | 5.32 / 7.51% / **0.795** | **5.60** / **7.71%** / **0.777** |
| **20** | **5.31** / **7.50%** / 0.792 | 5.60 / 7.72% / 0.774 |
| 50 | 5.41 / 7.62% / 0.783 | 5.70 / 7.83% / 0.768 |

- **k = 20 holds.** It is best on average power. On peak, k = 10 is ahead by 0.002 W and
  0.01 points of MAPE, too little to set a different k per target.
- **The median beats the vote and the mean on MAE in every column**, as in the reproduction
  runs ([The median of the neighbours](#the-median-of-the-neighbours-not-a-vote)). The sweep's MAEs are
  lower than the reproduction's (5.31 against 5.44 at k = 20) because of exact ties, as
  below.

#### On the authors' setup

The first sweep ran per allocated node with `zscore` features, at 76f4f0f, and is kept for
the comparison with the paper. Like the paper's, it put θ = 500, k = 5 close to the best. The
full grid took 2 h 15 min (7 to 51 minutes per θ, the most at θ = 5000) and peaked at ~17 GB
resident. Each cell shows MAPE / R² on average power per allocated node; coverage is the same
as above.

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

What that grid showed:

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
the authors' setup above, including its vote, with one setting changed:

| Recipe | Changed setting | Jobs used | Test jobs | Scored |
|---|---|---:|---:|---:|
| `uopc_paper_reproduction_paper_setup.yml` | — | 2,930,414 | 1,591,115 | 1,587,516 |
| `uopc_paper_reproduction_unpadded.yml` | `max_alloc_ratio: 12` | 2,488,780 | 1,443,390 | 1,439,792 |
| per requested node (its recipe became the headline's node count in #228) | `node_count: requested` | 2,930,414 | 1,591,115 | 1,587,516 |

They ran on 2026-10-19 at d1e11c8, ~32 minutes each, peaking at 12 and 16 GB.
`max_alloc_ratio: 12` dropped 441,634 jobs from history and test: 410,740 allocated 48× their
request, 30,855 at 24×, and 39 others. Every row below uses `zscore` features.

| Target | Run | MAE | RMSE | MAPE | R² | Per-user mean MAPE / R² |
|---|---|---:|---:|---:|---:|---:|
| Average | Paper (Table I) | | | 10% | 0.80 | |
| | Authors' setup (per allocated node) | 6.36 | 16.14 | 9.93% | 0.837 | 60.27% / 0.771 |
| | Unpadded (per allocated node) | 7.07 | 17.01 | **10.34%** | **0.751** | 23.02% / 0.693 |
| | Per requested node | 6.30 | 15.97 | **8.65%** | **0.738** | 14.30% / 0.729 |
| | Rolling benchmark UoPC with `zscore` (per requested node) | 8.01 | 18.13 | 11.36% | 0.660 | — |
| Peak | Paper (Table I) | | | 10% | 0.79 | |
| | Authors' setup | 6.72 | 17.77 | 10.17% | 0.826 | 61.77% / 0.769 |
| | Unpadded | 7.41 | 18.62 | **10.54%** | **0.737** | 23.81% / 0.686 |
| | Per requested node | 6.67 | 17.56 | **8.91%** | **0.718** | 15.01% / 0.719 |
| | Rolling benchmark UoPC with `zscore` | 8.60 | 20.04 | 11.73% | 0.629 | — |

What they show:

- **On the paper's apparent data, MAPE still matches and R² falls short.** Dropping the
  padded jobs leaves 1.44M test jobs (the paper reports more than 1.3M). MAPE is 10.3% and
  10.5% against the paper's 10%. R² is 0.75 and 0.74 against 0.80 and 0.79. The padded jobs
  had lifted our R² above the paper's; without them it sits below. Better-balanced features
  narrow that gap but don't close it ([Feature modes](#feature-modes)).
- **Dividing by requested nodes lowers MAPE and R² alike.** It scores the same jobs as the
  authors' setup. MAPE drops from 9.93% to 8.65% because the ~2 W padded targets, where a
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
| `zscore` | the job embedding + z-scored cores, nodes and frequency requested (the paper-comparison recipes) |
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
Every run in this section uses k = 5, the default until #228, and the vote, the default until
#241; our results at k = 20 with the median are in
[Our reproduction](#our-reproduction-θ--500-k--20) and the [power results](results.md).

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

**Per requested node, all jobs** (`uopc_paper_reproduction.yml` at k = 5; the `balanced`
rows ran at 8d914e7):

| Target | Features | MAE | RMSE | MAPE | R² |
|---|---|---:|---:|---:|---:|
| Average | `zscore` | 6.30 | 15.97 | 8.65% | 0.738 |
| | **`balanced`** | **6.11** | **15.50** | **8.29%** | **0.753** |
| Peak | `zscore` | 6.67 | 17.56 | 8.91% | 0.718 |
| | **`balanced`** | **6.39** | **16.94** | **8.47%** | **0.737** |

**Rolling benchmark UoPC** (`uopc_rolling_*.yml`, [power results](results.md)):

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
  - On F-DATA it gains 0.4–0.6 MAPE points and about 0.02 R² over `zscore`, in both
    protocols, on both targets and with either node count.
  - The unpadded reproduction drops below the paper's 10% MAPE.
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

## Is this protocol the power benchmark?

No. Job-power prediction is becoming a tracked benchmark
([#230](https://github.com/NatLabRockies/hpc-oda-commons/issues/230)), but on the shared
rolling protocol every model runs on ([power results](results.md)), not on this one. This
protocol is UoPC's own: it refits a model per job against that user's history, which most
models in the Commons do not support. The reproduction stays as UoPC's reference result.
