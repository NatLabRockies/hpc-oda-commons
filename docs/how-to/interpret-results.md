# Interpreting Results

After running `hpc-oda benchmark` or `hpc-oda analyze`, you'll have result artifacts. This guide explains what they contain and what the numbers mean.

## Result Bundle Structure

A benchmark writes a directory under its recipe's `run.output_dir` (default `runs/`) with three files:

```text
runs/benchmark-20260301-120000/
  result.json       # Summary: recipe, model, dataset, metrics
  metrics.json      # Detailed metrics (per-window entries for rolling)
  provenance.json   # Reproducibility record (code version, input hashes)
```

## Understanding the Metrics

Metrics are in the units of the recipe's target: seconds for `runtime_seconds`, watts per
node for `avgpcon_per_node` / `maxpcon_per_node` (see
[Predict job power](predict-power.md)). The examples below are for runtime.

### MAE (Mean Absolute Error)

The average absolute difference between predicted and actual runtime, in seconds.

- **MAE = 300** means predictions are off by ~5 minutes on average
- **MAE = 3600** means predictions are off by ~1 hour on average
- Lower is better. The baseline model, which predicts the training mean, is the reference to beat.

### RMSE (Root Mean Squared Error)

Like MAE but penalizes large errors more heavily. Always >= MAE.

- If RMSE is much larger than MAE, a few jobs have very large prediction errors
- If RMSE is close to MAE, errors are relatively uniform across jobs

### Comparing Models

