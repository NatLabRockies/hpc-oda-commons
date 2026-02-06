# Pillars

The v0.1 implementation maps directly to the three pillars.

## Find

Offline registry snapshot in `registry/snapshot.json`.

CLI commands:
1. `hpc-oda browse`
2. `hpc-oda info <entry_id>`

## Compare

Benchmark recipes live in `recipes/` and produce canonical result bundles.

CLI command:
1. `hpc-oda benchmark <recipe.yml>`

## Run

Local-first ingestion, validation, and analysis.

CLI commands:
1. `hpc-oda ingest slurmctld --path <log>`
2. `hpc-oda validate <path>`
3. `hpc-oda run-baseline`
4. `hpc-oda analyze --data <parquet|dir>`

Together, these allow a site operator to go from local logs to comparable
results without sending data off-cluster.
