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
- `src/hpc_oda_commons/recipes/job-runtime/uopc_maxpcon.yml` -- UoPC power prediction, fixed split

See the [Recipes Reference](../reference/recipes.md) for the full format specification with annotated examples.

## Split Methods

### Fixed Split

A deterministic partition of rows into training and test sets. Controlled by `train_fraction` and `seed`. Used with the baseline model.

This is fast and easy to understand, but it does not account for temporal dynamics in HPC workloads -- a model might train on future data and test on past data.

### Rolling Split

Simulates production deployment by evaluating the model as if it were retrained on a recurring schedule. For each window:

```
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

### Preprocessing Caches

The rolling models use caching to avoid redundant computation across windows:

- **Rolling tabular models** (`xgboost`, `random_forest`, `mlp`): Categorical feature preprocessing (one-hot encoding + SVD) is cached by day. The encoder and SVD are refit on the first split of each new day, then reused for remaining windows. This mirrors production behavior where preprocessing would be refreshed on a daily schedule. The three models share this preprocessing via the `rolling_tabular` package.
- **TF-IDF + kNN**: The HashingVectorizer hash matrix is cached incrementally. Between windows, only new/removed jobs are hashed -- the rest of the matrix is reused. This avoids re-vectorizing the full training set each window.

## Metrics

The v0.1 runtime prediction problem uses regression metrics:

| Metric | Description |
|--------|-------------|
| MAE | Mean Absolute Error -- average absolute difference in seconds |
| RMSE | Root Mean Squared Error -- penalizes large errors more heavily |

Additional metrics (`mape`, `r2`, `underprediction_ratio`) can be added to a recipe's metric definitions. All metrics must target the same field (e.g., `runtime_seconds`).

## Result Bundles

Every benchmark run produces a result bundle directory:

```
runs/<run-id>/
  result.json       # Schema-validated result (oda.result.v0.1.0)
  metrics.json      # Detailed metrics (includes per-window data for rolling)
  provenance.json   # Full reproducibility record
```

`result.json` includes an `integrity` block with the source code hash, validation status, and git commit. Two results with the same `code_hash` and `validated: true` are guaranteed to have used identical, test-validated code. The leaderboard surfaces these fields for easy comparison.

Result bundles are the input to the [leaderboard](../reference/cli.md) generator, which aggregates multiple runs for comparison.

See [Interpreting Results](../how-to/interpret-results.md) for guidance on reading these files.
