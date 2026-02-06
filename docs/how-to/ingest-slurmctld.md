# Ingest slurmctld

## Command
```bash
hpc-oda ingest slurmctld --path /path/to/slurmctld.log
```

## Output
1. Parquet: `data/ingested/slurmctld/<run>/data.parquet`
2. Manifest: `data/ingested/slurmctld/<run>/manifest.json`

## Ingest checks

hpc-oda performs deterministic ingest checks and prints warnings when required
fields are missing or timestamps look inconsistent.

## Validate
```bash
hpc-oda validate data/ingested/slurmctld/<run>/data.parquet
```
