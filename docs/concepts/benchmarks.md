# Benchmarks

Benchmarks define how models are evaluated against datasets to produce comparable results.

## Recipes

A recipe is a YAML file that fully specifies one evaluation:

1. **Dataset:** the prepared table to read, and optionally the days to read from it.
2. **Model:** the model and its version.
3. **Metrics:** at least MAE and RMSE, all on one target column, which is what the model
   predicts.
4. **Split:** how the rows divide into training and test.

The [recipes reference](../reference/recipes.md) explains every key and where recipes come
from: bundled with the package, written for your data by `hpc-oda recipes write`, or by hand.

## Which rows a run reads

A recipe's `dataset.window` names the days a run reads, and `dataset.require_nonnull` the
columns every row must have. They filter the table as it is read, before any split, so a
recipe can read a whole prepared table without a sliced copy on disk. With `by: overlap` (the
default), a job is read if its submit-to-end interval overlaps the days, so a long job that
ends inside the window still trains the earliest windows. With `by: submit`, only jobs
submitted in the days are read.

## Split Methods

### Fixed Split

A deterministic partition of rows into training and test sets, controlled by `train_fraction`
and `seed`. Used with the baseline model and the fixed UoPC adaptation.

This is fast and easy to understand, but it does not account for temporal dynamics in HPC
workloads -- a model might train on future data and test on past data.

### Rolling Split

Simulates production deployment by evaluating the model as if it were retrained on a
recurring schedule. For each window:

```text
         lookback_days         test_window_hours
    |◄─────────────────────►|◄──────────────►|
    ┌───────────────────────┬────────────────┐
    │     Train window      │  Test window   │
    │  (jobs that ENDED     │  (jobs that    │
    │   before split_time)  │  were SUBMITTED│
    │                       │  after split)  │
    └───────────────────────┴────────────────┘
                            ▲
                        split_time
```

- **Train**: all jobs whose `end_time` falls in `[split_time - lookback_days, split_time)`
- **Test**: all jobs whose `submit_time` falls in `[split_time, split_time + test_window_hours)`

This enforces strict temporal separation -- the model never sees future data during training.
The `n_windows` test windows end at the last submit hour of the rows read, one after another.
Every model runs under it.

### Cutoff Split

Every job submitted on or after a date (`test_start`) is a test job; everything earlier is
history only. Used with `model.uopc` to reproduce the UoPC paper, which scores each test job
against the jobs its user had finished before it was submitted -- an online protocol rather
than a retraining schedule. See [UoPC](../benchmarking/power/uopc.md).

## The benchmark's protocols

A recipe can use any split settings, but the leaderboard counts only runs on the benchmark's
own protocol for each target: the windows, their length and the lookbacks. The
[runtime](../benchmarking/runtime/methodology.md#benchmark-configuration) and
[power](../benchmarking/power/methodology.md#benchmark-configuration) methodology pages hold
them, and [reading the leaderboard](../how-to/interpret-results.md#reading-the-leaderboard)
says which runs count.

## Rolling tabular models

XGBoost, MoE XGBoost, random forest, MLP and the signature memorizer share one base,
`RollingTabularModel` in `models/rolling_tabular/`. It owns the rolling split, the features and
the preprocessing; each model supplies only its regressor (MoE XGBoost and the memorizer
override the fit and predict step).

**Features.** Only columns known when a job is submitted are used: the allowlist in
`models/feature_policy.py`. The job schema allows extra columns, so anything a descriptor maps
reaches the model, and anything known only after dispatch (`job_state`, `exit_code`, allocated
resources) must be filtered out. `job_id` is an identifier, not a feature, and the target is
never one. A dataset-specific column is admitted per model with `extra_feature_fields`. With
`-v`, the models print the columns they use and the ones they ignore.

**Preprocessing.** Categorical columns (strings and booleans) are one-hot encoded, with rare
values collapsed so the total width stays under `target_max_one_hot_width`, then compressed
with truncated SVD to the components that explain `explained_variance_target` of the variance.
Columns with many distinct values can be target-encoded instead
(`target_encode_min_cardinality`). Numeric columns pass through, with missing values as 0.
The regressor trains on the numeric columns and the SVD components together. To see the
choices the pipeline makes on a table, for tuning, call `analyze_preprocessing(...)` on a
rolling tabular model. The signature
memorizer instead matches jobs on their raw submit-time values.

**Each window:** take the training and test rows; keep those with a finite target; get the
day's preprocessing (below); fit a fresh regressor; predict; score. A window with fewer than
two training rows, no test rows, or no features is skipped and counted. The headline metrics
are computed over every scored row.

### Preprocessing Caches

- **Daily:** the one-hot encoder and SVD are fitted on the first window of each day and reused
  for that day's other windows, as a production system would refresh them daily.
  `summary.preprocessing_refits` counts the fits.
- **Across runs:** a day's preprocessing depends only on its training rows and the
  preprocessing settings, not on the regressor, so the models on this base build the same
  artifacts on the same table and protocol. The benchmark runner keeps them on disk in
  `.hpc_oda/cache/preprocessing/` and builds each once. `HPC_ODA_PREPROCESSING_CACHE=<dir>`
  moves the store and `HPC_ODA_PREPROCESSING_CACHE=off` turns it off.
  - Entries are keyed by content: the training rows' feature values, the target too when
    target encoding is on, the settings, and the versions of the code and of scikit-learn,
    NumPy and SciPy. A hit returns what a fresh build would, so results don't change.
  - Writes are atomic, so parallel jobs can share a store; an unreadable entry is rebuilt.
  - Entries are pickles: point the store only at a directory you control.
  - `summary.preprocessing_store` in `metrics.json` reports `{"hits": n, "misses": m}`.
- **TF-IDF + kNN:** the stateless hashing vectorizer runs once over all rows, and each window
  scores a slice of that matrix. The windows are then independent, so they can run on several
  cores (`window_n_jobs`) without changing results.

## Metrics

| Metric | Description |
|--------|-------------|
| MAE | Mean Absolute Error -- the average absolute error, in the target's units |
| RMSE | Root Mean Squared Error -- penalizes large errors more heavily |

`mape`, `r2` and `underprediction_ratio` can be added to a recipe. All metrics target the same
column (e.g., `runtime_seconds`), and **that column is what the model predicts**: point a model
at `avgpcon_per_node` or `maxpcon_per_node` to predict power per node. A model that cannot
predict the named target fails the run. See [Predict job power](../how-to/predict-power.md).

## Result Bundles

Every benchmark run produces a result bundle directory under the recipe's `run.output_dir`
(default `runs/`):

```text
runs/benchmark-<timestamp>/
  result.json       # Schema-validated result (oda.result.v0.1.0)
  metrics.json      # Detailed metrics (includes per-window data for rolling)
  provenance.json   # Full reproducibility record
```

`result.json` includes an `integrity` block with the source code hash, validation status, and
git commit. Two results with the same `code_hash` and `validated: true` used identical,
test-validated code.

Result bundles are the input to `hpc-oda leaderboard`, which gathers them into one table per
target. See [Interpreting Results](../how-to/interpret-results.md) for reading these files.
