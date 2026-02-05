# hpc-oda-commons Docs

Welcome to the documentation for **hpc-oda-commons**. v0.1 focuses on a vertical slice for SLURM job runtime prediction.

## Quick Links
1. Quickstart: `docs/how-to/quickstart.md`
2. CLI reference: `docs/reference/cli.md`
3. Schema overview: `docs/concepts/schema.md`
4. Benchmarks: `docs/concepts/benchmarks.md`

## 10-minute Workflow (v0.1)
1. Install: `pip install -e ".[dev]"`
2. Initialize: `hpc-oda init`
3. Browse: `hpc-oda browse`
4. Run baseline: `HPC_ODA_OFFLINE=1 hpc-oda run-baseline`
5. Ingest logs: `hpc-oda ingest slurmctld --path /path/to/slurmctld.log`
6. Validate data: `hpc-oda validate data/ingested/slurmctld/<run>/data.parquet`
7. Benchmark: `HPC_ODA_OFFLINE=1 hpc-oda benchmark recipes/job-runtime/baseline_tiny.yml`
8. Leaderboard: `hpc-oda leaderboard --runs runs --out leaderboard`
