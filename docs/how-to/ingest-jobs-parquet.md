# Ingest Jobs Parquet Exports

This workflow handles the common case where job data is a Parquet export from a database query (e.g., `sacct` output) rather than raw slurmctld logs.

## Interactive Wizard

```bash
hpc-oda ingest jobs-parquet --path /path/to/jobs.parquet
```

The wizard:
1. **Profiles** your columns (data types, null rates, sample values)
2. **Suggests** mappings to canonical fields based on column name matching
3. **Asks** for timestamp format, duration units, and memory units for each mapped field
4. **Offers** identifier hashing for sensitive fields like `user` and `account`
5. **Writes** a reusable `mapping.yml` alongside the output

### Supported Transformations

| Type | Formats / Units |
|------|----------------|
| Timestamp | `iso8601`, `epoch_s`, `epoch_ms`, `epoch_us` |
| Duration | `seconds`, `minutes`, `hours`, `HH:MM:SS` |
| Memory | `bytes`, `KB`, `MB`, `GB`, `KiB`, `MiB`, `GiB` |
| Identifier | SHA-256 hash with optional salt (via `HPC_ODA_HASH_SALT` env var) |

## Non-Interactive (Reuse Mapping)

```bash
hpc-oda ingest jobs-parquet --path /path/to/jobs.parquet --mapping mapping.yml
```

### Additional Flags

- `--sample-rows <N>` -- rows to sample for profiling (default: 200)
- `--batch-size <N>` -- rows per processing batch (default: 50,000)
- `--non-interactive` -- skip wizard prompts, use suggestions only
- `--hash-identifiers / --no-hash-identifiers` -- control identifier hashing

## Mapping Spec Example

The wizard produces a YAML file like this:

```yaml
schema_version: oda.mapping.v0.1.0
kind: jobs_parquet
output_schema_version: oda.job.v0.1.0
fields:
  job_id:
    source: JobID
    role: required
  start_time:
    source: Start
    role: required
    transform:
      type: timestamp
      format: epoch_s
  end_time:
    source: End
    role: required
    transform:
      type: timestamp
      format: epoch_s
  runtime_seconds:
    derive: end_time - start_time
    role: required
  user:
    source: User
    role: optional
    transform:
      type: hash_identifier
      salt_env: HPC_ODA_HASH_SALT
  partition:
    source: Partition
    role: optional
```

Fields can be **sourced** from a column (`source:`) or **derived** from other fields (`derive:`). The `role` is either `required` (rows missing this field are skipped) or `optional`.

## Output

```
data/ingested/jobs_parquet/<run>/
  data.parquet      # Canonical ODA table (oda.job.v0.1.0)
  manifest.json     # Transformation lineage
  mapping.yml       # Reusable mapping spec
```

## Validate

```bash
hpc-oda validate data/ingested/jobs_parquet/<run>/data.parquet
```

This writes a quality report to `data.parquet.quality.json`.
