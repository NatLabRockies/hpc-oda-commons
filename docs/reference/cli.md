# CLI Reference

This reference covers the v0.1 `hpc-oda` commands.

## Global
1. `hpc-oda --help` shows available commands.

## Project
1. `hpc-oda init`
   Creates `.hpc_oda/`, `data/`, and `runs/` in the current directory.

## Find
1. `hpc-oda browse [--tag <tag>] [--type <adapter|model|recipe>] [--source <source>] [--input-schema <id>] [--output-schema <id>]`
   Lists registry entries from the bundled snapshot. All flags are optional filters.
1. `hpc-oda info <entry_id>`
   Shows metadata and compatibility for a registry entry.

## Run
1. `hpc-oda run-baseline`
   Runs the offline baseline on the tiny synthetic dataset. Produces a result bundle under `runs/`.
1. `hpc-oda ingest slurmctld --path <log>`
   Parses a slurmctld log into `oda.job.v0.2.0` Parquet + manifest.
   Output: `data/ingested/slurmctld/<run>/`
1. `hpc-oda ingest jobs-parquet --path <parquet> [--mapping <yaml>] [--sample-rows <N>] [--batch-size <N>] [--non-interactive] [--hash-identifiers | --no-hash-identifiers]`
   Ingests a site-specific jobs Parquet file into canonical format.
   Without `--mapping`, launches an interactive wizard to build the mapping spec.
   With `--mapping`, applies the spec non-interactively.
   Output: `data/ingested/jobs_parquet/<run>/`
1. `hpc-oda analyze --data <parquet|dir> [--out <dir>]`
   Analyzes a local dataset with the baseline model and writes a report bundle
   containing `analysis.json` and `index.html`. Default output: `reports/`.
1. `hpc-oda validate <path>`
   Validates a result bundle, manifest, or parquet file. For parquet, writes a `*.quality.json` report.

## Embed
1. `hpc-oda embed <ingested.parquet> --out <embedded.parquet> [--model <id>] [--format prose|kv] [--config <local.yml>] [--cache-dir <dir>] [--device auto|cpu|cuda|mps] [--dtype fp16|fp32] [--batch-size <N>] [--chunk-size <N>] [--instruction <text>]`
   Serializes each job row to text (submission-time fields only) and encodes it, writing an
   embedded Parquet (original columns + a dense `embedding` column) plus a provenance
   manifest — the input for `model.job_runtime_embedding_knn`.
   `--model stub` uses a deterministic, dependency-free encoder (offline/CI); a real model
   (e.g. `microsoft/harrier-oss-v1-0.6b`, the recommended default) needs the `embed` extra
   (`pip install -e ".[embed]"`). Extra text columns (e.g. local job scripts) are named only
   in a local `--config` YAML so sensitive content stays off the command line. Embedding is
   chunk-cached and resumable via `--cache-dir`. See
   [Embedding-based kNN](../how-to/embedding-knn.md).

## Compare
1. `hpc-oda benchmark <recipe.yml> [--verbose|-v]`
   Runs a benchmark recipe and emits a result bundle under `runs/`.
   `--verbose` enables progress bar output for long-running benchmarks.
   Supported v0.1 model/split pairs:
   - `model.job_runtime_baseline` + `split.method: fixed`
   - `model.job_runtime_baseline` + `split.method: rolling`
   - `model.job_runtime_xgboost` + `split.method: rolling`
   - `model.job_runtime_random_forest` + `split.method: rolling`
   - `model.job_runtime_mlp` + `split.method: rolling`
   - `model.job_runtime_tfidf_knn` + `split.method: rolling`
   - `model.job_runtime_embedding_knn` + `split.method: rolling` (needs an `embedding` column; see `hpc-oda embed`)
   - `model.job_power_uopc` + `split.method: fixed`
   Result bundles include an `integrity` block with code hash and validation status.
   For rolling recipes, `split.n_windows` is required.
   Optional: `split.test_window_hours` (default `6`) sets the test window duration.
   Optional: `split.training_lookback_days` (default `100`) limits training rows
   to the previous `n` days before each split.

## Integrity
1. `hpc-oda record-hash`
   Records the current source code hash (SHA-256 of all `.py` files) and git commit
   in `integrity/known_hashes.json`. Run after tests pass on a clean commit to
   register it as validated. Benchmark results on validated code show `integrity.validated: true`.

## Leaderboard
1. `hpc-oda leaderboard --runs <dir> --out <dir>`
   Aggregates result bundles into `leaderboard.json` and `index.html`.
   The HTML table includes Validated and Code Hash columns for integrity verification.
