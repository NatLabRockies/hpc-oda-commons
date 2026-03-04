# hpc-oda-commons

**A community-driven platform for standardizing HPC operational data analytics.**

HPC sites generate enormous volumes of operational data — scheduler logs, accounting records, monitoring streams — but turning that data into actionable insight is needlessly hard. Each site builds bespoke parsers, schemas, and evaluation pipelines. Results can't be compared across institutions. Promising analytics ideas stay siloed because there's no shared language for describing the data, the experiments, or the outcomes.

hpc-oda-commons fixes this by establishing **community-governed contracts** — versioned schemas, canonical artifacts, and benchmark recipes — that make ODA workflows **discoverable**, **reproducible**, and **comparable**. It pairs these standards with a practical, CLI-first toolkit that lets operators and researchers go from raw logs to standardized results without sending data off-cluster.

## Design Principles

- **Artifacts are the interface.** Every stage of the pipeline reads and writes stable, versioned artifacts (Parquet tables, JSON manifests, result bundles). Standards live in the artifact contracts, not in any particular tool's internals.
- **Local-first.** Ingestion and analysis run entirely on your machine. No data is uploaded or transmitted. Transformation helpers (hashing, binning, redaction) let you sanitize artifacts before sharing.
- **Recipe-driven evaluation.** Benchmarks are defined by YAML recipes that fully specify dataset, model, metrics, and split strategy — so "running the same benchmark" actually means the same thing across sites.
- **Domain-extensible.** The platform is designed to support multiple ODA problem domains over time. v0.1 delivers job runtime prediction as the first complete vertical slice; future domains include energy/power prediction, queue wait time estimation, and more.

## The Three Pillars

| Pillar | Purpose | v0.1 commands |
|--------|---------|---------------|
| **Find** | Discover available models, adapters, recipes, and datasets from a community registry | `hpc-oda browse`, `hpc-oda info <id>` |
| **Run** | Ingest data, validate against schemas, and run local analysis | `hpc-oda init`, `hpc-oda ingest ...`, `hpc-oda validate ...`, `hpc-oda analyze ...` |
| **Compare** | Execute recipe-driven benchmarks and aggregate results into leaderboards | `hpc-oda benchmark <recipe>`, `hpc-oda leaderboard ...` |

Together, these let a site operator go from local logs to comparable, provenance-tracked results — and let a researcher publish results that others can actually reproduce.

---

## v0.1: Job Runtime Prediction

The first vertical slice delivers a complete end-to-end workflow for SLURM job runtime prediction.

**Python 3.9+**

### Quickstart

```bash
# Install from a repo clone
git clone <repo-url> && cd hpc-oda-commons
pip install -e ".[dev]"

# Initialize project directory structure
hpc-oda init

# Browse the offline registry
hpc-oda browse
hpc-oda info model.job_runtime_baseline

# Run a deterministic baseline on a bundled synthetic dataset (no network)
HPC_ODA_OFFLINE=1 hpc-oda run-baseline

# Benchmark using the v0.1 baseline recipe
HPC_ODA_OFFLINE=1 hpc-oda benchmark recipes/job-runtime/baseline_tiny.yml

# Generate a leaderboard from result bundles
hpc-oda leaderboard --runs runs --out leaderboard
```

### Ingest Your Own Data

hpc-oda-commons supports two ingestion paths:

**Option A: slurmctld logs**
```bash
hpc-oda ingest slurmctld --path /path/to/slurmctld.log
```

**Option B: any jobs table exported as Parquet** (interactive mapping wizard)
```bash
hpc-oda ingest jobs-parquet --path /path/to/jobs.parquet
```

The wizard walks you through mapping your columns to the canonical ODA schema. To replay a mapping non-interactively:
```bash
hpc-oda ingest jobs-parquet --path /path/to/jobs.parquet --mapping /path/to/mapping.yml
```

### Validate, Analyze, and Benchmark

```bash
# Validate ingested data and generate a quality report
hpc-oda validate data/ingested/slurmctld/<run>/data.parquet

# Run a baseline analysis → reports/<id>/{analysis.json, index.html}
hpc-oda analyze --data data/ingested/slurmctld/<run>

# Benchmark with the XGBoost rolling-hourly model
HPC_ODA_OFFLINE=1 hpc-oda benchmark recipes/job-runtime/xgb_hourly_recent.yml
# Use -v/--verbose for progress on long rolling-hourly runs
HPC_ODA_OFFLINE=1 hpc-oda benchmark -v recipes/job-runtime/xgb_hourly_recent.yml
```

### v0.1 Models

**Baseline** (`model.job_runtime_baseline`) — Deterministic mean-prediction model. Computes `mean(runtime_seconds)` on the training set and predicts that constant for all test rows. Fast, explainable, and useful as a floor for comparison.

**XGBoost** (`model.job_runtime_xgboost`) — Gradient-boosted tree model with automatic categorical preprocessing (one-hot encoding + SVD dimensionality reduction). Uses a daily preprocessing cache so OHE/SVD are only refit on day boundaries during rolling-hourly evaluation.

---

## Core Concepts

### Schemas

All artifacts are validated against versioned JSON Schemas following the pattern `oda.<type>.v<MAJOR>.<MINOR>.<PATCH>`:

