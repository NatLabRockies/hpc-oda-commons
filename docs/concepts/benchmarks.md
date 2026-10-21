# Benchmarks

Benchmarks define how models are evaluated against datasets to produce comparable results.

## Recipes

Recipes are YAML files that fully specify an evaluation:
1. **Dataset** -- which data to use and its schema version
2. **Model** -- which model to evaluate and its version
3. **Metrics** -- which metrics to compute (v0.1 requires MAE and RMSE)
4. **Split** -- how to divide data into train/test sets

Built-in v0.1 recipes:
- `src/hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml` -- baseline model, fixed split
- `src/hpc_oda_commons/recipes/job-runtime/xgb_hourly_recent.yml` -- XGBoost, rolling
- `src/hpc_oda_commons/recipes/job-runtime/alt_model_example.yml` -- XGBoost, smaller rolling window
- `src/hpc_oda_commons/recipes/job-runtime/mlp_rolling.yml` -- MLP, rolling
- `src/hpc_oda_commons/recipes/job-runtime/embedding_knn_rolling.yml` -- embedding kNN, rolling (needs an embedded dataset)
- `src/hpc_oda_commons/recipes/job-runtime/uopc_maxpcon.yml` -- UoPC power prediction, fixed split
- `src/hpc_oda_commons/recipes/job-power/uopc_paper_reproduction.yml` -- the UoPC paper protocol, cutoff split ([UoPC reproduction](../benchmarking/power/uopc.md))
- `src/hpc_oda_commons/recipes/job-power/uopc_paper_sensitivity.yml` -- the paper's θ × k sweep, cutoff split
- `src/hpc_oda_commons/recipes/job-power/<model>_rolling_{avg,peak}.yml` -- every model, UoPC included, predicting average or peak power per node on one rolling protocol ([Power prediction benchmark](../benchmarking/power/results.md))
- `src/hpc_oda_commons/recipes/job-power/<model>_rolling_avg_{eagle,kestrel}.yml` -- the same models predicting average power per node on NLR Eagle and Kestrel, on the same split shape ([Power prediction on Eagle and Kestrel](../benchmarking/power/results.md#eagle-and-kestrel))
- `src/hpc_oda_commons/recipes/job-power/<model>_rolling_{avg,peak}_pm100.yml` -- the same models predicting average and peak power per node on PM100 (Marconi100) ([PM100](../benchmarking/power/results.md#pm100))

See the [Recipes Reference](../reference/recipes.md) for the full format specification with annotated examples.

## Split Methods

### Fixed Split

A deterministic partition of rows into training and test sets. Controlled by `train_fraction` and `seed`. Used with the baseline model.

This is fast and easy to understand, but it does not account for temporal dynamics in HPC workloads -- a model might train on future data and test on past data.

### Rolling Split

Simulates production deployment by evaluating the model as if it were retrained on a recurring schedule. For each window:

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

**Parameters:**
- `n_windows` (required): how many windows to evaluate
- `test_window_hours` (default 6): duration of each test window in hours
- `training_lookback_days` (default 100): how far back to look for training data

### Cutoff Split

Every job submitted on or after a date (`test_start`) is a test job; everything earlier is history only. Used with `model.uopc` to reproduce the UoPC paper, which scores each test job against the jobs its user had finished before it was submitted -- an online protocol rather than a retraining schedule. See [UoPC reproduction](../benchmarking/power/uopc.md).

**Parameters:**
- `test_start` (required): ISO date, quoted in YAML
- `theta` / `k`: history size and neighbour count
- `theta_values` / `k_values` (optional): run the θ × k sensitivity grid instead; `theta`/`k` then name its headline cell

### Preprocessing Caches

The rolling models use caching to avoid redundant computation across windows:

- **Rolling tabular models** (`xgboost`, `random_forest`, `mlp`): Categorical feature preprocessing (one-hot encoding + SVD) is cached by day. The encoder and SVD are refit on the first split of each new day, then reused for remaining windows. This mirrors production behavior where preprocessing would be refreshed on a daily schedule. The three models share this preprocessing via the `rolling_tabular` package.
- **TF-IDF + kNN**: The stateless HashingVectorizer runs once over all rows, and each window scores an index slice of that single hash matrix. Because the windows are then independent, they can run concurrently across cores (`window_n_jobs`) without changing results.

## Metrics

The v0.1 runtime prediction problem uses regression metrics:

| Metric | Description |
|--------|-------------|
| MAE | Mean Absolute Error -- average absolute difference in seconds |
| RMSE | Root Mean Squared Error -- penalizes large errors more heavily |

Additional metrics (`mape`, `r2`, `underprediction_ratio`) can be added to a recipe's metric definitions. All metrics must target the same field (e.g., `runtime_seconds`), and **that field is what the model predicts**: point any runtime model at `avgpcon_per_node` or `maxpcon_per_node` to predict power per node. A model that cannot predict the named target fails the run. See [Predict job power](../how-to/predict-power.md).

## Result Bundles

Every benchmark run produces a result bundle directory:

```text
runs/<run-id>/
  result.json       # Schema-validated result (oda.result.v0.1.0)
  metrics.json      # Detailed metrics (includes per-window data for rolling)
  provenance.json   # Full reproducibility record
```

`result.json` includes an `integrity` block with the source code hash, validation status, and git commit. Two results with the same `code_hash` and `validated: true` are guaranteed to have used identical, test-validated code. The leaderboard surfaces these fields for easy comparison.

Result bundles are the input to the [leaderboard](../reference/cli.md) generator, which aggregates multiple runs for comparison.

See [Interpreting Results](../how-to/interpret-results.md) for guidance on reading these files.
