# Agent Usage Guide

Instructions for AI agents **using** hpc-oda-commons as a tool. If you are
*developing* hpc-oda-commons (changing its code), see
[`CONTRIBUTING.md`](../CONTRIBUTING.md) and
[`docs/architecture.md`](architecture.md) instead.

## Project Overview

**hpc-oda-commons** is a local-first CLI + standards toolkit for HPC Operational Data Analytics (ODA). v0.1 focuses on SLURM job runtime prediction: discovering, ingesting, analyzing, and benchmarking runtime prediction models across HPC sites.

## Installation

```bash
pip install -e ".[dev]"
```

## Workflow

The typical workflow is: **ingest -> validate -> benchmark -> leaderboard**. Every command runs locally with no network required.

```bash
# 1. Ingest data (pick one)
hpc-oda ingest jobs-parquet --path /path/to/jobs.parquet  # interactive wizard
hpc-oda ingest slurmctld --path /path/to/slurmctld.log

# 2. Validate ingested data
hpc-oda validate data/ingested/jobs_parquet/<run>/data.parquet

# 3. Run a benchmark
hpc-oda benchmark my_recipe.yml

# 4. Compare results
hpc-oda leaderboard --runs runs --out leaderboard
```

## Key Commands

| Command | What it does | Output location |
|---------|-------------|-----------------|
| `hpc-oda ingest jobs-parquet --path <parquet>` | Transform Parquet with interactive wizard | `data/ingested/jobs_parquet/<run>/` |
| `hpc-oda ingest slurmctld --path <log>` | Parse slurmctld logs to canonical Parquet | `data/ingested/slurmctld/<run>/` |
| `hpc-oda validate <path>` | Validate artifacts against schemas | `*.quality.json` next to input |
| `hpc-oda analyze --data <path>` | Quick baseline analysis with HTML report | `reports/analysis-<id>/` |
| `hpc-oda benchmark <recipe.yml>` | Run a benchmark recipe | `runs/benchmark-<timestamp>/` |
| `hpc-oda benchmark -v <recipe.yml>` | Benchmark with verbose progress | Same, with console output |
| `hpc-oda leaderboard --runs <dir> --out <dir>` | Aggregate results into comparison table | `leaderboard.json` + `index.html` |
| `hpc-oda record-hash` | Record source hash for current git commit | `integrity/known_hashes.json` |
| `hpc-oda browse` | List registry entries (adapters, models, recipes) | Console output |
| `hpc-oda info <entry_id>` | Show metadata for a registry entry | Console output |

## Recipes

Bundled recipes are at `src/hpc_oda_commons/recipes/job-runtime/`:
- `baseline_tiny.yml` -- baseline model, fixed 80/20 split (fast, good for smoke tests)
- `xgb_hourly_recent.yml` -- XGBoost, rolling evaluation (slower, production-realistic)
- `alt_model_example.yml` -- XGBoost with smaller window (faster iteration)
- `mlp_rolling.yml` -- feed-forward neural network, rolling evaluation
- `uopc_maxpcon.yml` -- UoPC user-based power prediction, fixed chronological split

v0.1 models:
- `model.job_runtime_baseline` -- mean predictor (supports fixed and rolling splits)
- `model.job_runtime_xgboost` -- XGBoost with OHE+SVD preprocessing (rolling splits)
- `model.job_runtime_tfidf_knn` -- TF-IDF text vectorization + kNN regression (rolling splits)
- `model.job_runtime_random_forest` -- Random Forest, uses the shared `rolling_tabular` OHE+SVD preprocessing (rolling splits)
- `model.job_runtime_mlp` -- feed-forward neural network, uses the shared `rolling_tabular` preprocessing (rolling splits)
- `model.job_power_uopc` -- user-based online power prediction (UoPC), per-user kNN (fixed chronological split)

To create a custom recipe, copy a bundled one and modify the dataset path, split parameters, or model selection:
```bash
cp src/hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml my_recipe.yml
# Edit my_recipe.yml
hpc-oda benchmark my_recipe.yml
```

## Ingesting Parquet Data

The jobs-parquet ingest uses an interactive wizard that profiles columns, suggests mappings, and asks for timestamp/duration/memory formats. Agents should prompt the user to run it interactively:

```bash
hpc-oda ingest jobs-parquet --path /path/to/jobs.parquet
```

The wizard will:
1. Show a preview of the input Parquet (columns, types, sample values)
2. For each canonical field, suggest a source column and ask for confirmation
3. Ask for timestamp formats (iso8601, epoch_s, etc.) and duration units (seconds, minutes, etc.)
4. For memory fields, accept a fixed unit (MB, GB, etc.) or `slurm` to parse SLURM-format strings like `160G`
5. Offer to hash sensitive fields (user, account, or any mapped field)
6. Optionally filter rows by job state (e.g., keep only COMPLETED and TIMEOUT)
7. Write a reusable `mapping.yml` alongside the output

Once a mapping exists, subsequent ingests can be fully automated:
```bash
hpc-oda ingest jobs-parquet --path new_data.parquet --mapping data/ingested/jobs_parquet/<prior-run>/mapping.yml --non-interactive
```

See `docs/how-to/ingest-jobs-parquet.md` for the full mapping spec format and supported transformations.

## Reading Results

A benchmark produces three files in `runs/<run-id>/`:
- `result.json` -- headline metrics (MAE, RMSE), model/dataset metadata, integrity, provenance
- `metrics.json` -- detailed per-window metrics (for rolling benchmarks)
- `provenance.json` -- Python version, package versions, input file hashes, git commit, source hash

The key fields in `result.json`:
```json
{
  "metrics": {"mae": 350.4, "rmse": 412.7},
  "model": {"id": "model.job_runtime_baseline", "version": "0.1.0"},
  "dataset": {"hash": "e3b0c44..."},
  "integrity": {"code_hash": "abc123...", "validated": true, "git_commit": "def456..."}
}
```

Two results with the same `dataset.hash` used the same input data. Two results with the same `integrity.code_hash` and `validated: true` used identical, test-validated code. Both conditions together mean the results are fully comparable.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `HPC_ODA_OFFLINE` | Set to `1` for offline mode (required for integration tests) |
| `HPC_ODA_HASH_SALT` | Salt for identifier hashing during ingestion |

## Output Paths

All output directories are gitignored:
- `data/ingested/<adapter>/<run_id>/` -- Parquet table, manifest, quality report
- `runs/<run_id>/` -- Result bundle (result.json, metrics.json, provenance.json)
- `reports/analysis-<id>/` -- Analysis report (JSON + HTML)
- `leaderboard/` -- Leaderboard output (leaderboard.json + index.html)
