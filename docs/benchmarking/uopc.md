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

The adaptation is unchanged by this work; the paper protocol is new. A third mode,
`split.method: rolling`, scores the same paper model on the shared rolling windows next to
every other model ([Power prediction benchmark](power.md)). When a prepared table carries
`avgpcon_per_node`/`maxpcon_per_node`, the paper protocol reads those columns, so UoPC and
the other models score exactly the same target.

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

Run on <!-- date, machine --> with the bundled recipes.

<!-- results:reproduction -->

<!-- results:sensitivity -->
