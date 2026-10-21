# CLI Reference

This reference covers the v0.1 `hpc-oda` commands.

## Global
1. `hpc-oda --help` shows available commands.

## Project
1. `hpc-oda init`
   Creates `.hpc_oda/`, `data/`, and `runs/` in the current directory.

## Find
1. `hpc-oda browse [--tag <tag>] [--type <adapter|model|recipe>] [--source <source>] [--input-schema <id>] [--output-schema <id>]`
   Lists registry entries: the package's adapters, models, recipes and datasets. All flags are optional filters.
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
   manifest — the input for `model.embedding_knn`.
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
   - `model.baseline` + `split.method: fixed`
   - `model.baseline` + `split.method: rolling`
   - `model.xgboost` + `split.method: rolling`
   - `model.random_forest` + `split.method: rolling`
   - `model.mlp` + `split.method: rolling`
   - `model.tfidf_knn` + `split.method: rolling`
   - `model.embedding_knn` + `split.method: rolling` (needs an `embedding` column; see `hpc-oda embed`)
   - `model.moe_xgboost` + `split.method: rolling`
   - `model.uopc` + `split.method: fixed`
   - `model.uopc` + `split.method: cutoff` (the UoPC paper protocol; see `docs/benchmarking/power/uopc.md`)
   - `model.uopc` + `split.method: rolling` (UoPC on the shared rolling windows; see `docs/how-to/predict-power.md`)
   The model predicts the column the recipe's metrics target (`runtime_seconds` by default); a model that cannot predict it fails the run.
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

## Datasets and recipes
1. `hpc-oda datasets prepare <descriptor.yml> [--from <dir>]`
   Fetches (or, for a `manual` source, copies from `--from`) and checksums a dataset's
   files, then writes its prepared table, manifest and quality report.
1. `hpc-oda datasets characterize <table> --out <dir> [--pin-end YYYY-MM-DD]`
   Writes the dataset's runtime card: its characterization and runtime window. `--pin-end`
   keeps a window a benchmark already ran on.
1. `hpc-oda datasets ceiling <table> --dataset-id <id> [--target <col>] [--start --end --by --require-nonnull]`
   Writes an error ceiling: the lowest error any submit-time predictor could reach.
1. `hpc-oda recipes write <descriptor.yml> --out <dir> [--card <card.json>] [--start --end --by --require-nonnull] [--model <name>]`
   Writes every model's recipes for a dataset on the benchmark's protocol, and prints the
   embedding and ceiling commands that go with them
   ([Benchmark your own data](../how-to/benchmark-your-data.md)).
1. `hpc-oda datasets cards [--descriptors <dir> --benchmark-dir <dir> --recipes <dir> --leaderboard <json>] [--out <dir>]`
   Writes a card for each dataset: the bundled ones by default, or the descriptors in
   `--descriptors`.

## Leaderboard
1. `hpc-oda leaderboard --runs <dir> --out <dir> [--recipes <dir>]`
   Writes `index.html` (one leaderboard per prediction target: a row per model, headroom
   per dataset, an average), `runs.html` (every bundle, and why any was not counted) and
   `leaderboard.json`. `--ceilings <dir>` points at the error ceilings and dataset cards
   (default `docs/benchmarking/datasets`). `--recipes <dir>` counts power runs from recipes
   that `hpc-oda recipes write` wrote. See
   [Reading the leaderboard](../how-to/interpret-results.md#reading-the-leaderboard).
