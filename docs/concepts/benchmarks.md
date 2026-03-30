# Benchmarks

Benchmarks define how models are evaluated against datasets to produce comparable results.

## Recipes

Recipes are YAML files that fully specify an evaluation:
1. **Dataset** -- which data to use and its schema version
2. **Model** -- which model to evaluate and its version
3. **Metrics** -- which metrics to compute (v0.1 requires MAE and RMSE)
4. **Split** -- how to divide data into train/test sets

Built-in v0.1 recipes:
- `hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml` -- baseline model, fixed split
- `hpc_oda_commons/recipes/job-runtime/xgb_hourly_recent.yml` -- XGBoost, rolling-hourly

See the [Recipes Reference](../reference/recipes.md) for the full format specification with annotated examples.

## Split Methods

### Fixed Split

A simple random partition of rows into training and test sets. Controlled by `train_fraction` and `seed`. Used with the baseline model.

This is fast and easy to understand, but it does not account for temporal dynamics in HPC workloads -- a model might train on future data and test on past data.

### Rolling-Hourly Split

Simulates production deployment by evaluating the model as if it were retrained on a recurring schedule. For each hourly window:

```
         lookback_days              1 hour
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
- **Test**: all jobs whose `submit_time` falls in `[split_time, split_time + 1 hour)`

This enforces strict temporal separation -- the model never sees future data during training.

**Parameters:**
- `n_recent_hours` (required): how many hourly windows to evaluate
- `training_lookback_days` (default 100): how far back to look for training data

### Daily Preprocessing Cache

For the XGBoost model, categorical feature preprocessing (one-hot encoding + SVD dimensionality reduction) is computationally expensive. To avoid redundant computation, the preprocessing pipeline is cached by day -- the encoder and SVD are refit on the first hourly split of each new day, then reused for the remaining hours of that day. This mirrors realistic production behavior where preprocessing would be refreshed on a daily schedule.

## Metrics

The v0.1 runtime prediction problem uses regression metrics:

| Metric | Description |
|--------|-------------|
| MAE | Mean Absolute Error -- average absolute difference in seconds |
| RMSE | Root Mean Squared Error -- penalizes large errors more heavily |

Additional metrics (`mape`, `r2`) can be added to a recipe's metric definitions. All metrics must target the same field (e.g., `runtime_seconds`).

## Result Bundles

Every benchmark run produces a result bundle directory:

```
runs/<run-id>/
  result.json       # Schema-validated result (oda.result.v0.1.0)
  metrics.json      # Detailed metrics (includes per-hour data for rolling-hourly)
  provenance.json   # Full reproducibility record
```

Result bundles are the input to the [leaderboard](../reference/cli.md) generator, which aggregates multiple runs for comparison.

See [Interpreting Results](../how-to/interpret-results.md) for guidance on reading these files.
