# CLI Reference

This reference covers the v0.1 `hpc-oda` commands.

## Global
1. `hpc-oda --help` shows available commands.

## Project
1. `hpc-oda init`
   Creates `hpc-oda.toml`, `.hpc_oda/`, `data/`, and `runs/` in the current directory.

## Find
1. `hpc-oda browse --tag <tag> --type <adapter|model|recipe> --source <source>`
   Lists registry entries from the bundled snapshot.
1. `hpc-oda info <entry_id>`
   Shows metadata and compatibility for a registry entry.

## Run
1. `hpc-oda run-baseline`
   Runs the offline baseline on the tiny synthetic dataset.
1. `hpc-oda ingest slurmctld --path <log>`
   Parses a slurmctld log into `oda.job.v0.1.0` Parquet + manifest.
1. `hpc-oda analyze --data <parquet|dir> [--out <dir>]`
   Analyzes a local dataset with the baseline model and writes an analysis report.
1. `hpc-oda validate <path>`
   Validates a result bundle, manifest, or parquet file. For parquet, writes a `*.quality.json` report.

## Compare
1. `hpc-oda benchmark <recipe.yml> [--verbose|-v]`
   Runs a benchmark recipe and emits a result bundle under `runs/`.
   `--verbose` enables progress bar output for long-running benchmarks.
   Supported v0.1 model/split pairs:
   - `model.job_runtime_baseline` + `split.method: fixed`
   - `model.job_runtime_xgboost` + `split.method: rolling_hourly`
   For rolling-hourly recipes, `split.n_recent_hours` is required.
   Optional: `split.training_lookback_days` (default `100`) limits training rows
   to the previous `n` days before each split hour.

## Leaderboard
1. `hpc-oda leaderboard --runs <dir> --out <dir>`
   Aggregates result bundles into `leaderboard.json` and `index.html`.