| Schema | Purpose |
|--------|---------|
| `oda.job.v0.1.0` | Canonical job record (the rows in an ODA table) |
| `oda.result.v0.1.0` | Benchmark result bundle |
| `oda.recipe.v0.1.0` | Benchmark recipe definition |
| `oda.manifest.v0.1.0` | Ingest provenance manifest |
| `oda.mapping.v0.1.0` | Field mapping specification |
| `oda.registry.v0.1.0` | Registry snapshot |
| `oda.mdl.v0.1.0` | Metric definition |

Schema changes are proposed through a **Schema Evolution Request (SER)** — see `CONTRIBUTING.md`. During v0.1 the core job schema is frozen except for non-breaking fixes.

### Artifacts

The pipeline produces four types of artifacts:

**ODA Table** — A Parquet file of job records conforming to the domain's schema (e.g., `oda.job.v0.1.0`). This is the primary input for validation, analysis, and benchmarks.

**Manifest** — JSON written alongside each ingested Parquet file. Captures the adapter used, inputs, transformations applied, and provenance (including content hashes).

**Result Bundle** — A directory produced by benchmarks and baseline runs containing `result.json`, `metrics.json`, and `provenance.json`. Result bundles are the input to leaderboard generation.

**Quality Report** — JSON written by `hpc-oda validate`, recording schema violations, semantic checks (e.g., negative runtimes, inverted timestamps), and missingness statistics.

### Benchmark Recipes

Recipes are YAML files that fully specify a reproducible evaluation:

```yaml
recipe_id: recipe.job_runtime.baseline_tiny
problem_domain: [job-runtime-prediction]
schema_version: oda.job.v0.1.0

dataset:
  id: hpc_oda_commons/datasets/synthetic/job-runtime/tiny
  table_path: <path-to-parquet>

model:
  id: model.job_runtime_baseline
  version: "0.1.0"

metrics:
  - name: mae
    target: runtime_seconds
  - name: rmse
    target: runtime_seconds

split:
  method: fixed          # or rolling_hourly
  train_fraction: 0.8
  seed: 42

run:
  output_dir: runs
  overwrite: false
```

v0.1 supports two split methods:
- **`fixed`** — deterministic train/test split (used with the baseline model)
- **`rolling_hourly`** — sliding-window evaluation that simulates production retraining (used with XGBoost). Parameters: `n_recent_hours`, `training_lookback_days`

### Provenance

Every result bundle includes `provenance.json` capturing:
- Schema versions used
- Python version and installed packages (`pip freeze`)
- Package version and git commit
- SHA-256 hashes and sizes of input files

This enables full traceability: a leaderboard entry can trace back to exactly what ran, on what data, and in what environment.

### Data Privacy

For sharing derived artifacts, the toolkit provides deterministic transformation helpers:
- `hash_identifier(value, salt=...)` — pseudonymize user/account identifiers (salt via `HPC_ODA_HASH_SALT`)
- `bin_timestamp(value, interval_seconds=...)` — reduce timestamp precision
- `redact_value(value, replacement=...)` — remove or replace sensitive values

All transformations are recorded in the manifest's transformation ledger.

## Artifact Output Paths

| Command | Output |
|---------|--------|
| `hpc-oda ingest slurmctld ...` | `data/ingested/slurmctld/<run>/{data.parquet, manifest.json}` |
| `hpc-oda ingest jobs-parquet ...` | `data/ingested/jobs_parquet/<run>/{data.parquet, manifest.json, mapping.yml}` |
| `hpc-oda validate <parquet>` | `<parquet>.quality.json` |
| `hpc-oda run-baseline` | `runs/run-baseline-*/{result.json, metrics.json, provenance.json}` |
| `hpc-oda benchmark <recipe>` | `runs/benchmark-*/{result.json, metrics.json, provenance.json}` |
| `hpc-oda analyze --data ...` | `reports/analysis-*/{analysis.json, index.html}` |
| `hpc-oda leaderboard ...` | `leaderboard/{leaderboard.json, index.html}` |

## Repo Layout

```
src/hpc_oda_commons/     Package implementation
  qst/                   CLI (Typer-based, entry point: hpc-oda)
  kernel/                Core: artifacts, provenance, validation, schemas
  models/                Baseline and XGBoost runtime models
  adapters/              Source parsers (slurmctld)
  ingest/                Data ingestion pipeline (profile, suggest, wizard, apply)
  benchmark/             Recipe loading and results aggregation
  intelligence/          Mapping suggestions, metadata graph, synthetic scoring
  schema/                JSON Schema validation and quality rules
  schemas/               Bundled JSON Schema files
  datasets/              Bundled synthetic datasets
  registry/              Offline registry snapshot
  tools/                 HTML report generation
recipes/                 Benchmark recipes (YAML)
tests/                   Unit + integration tests
docs/                    User and contributor documentation
scripts/                 Validation and release helpers
```

## Documentation

- **How-to guides:** `docs/how-to/quickstart.md`, `ingest-slurmctld.md`, `ingest-jobs-parquet.md`
- **Concepts:** `docs/concepts/` — pillars, artifacts, schema, benchmarks, security
- **CLI reference:** `docs/reference/cli.md`
- **Deep dive:** `WHITEPAPER.md`

## Contributing

See `CONTRIBUTING.md` for branching conventions, code style (Ruff), testing expectations, and the Schema Evolution Request process.

## Citation

If you use this in academic work, please cite via `CITATION.cff`.
