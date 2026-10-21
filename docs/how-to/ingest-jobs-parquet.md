# Ingest Jobs Parquet Exports

This workflow handles the common case where job data is a Parquet export from a database query (e.g., `sacct` output) rather than raw slurmctld logs. Its wizard is a quick way to look at an export and map it.

To benchmark your data, write a dataset descriptor instead: it ties the table to the exact export and works with every `hpc-oda datasets` command. See [Benchmark your own data](benchmark-your-data.md).

## Interactive Wizard

```bash
hpc-oda ingest jobs-parquet --path /path/to/jobs.parquet
```

The wizard:
1. **Profiles** your columns (data types, null rates, sample values)
2. **Suggests** mappings to canonical fields based on column name matching
3. **Asks** for timestamp format, duration units, and memory units for each mapped field
4. **Offers** identifier hashing for any mapped field (defaults to `user` and `account`)
5. **Writes** a reusable `mapping.yml` alongside the output

### Supported Transformations

| Type | Formats / units |
|------|----------------|
| Timestamp | `iso8601`, `epoch_s`, `epoch_ms`, `epoch_us` |
| Duration | `seconds`, `minutes`, `hours`, `HH:MM:SS`, `timedelta` (`"N days HH:MM:SS"`) |
| Memory | `bytes`, `KB`, `MB`, `GB`, `KiB`, `MiB`, `GiB`, or `slurm` for Slurm strings such as `160G` |
| Identifier | Hashed, salted with `HPC_ODA_HASH_SALT` when it is set. Any mapped field can be hashed. |

The wizard also offers a state filter after the mapping, to keep only some job states (such as
`COMPLETED` and `TIMEOUT`).

## Non-Interactive (Reuse Mapping)

```bash
hpc-oda ingest jobs-parquet --path /path/to/jobs.parquet --mapping mapping.yml --non-interactive
```

With `--mapping`, the wizard doesn't run. Without `--non-interactive`, it still asks about the
state filter when run in a terminal. `--non-interactive` never prompts, and fails without
`--mapping`. The [CLI reference](../reference/cli.md) lists every
option.

## Mapping Spec Example

The wizard produces a YAML file like this:

```yaml
schema_version: oda.mapping.v0.1.0
kind: jobs_parquet
output_schema_version: oda.job.v0.2.0
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

Each field takes the same options as a descriptor's mapping rule: `derive`, `null_values`,
`null_when`, and transform types including `energy`, `integer`, `number`, `list_mean` and
`list_max`. A mapping.yml names its source column `source:` and nests the type under
`transform:`, where a descriptor writes `from:` and `type:` on the rule itself.
[Dataset descriptors](../reference/descriptors.md#mapping-rules) explains each option.
`trim_quantiles` is for descriptors only.

Fields can be **sourced** from a column (`source:`) or **derived** from other fields (`derive:`). The `role` is either `required` (rows missing this field are skipped) or `optional`.

## Output

```text
data/ingested/jobs_parquet/<run>/
  data.parquet               # Canonical ODA table (oda.job.v0.2.0)
  data.parquet.quality.json  # Quality report
  manifest.json              # Transformation lineage
  mapping.yml                # Reusable mapping spec, written by the wizard only
```

In the canonical table, the `start_time`, `end_time`, and `submit_time` columns
are written as native Arrow `timestamp(us, tz=UTC)` values, not ISO-8601 strings.

## Validate

```bash
hpc-oda validate data/ingested/jobs_parquet/<run>/data.parquet
```

This checks the table against the schema again and rewrites `data.parquet.quality.json`.
