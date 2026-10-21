# Quickstart (v0.1) — SLURM Job Runtime Prediction

This quickstart walks through the end-to-end workflow for v0.1: ingest job data, validate it, benchmark models, and compare results.

## 1) Install

```bash
pip install -e ".[dev]"
```

## 2) Browse available components

```bash
hpc-oda browse
hpc-oda info model.baseline
```

## 3) Ingest your data

**Option A: Jobs Parquet export** (interactive wizard)
```bash
hpc-oda ingest jobs-parquet --path /path/to/jobs.parquet
```
The wizard previews your data, suggests column mappings, and asks for timestamp/duration/memory formats. It also offers to hash sensitive fields (user, account). Once complete, it writes a reusable `mapping.yml` alongside the output.

To replay a mapping non-interactively:
```bash
hpc-oda ingest jobs-parquet --path new_data.parquet \
  --mapping data/ingested/jobs_parquet/<prior-run>/mapping.yml \
  --non-interactive
```

**Option B: slurmctld logs**
```bash
hpc-oda ingest slurmctld --path /path/to/slurmctld.log
```

## 4) Validate ingested artifacts

```bash
hpc-oda validate data/ingested/jobs_parquet/<run>/data.parquet
```
Writes a quality report (`*.quality.json`) next to the parquet file with schema violations, semantic checks, and missingness statistics.

## 5) Benchmark

Run the offline baseline demo (no data required):
```bash
HPC_ODA_OFFLINE=1 hpc-oda run-baseline
```

Run a benchmark recipe against your ingested data — copy a bundled recipe and update the `dataset.table_path`:
```bash
cp src/hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml my_recipe.yml
# Edit my_recipe.yml: set table_path to your ingested parquet
hpc-oda benchmark my_recipe.yml
```

### Bundled models

| Model | Split method | Description |
|-------|-------------|-------------|
| `model.baseline` | `fixed` or `rolling` | Mean-prediction baseline |
| `model.xgboost` | `rolling` | XGBoost with automatic OHE+SVD categorical preprocessing |
| `model.random_forest` | `rolling` | Random forest with automatic OHE+SVD categorical preprocessing |
| `model.mlp` | `rolling` | Feed-forward MLP with automatic OHE+SVD categorical preprocessing |
| `model.tfidf_knn` | `rolling` | TF-IDF text vectorization + k-nearest-neighbor regression |
| `model.embedding_knn` | `rolling` | kNN over a precomputed dense embedding column (see `hpc-oda embed`) |
| `model.moe_xgboost` | `rolling` | Per-(user, wallclock-bin) XGBoost experts, routed inside the shared window |
| `model.uopc` | `fixed`, `cutoff` or `rolling` | Job power prediction via per-user kNN (UoPC); `cutoff` runs the paper protocol, `rolling` scores it on the shared windows |

Every runtime model can predict power instead by naming a power column as its metric target — see [Predict job power](predict-power.md).

The `xgboost`, `random_forest`, and `mlp` models share the tabular rolling
implementation in `models/rolling_tabular/` (see `RollingTabularModel`).

For rolling benchmarks, use `-v` for progress output:
```bash
hpc-oda benchmark -v my_recipe.yml
```

### Rolling split parameters

Adjust these in the recipe's `split:` section:
- `n_windows` — number of evaluation windows (default 1000)
- `test_window_hours` — hours per test window (default 6)
- `training_lookback_days` — training history limit (default 100)

## 6) Compare results

```bash
hpc-oda leaderboard --runs runs --out leaderboard
```
Aggregates the result bundles under `runs/` into `leaderboard.json`, `index.html` (one leaderboard per target) and `runs.html` (every bundle). The quickstart's tiny run is not a benchmark cell, so it appears on `runs.html` only ([reading the leaderboard](interpret-results.md#reading-the-leaderboard)).