Run the baseline first to establish a reference, then run other models on the same data with the same split. A useful model has lower MAE and RMSE than the baseline, which predicts the training mean for every job (in a rolling split, each window's mean).

The [model cards](../models/README.md) list the models, what each predicts and the splits it supports. Every model predicts the column its recipe's metrics target. With rolling UoPC, `summary.rows_fallback` in `metrics.json` counts test jobs whose
user had fewer than `k` training jobs; they were predicted with the window mean, so the row
counts match the other models'.

Use rolling evaluation with the same `n_windows`, `test_window_hours`, and `training_lookback_days` across all models for apples-to-apples comparison.

## Reading `result.json`

```json
{
  "schema_version": "oda.result.v0.1.0",
  "recipe_id": "recipe.job_runtime.baseline_tiny",
  "metrics": {"mae": 350.4, "rmse": 412.7},
  "model": {"id": "model.baseline", "version": "0.1.0"},
  "dataset": {
    "id": "...",
    "schema_version": "oda.job.v0.2.0",
    "hash": "e3b0c44..."
  },
  "integrity": {
    "code_hash": "abc123def456...",
    "validated": true,
    "git_commit": "def456abc123..."
  }
}
```

- `metrics` -- the headline numbers to compare
- `dataset.hash` -- SHA-256 of the input Parquet file. Two results with the same hash used the same data.
- `model.id` + `model.version` -- exactly which model produced this result
- `integrity.code_hash` -- SHA-256 of all `.py` files in the package. Two results with the same hash used identical code.
- `integrity.validated` -- `true` if the code hash matches a known-good commit registered via `hpc-oda record-hash`
- `integrity.git_commit` -- the checkout's commit, or null when the run's working directory isn't a git checkout. `hpc-oda benchmark` reads it and the code hash when the run starts, since the code a run executes is the code it imported then ([#215](https://github.com/NatLabRockies/hpc-oda-commons/issues/215))

## Reading `metrics.json` (Rolling)

For a rolling benchmark, `metrics.json` contains per-window detail:

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
- `preprocessing_refits` -- appears only for the rolling tabular models (XGBoost, MoE XGBoost, random forest, MLP, signature memorizer). The OHE/SVD pipeline is refit once per day, and this count shows how many unique days were covered.
- `preprocessing_store` -- `{"hits": n, "misses": m}`, for the same models when the benchmark runner's preprocessing store was in use. Hits are days whose OHE/SVD artifacts an earlier run on the same rows had already built; they change no result, only the run time ([preprocessing caches](../concepts/benchmarks.md#preprocessing-caches)).
- Per-window `metrics` show how prediction quality varies over time. Large swings may indicate workload pattern changes.

## Reading `provenance.json`

```json
{
  "schema_versions": {"input": "oda.job.v0.2.0", "result": "oda.result.v0.1.0"},
  "environment": {"python": "3.12.1"},
  "code": {"package_version": "0.1.0", "git_commit": "abc123...", "code_changed_during_run": false},
  "inputs": [{"path": "data.parquet", "sha256": "e3b0c44...", "size_bytes": 1048576}]
}
```

Use provenance to verify two results were produced under comparable conditions: same code version, same input data (matching SHA-256 hashes), same schema versions.

`code.code_changed_during_run` is `true` when the checkout's commit or code hash differed at the end of a benchmark from its start, for example after a merge during a long run. The bundle still records the code the run started with, which is the code it ran. A `true` here says the checkout moved, and the run should be checked or redone if that matters.

## Reading the Leaderboard

```bash
hpc-oda leaderboard --runs runs --out leaderboard
```

This writes three files:

- **`index.html`: one leaderboard per prediction target** (job runtime, average power, peak power), built like the MTEB leaderboard. Each row is a model, then its **Average**, then one column per dataset.
  - **Each cell is headroom captured**: (baseline MAE − model MAE) / (baseline MAE − floor MAE). The baseline is the window mean on that dataset, and the floor is the dataset's error ceiling (`docs/benchmarking/datasets/*.ceiling.json`). 0% means no better than the window mean, 100% reaches the floor, and a negative value (in red) is worse than the window mean.
  - **Headroom or MAE:** the *Show* toggle at the top switches every cell between the two. MAE can't be averaged across datasets, so the Average column shows only with headroom. Your browser remembers the choice.
  - **Names and links:** rows and columns show model and dataset titles. Each model links to its [card](../models/README.md), each dataset to its [card](../datasets/cards/README.md); hovering shows the id.
  - **Caveats:** a * on a column header marks a note about that dataset, or about the average; hover over it, or tab to it.
  - **Why not raw MAE:** it isn't comparable across datasets. Power per node differs several-fold between machines, and runtime errors differ as much. Within a dataset, headroom orders models exactly as MAE does.
  - **The average** covers every dataset in the table, and is shown only for models that ran on all of them. Otherwise the row says how many it ran ("3/4 datasets") and sits below the ranked rows.
  - **Headroom needs the same jobs.** A cell shows headroom only when its dataset's floor, its baseline and the cell itself cover the same jobs. Otherwise it shows the MAE alone, and hovering over it says why. Runtime cells use the walk-forward choice among lookback arms, scored past a 20-window burn-in ([error ceilings](../benchmarking/runtime/ceilings.md)).
- **`runs.html`: every result bundle, one row each.** This is for checking runs, not for ranking them. Each row says whether it counted on a leaderboard, and if not, why:
  - a study on another protocol, such as the UoPC paper reproduction;
  - no rolling split, as in a demo or smoke run;
  - a runtime dataset with no runtime card in `--ceilings`;
  - windows, window length or lookback other than the benchmark's;
  - a power recipe that isn't bundled and wasn't passed with `--recipes`;
  - a bundle run before its recipe changed;
  - a run replaced by a newer one.
- **`leaderboard.json`** (format `oda.leaderboard.v0.2.0`): `tables` per target, `excluded` with reasons, and the per-bundle `entries`.

Only runs on a target's own benchmark protocol count:

- **Power:** the bundled power recipes, and those in any folder passed with `--recipes`, on the [power protocol](../benchmarking/power/methodology.md#benchmark-configuration).
- **Runtime:** a dataset with a runtime card in `--ceilings`, on the [runtime protocol](../benchmarking/runtime/methodology.md#benchmark-configuration) and one of its lookbacks.

`--ceilings` points at the error ceilings and runtime cards (default `docs/benchmarking/datasets`). A cell with no ceiling still counts, and shows its MAE without headroom.

## Analysis Reports

```bash
hpc-oda analyze --data data/ingested/slurmctld/<run>
```

This produces `reports/analysis-<id>/analysis.json` and `index.html` with a quick baseline evaluation of your dataset. Use it as a sanity check before running full benchmarks.
