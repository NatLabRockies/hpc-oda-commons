# Interpreting Results

After running `hpc-oda benchmark` or `hpc-oda analyze`, you'll have result artifacts. This guide explains what they contain and what the numbers mean.

## Result Bundle Structure

A benchmark produces a directory under `runs/<run-id>/` with three files:

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
- Lower is better. The baseline model (global mean) sets the floor.

### RMSE (Root Mean Squared Error)

Like MAE but penalizes large errors more heavily. Always >= MAE.

- If RMSE is much larger than MAE, a few jobs have very large prediction errors
- If RMSE is close to MAE, errors are relatively uniform across jobs

### Comparing Models

Run the baseline first to establish a reference, then run alternate models on the same data using the same rolling split parameters. A useful model should achieve lower MAE and RMSE than the baseline, which predicts the global mean runtime for every job.

The toolkit ships eight models -- seven for job runtime and one for job power:
- `model.baseline` -- mean predictor (supports fixed and rolling splits)
- `model.xgboost` -- gradient-boosted trees with OHE+SVD preprocessing
- `model.random_forest` -- random forest with OHE+SVD preprocessing
- `model.mlp` -- feed-forward MLP with OHE+SVD preprocessing
- `model.tfidf_knn` -- text similarity via TF-IDF + k-nearest neighbors
- `model.embedding_knn` -- kNN over precomputed dense embeddings (see `hpc-oda embed`)
- `model.moe_xgboost` -- per-(user, wallclock-bin) XGBoost experts routed inside the shared rolling window
- `model.uopc` -- job power prediction via per-user kNN (fixed split, the paper protocol with a cutoff split, or the shared rolling windows; see `docs/benchmarking/power/uopc.md`)

Every runtime model can also predict power: the recipe's metric target is the column it
predicts. With rolling UoPC, `summary.rows_fallback` in `metrics.json` counts test jobs whose
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
- `integrity.git_commit` -- the checkout's commit. `hpc-oda benchmark` reads it and the code hash when the run starts, since the code a run executes is the code it imported then ([#215](https://github.com/NatLabRockies/hpc-oda-commons/issues/215))

## Reading `metrics.json` (Rolling)

For rolling benchmarks (baseline, XGBoost, random forest, MLP, TF-IDF kNN, or embedding kNN), `metrics.json` contains per-window detail:

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
- `preprocessing_refits` -- appears only for the tabular rolling models (`xgboost`, `random_forest`, `mlp`), not the baseline or TF-IDF kNN rolling summaries. The OHE/SVD pipeline is refit once per day, and this count shows how many unique days were covered.
- `preprocessing_store` -- `{"hits": n, "misses": m}`, for the tabular rolling models when the benchmark runner's preprocessing store was in use. Hits are days whose OHE/SVD artifacts an earlier run on the same rows had already built; they change no result, only the run time ([reference](../hpc-oda-commons-reference.md)).
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
  - **Why not raw MAE:** it isn't comparable across datasets. A Fugaku node draws ~90 W and a Kestrel node ~590 W, and runtime errors differ as much between machines. Within a dataset, headroom orders models exactly as MAE does.
  - **The average** covers every dataset in the table, and is shown only for models that ran on all of them. Otherwise the row says how many it ran ("3/4 datasets") and sits below the ranked rows.
  - **Headroom needs the same jobs.** A cell shows headroom only when its dataset's floor, its baseline and the cell itself cover the same jobs. Otherwise it shows the MAE alone, and hovering over it says why. Runtime cells use the walk-forward choice among lookback arms, scored past a 20-window burn-in, on the 30-day fleet that has run ([methodology](../benchmarking/runtime/methodology.md#calibrating-the-numbers-the-error-ceiling)).
- **`runs.html`: every result bundle, one row each.** This is for checking runs, not for ranking them. Each row says whether it counted on a leaderboard, and if not, why: another protocol (the UoPC paper reproduction), a smoke run, an ad hoc recipe, a bundle run before its recipe changed, or one replaced by a newer run.
- **`leaderboard.json`** (format `oda.leaderboard.v0.2.0`): `tables` per target, `excluded` with reasons, and the per-bundle `entries`.

Only runs of a target's own benchmark protocol count: for power, the bundled `recipes/job-power/*_rolling_*.yml` on 89 × 24 h windows with a 60-day lookback; for runtime, the `bench-matrix` configuration. `--ceilings` points at the ceilings and dataset cards (default `docs/benchmarking/datasets`).

## Analysis Reports

```bash
hpc-oda analyze --data data/ingested/slurmctld/<run>
```

This produces `reports/analysis-<id>/analysis.json` and `index.html` with a quick baseline evaluation of your dataset. Use it as a sanity check before running full benchmarks.
