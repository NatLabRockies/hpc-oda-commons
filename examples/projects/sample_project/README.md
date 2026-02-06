# Sample Project

This directory mirrors the structure created by `hpc-oda init`.

Typical workflow:
1. `hpc-oda init`
2. `hpc-oda ingest slurmctld --path <log>`
3. `hpc-oda validate data/ingested/slurmctld/<run>/data.parquet`
4. `hpc-oda analyze --data data/ingested/slurmctld/<run>`
5. `HPC_ODA_OFFLINE=1 hpc-oda benchmark hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml`
