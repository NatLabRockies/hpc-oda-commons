# Interpreting Results

After running `hpc-oda benchmark` or `hpc-oda analyze`, you'll have result artifacts. This guide explains what they contain and what the numbers mean.

## Result Bundle Structure

A benchmark produces a directory under `runs/<run-id>/` with three files:

```
runs/benchmark-20260301-120000/
  result.json       # Summary: recipe, model, dataset, metrics
  metrics.json      # Detailed metrics (per-window entries for rolling)
  provenance.json   # Reproducibility record (code version, input hashes)
```

## Understanding the Metrics

### MAE (Mean Absolute Error)

The average absolute difference between predicted and actual runtime, in seconds.

- **MAE = 300** means predictions are off by ~5 minutes on average
- **MAE = 3600** means predictions are off by ~1 hour on average
- Lower is better. The baseline model (global mean) sets the floor.

### RMSE (Root Mean Squared Error)

Like MAE but penalizes large errors more heavily. Always >= MAE.

- If RMSE is much larger than MAE, a few jobs have very large prediction errors
- If RMSE is close to MAE, errors are relatively uniform across jobs

### Comparing Models

Run the baseline first to establish a reference:
```bash
hpc-oda benchmark hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml
```

Then run the XGBoost model on the same data:
```bash
hpc-oda benchmark hpc_oda_commons/recipes/job-runtime/xgb_hourly_recent.yml
```

A useful model should achieve lower MAE and RMSE than the baseline. The baseline predicts the global mean runtime for every job, so any model that learns from job features should improve on it.

## Reading `result.json`

```json
{
  "schema_version": "oda.result.v0.1.0",
  "recipe_id": "recipe.job_runtime.baseline_tiny",
  "metrics": {"mae": 350.4, "rmse": 412.7},
  "model": {"id": "model.job_runtime_baseline", "version": "0.1.0"},
  "dataset": {
    "id": "...",
    "schema_version": "oda.job.v0.1.0",
    "hash": "e3b0c44..."
  }
}
```

- `metrics` -- the headline numbers to compare
- `dataset.hash` -- SHA-256 of the input Parquet file. Two results with the same hash used the same data.
- `model.id` + `model.version` -- exactly which model produced this result

## Reading `metrics.json` (Rolling)

For XGBoost rolling benchmarks, `metrics.json` contains per-window detail:

```json
{
  "mae": 280.5,
  "rmse": 340.2,
  "summary": {
    "windows_total": 1000,
    "windows_scored": 847,
    "windows_skipped": 153,
    "preprocessing_refits": 42,
    "rows_scored": 25340,
    "test_window_hours": 6
  },
  "windows": [
    {
      "split_time": "2026-01-15T08:00:00Z",
      "status": "ok",
      "metrics": {"mae": 195.3, "rmse": 245.1},
      "train_rows_supervised": 15200,
      "test_rows_supervised": 28
    }
  ]
}
```

- `windows_scored` vs `windows_skipped` -- some windows may lack enough data to train or test. A high skip rate suggests sparse data in parts of the evaluation window.
- `preprocessing_refits` -- the OHE/SVD pipeline is refit once per day. This count shows how many unique days were covered.
- Per-window `metrics` show how prediction quality varies over time. Large swings may indicate workload pattern changes.

## Reading `provenance.json`

```json
{
  "schema_versions": {"input": "oda.job.v0.1.0", "result": "oda.result.v0.1.0"},
  "environment": {"python": "3.12.1"},
  "code": {"package_version": "0.1.0", "git_commit": "abc123..."},
  "inputs": [{"path": "data.parquet", "sha256": "e3b0c44...", "size_bytes": 1048576}]
}
```

Use provenance to verify two results were produced under comparable conditions: same code version, same input data (matching SHA-256 hashes), same schema versions.

## Reading the Leaderboard

```bash
hpc-oda leaderboard --runs runs --out leaderboard
```

This produces `leaderboard.json` (machine-readable) and `index.html` (human-readable table). The leaderboard sorts all result bundles by creation time and shows recipe, model, dataset hash, and metrics side by side.

Open `index.html` in a browser to compare runs visually. Look for:
- Which model achieves the lowest MAE/RMSE
- Whether the same dataset hash was used across runs (apples-to-apples comparison)
- How metrics trend over time as models or data change

## Analysis Reports

```bash
hpc-oda analyze --data data/ingested/slurmctld/<run>
```

This produces `reports/analysis-<id>/analysis.json` and `index.html` with a quick baseline evaluation of your dataset. Use it as a sanity check before running full benchmarks.
