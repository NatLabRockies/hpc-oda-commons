# Quickstart (v0.1) — SLURM Job Runtime Prediction

This quickstart is the canonical 10-minute workflow for v0.1.

> Docs Sync Rule: If any CLI command names, flags, or output paths change, update this doc and the README quickstart.

## 1) Install (editable)

```bash
pip install -e ".[dev]"
```
## 2) Initialize a project
```bash
hpc-oda init
```

## 3) Browse available components (offline)
```bash
hpc-oda browse
hpc-oda info model.job_runtime_baseline
```

## 4) Run the offline baseline demo (no network)
```bash
HPC_ODA_OFFLINE=1 hpc-oda run-baseline
```

## 5) Ingest slurmctld logs
```bash
hpc-oda ingest slurmctld --path /path/to/slurmctld.log
```

## 6) Validate ingested artifacts
```bash
hpc-oda validate data/ingested/slurmctld/<run>/data.parquet
```
This writes a quality report next to the parquet file:
`data/ingested/slurmctld/<run>/data.parquet.quality.json`.

## 7) Analyze local data (baseline)
```bash
hpc-oda analyze --data data/ingested/slurmctld/<run>
```

## 8) Benchmark using the v0.1 recipe
```bash
HPC_ODA_OFFLINE=1 hpc-oda benchmark hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml
```

## 9) Generate a local leaderboard
```bash
hpc-oda leaderboard --runs runs --out leaderboard
```
