# hpc-oda-commons

A local-first CLI + standards toolkit for **HPC Operational Data Analytics (ODA)**, focused in v0.1 on
**SLURM job runtime prediction**.

Python: **3.9+**.

## What This Solves

HPC operational analytics is hard to compare across sites because data formats, ingestion pipelines, and
evaluation metrics vary. This repo standardizes the **artifacts**, **schemas**, and **benchmark recipes**
needed to run the same evaluation on different data sources.

## What This Repo Provides Today (v0.1)

A working, CLI-first vertical slice for **job runtime prediction**:

- **Find:** browse a bundled registry snapshot (`hpc-oda browse`, `hpc-oda info ...`)
- **Run:** ingest data and run a baseline locally (`hpc-oda ingest ...`, `hpc-oda analyze ...`)
- **Compare:** run a recipe-backed benchmark and generate a leaderboard (`hpc-oda benchmark ...`, `hpc-oda leaderboard ...`)

The stable surface area for v0.1 is the CLI (`hpc-oda`). Python APIs are minimal/experimental.

## Quickstart (10-minute workflow)

```bash
# Install (from a repo clone)
pip install -e ".[dev]"

# Initialize a project (creates .hpc_oda/, data/, runs/)
hpc-oda init

# Discover what's available (offline registry snapshot)
hpc-oda browse
hpc-oda info model.job_runtime_baseline

# Offline demo: generate a tiny synthetic dataset and run a deterministic baseline
HPC_ODA_OFFLINE=1 hpc-oda run-baseline

# Ingest option A: slurmctld logs
hpc-oda ingest slurmctld --path /path/to/slurmctld.log

# Ingest option B: jobs table exported as Parquet (interactive mapping wizard)
hpc-oda ingest jobs-parquet --path /path/to/jobs.parquet

# Validate Parquet rows + emit a quality report (*.parquet.quality.json)
hpc-oda validate data/ingested/slurmctld/<run>/data.parquet
# or:
hpc-oda validate data/ingested/jobs_parquet/<run>/data.parquet

# Analyze local data (baseline model) → reports/<id>/{analysis.json,index.html}
hpc-oda analyze --data data/ingested/slurmctld/<run>

# Benchmark a recipe (repo-local path)
HPC_ODA_OFFLINE=1 hpc-oda benchmark recipes/job-runtime/baseline_tiny.yml

# Benchmark the alternate XGBoost rolling-hourly recipe
HPC_ODA_OFFLINE=1 hpc-oda benchmark recipes/job-runtime/xgb_hourly_recent.yml
# Add -v/--verbose for progress updates during long rolling-hour runs
HPC_ODA_OFFLINE=1 hpc-oda benchmark -v recipes/job-runtime/xgb_hourly_recent.yml

# Generate a static leaderboard from runs/
hpc-oda leaderboard --runs runs --out leaderboard
```

For reproducible non-interactive jobs-parquet ingestion, reuse a mapping:

```bash
hpc-oda ingest jobs-parquet --path /path/to/jobs.parquet --mapping /path/to/mapping.yml
```

## What You Get (Artifacts)

| Command | Output |
| --- | --- |
| `hpc-oda ingest slurmctld ...` | `data/ingested/slurmctld/<run>/{data.parquet,manifest.json}` |
| `hpc-oda ingest jobs-parquet ...` | `data/ingested/jobs_parquet/<run>/{data.parquet,manifest.json,mapping.yml}` |
| `hpc-oda validate <parquet>` | `<parquet>.quality.json` |
| `hpc-oda run-baseline` | `runs/run-baseline-*/{result.json,metrics.json,provenance.json}` |
| `hpc-oda benchmark <recipe>` | `runs/benchmark-*/{result.json,metrics.json,provenance.json}` |
| `hpc-oda analyze --data ...` | `reports/analysis-*/{analysis.json,index.html}` |
| `hpc-oda leaderboard ...` | `leaderboard/{leaderboard.json,index.html}` |

## Offline Mode + Safety

- **Local-first:** ingestion and analysis run locally; this repo does not require shipping raw logs off-site.
- **Offline demos:** set `HPC_ODA_OFFLINE=1` to ensure workflows do not depend on network access.
- **Identifier handling:** the jobs-parquet ingest workflow can hash identifiers (e.g., `user`, `account`). If a
  mapping uses a salt, it can be provided via `HPC_ODA_HASH_SALT`.

## Repo Layout (Key Locations)

- `src/hpc_oda_commons/`: package implementation (CLI, schemas, adapters, models)
- `recipes/`: benchmark recipes (repo-local)
- `registry/`: source registry snapshot (synced into the package)
- `docs/`: user and contributor documentation
- `tests/`: unit + integration (“golden path”) tests
- `scripts/`: validation and release helpers

## Documentation

- Quickstart: `docs/how-to/quickstart.md`
- CLI reference: `docs/reference/cli.md`
- Ingest (slurmctld): `docs/how-to/ingest-slurmctld.md`
- Ingest (jobs parquet): `docs/how-to/ingest-jobs-parquet.md`
- Concepts (pillars): `docs/concepts/pillars.md`
- Concepts (artifacts): `docs/concepts/artifacts.md`
- Concepts (schema): `docs/concepts/schema.md`
- Concepts (benchmarks): `docs/concepts/benchmarks.md`
- Concepts (security): `docs/concepts/security-data-handling.md`
- Deep dive: `WHITEPAPER.md`
- Development process: `PROJECT_PLAN.md`

## Contributing

- Start here: `CONTRIBUTING.md`
- Code of Conduct: `CODE_OF_CONDUCT.md`
- Governance: `GOVERNANCE.md`
- Security: `SECURITY.md`
- Support: `SUPPORT.md`

## Citation

If you use this in academic work, please cite via `CITATION.cff`.
