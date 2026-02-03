# Quickstart (v0.1) — SLURM Job Runtime Prediction

This quickstart is the canonical 10-minute workflow for v0.1.

> Docs Sync Rule: If any CLI command names, flags, or output paths change, update this doc and the README quickstart.

## 1) Install (editable)

```bash
pip install -e ".[dev]"
```
## 2) Initialize a project
hpc-oda init

## 3) Browse available components (offline)
hpc-oda browse
hpc-oda info model.job_runtime_baseline

## 4) Run the offline baseline demo (no network)
HPC_ODA_OFFLINE=1 hpc-oda run-baseline

## 5) Ingest slurmctld logs
hpc-oda ingest slurmctld --path /path/to/slurmctld.log

## 6) Validate ingested artifacts
hpc-oda validate data/ingested/slurmctld/<run>/data.parquet

## 7) Benchmark using the v0.1 recipe
HPC_ODA_OFFLINE=1 hpc-oda benchmark recipes/job-runtime/baseline_tiny.yml