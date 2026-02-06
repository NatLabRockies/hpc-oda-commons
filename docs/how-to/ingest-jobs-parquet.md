# Ingest jobs Parquet exports

This workflow supports the common case where job data is available as a Parquet export
from a database query rather than raw `slurmctld` logs.

## Command (interactive wizard)

```bash
hpc-oda ingest jobs-parquet --path /path/to/jobs.parquet
```

The wizard will:
- inspect columns and suggest mappings
- ask for timestamp and duration units
- optionally hash identifiers such as `user` and `account`
- write a reusable `mapping.yml`

## Command (non-interactive, reuse mapping)

```bash
hpc-oda ingest jobs-parquet --path /path/to/jobs.parquet --mapping mapping.yml
```

## Output

1. Parquet: `data/ingested/jobs_parquet/<run>/data.parquet`
2. Manifest: `data/ingested/jobs_parquet/<run>/manifest.json`
3. Mapping: `data/ingested/jobs_parquet/<run>/mapping.yml`

## Validate

```bash
hpc-oda validate data/ingested/jobs_parquet/<run>/data.parquet
```

This writes a quality report next to the parquet file:
`data/ingested/jobs_parquet/<run>/data.parquet.quality.json`.
