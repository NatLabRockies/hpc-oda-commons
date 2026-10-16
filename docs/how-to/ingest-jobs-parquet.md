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
4. **Offers** identifier hashing for any mapped field (defaults to `user` and `account`)
5. **Writes** a reusable `mapping.yml` alongside the output

### Supported Transformations

| Type | Formats / Units |
|------|----------------|
| Timestamp | `iso8601`, `epoch_s`, `epoch_ms`, `epoch_us` |
| Duration | `seconds`, `minutes`, `hours`, `HH:MM:SS` |
| Memory | `bytes`, `KB`, `MB`, `GB`, `KiB`, `MiB`, `GiB` |
| Memory (SLURM) | `slurm` -- parses SLURM-format strings like `160G`, `2366M`, `4096` → MiB |
| Identifier | SHA-256 hash with optional salt (via `HPC_ODA_HASH_SALT` env var). Can be applied to any mapped field. |

The wizard also offers an optional state filter after field mapping, allowing you to keep only specific job states (e.g., COMPLETED, TIMEOUT).

## Non-Interactive (Reuse Mapping)

```bash
hpc-oda ingest jobs-parquet --path /path/to/jobs.parquet --mapping mapping.yml
```

### Additional Flags

- `--sample-rows <N>` -- rows to sample for profiling (default: 200)
- `--batch-size <N>` -- rows per processing batch (default: 50,000)
- `--non-interactive` -- skip wizard prompts, use suggestions only
- `--hash-identifiers / --no-hash-identifiers` -- control default selection for identifier hashing (default: on, pre-selects `user` and `account`)

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

`derive` supports two forms: `end_time - start_time` (for `runtime_seconds`, filling it where
the source is missing) and `<field> / <field>`, a ratio of two other mapped fields, e.g.
`avgpcon_per_node: {derive: "avgpcon / num_nodes_alloc"}`; a zero or missing denominator
gives null. Any other expression is an error. (Before #204 an unrecognised expression was
ignored, leaving the column empty.) A ratio may use `runtime_seconds` or another ratio, in
any order in the mapping; a circular derive is an error (#206). For a column that holds a
list of samples per job, such as a power trace, `transform: {type: list_mean}` or
`{type: list_max}` reduces it to one number.

`transform: {type: energy, unit: wh}` converts energy to joules (`j`, `kj`, `wh`, `kwh`).
`null_values: [0]` on a field turns those source values into null before any transform, for
counters where a value means "no reading". The row is kept; only that field is null.
Together they give average power from an energy counter (NLR Eagle, #206):

```yaml
energy_joules: { from: node_energy_total_watt_hours, type: energy, unit: wh, null_values: [0] }
avgpcon: { derive: "energy_joules / runtime_seconds" }
avgpcon_per_node: { derive: "avgpcon / num_nodes_alloc" }
```

`null_when` nulls a field where a condition on another source column holds, and keeps the
row. It takes a list; any match nulls. Each condition names a `source` column and one of
`gt`, `ge`, `lt`, `le` (a number) or `in` (a list). A null source value matches nothing. For
example, Kestrel's Slurm energy is the whole node's when the node was shared, so it is not
the job's power (#209):

```yaml
energy_joules:
  from: consumed_energy_raw_joules
  type: energy
  unit: j
  null_values: [0]
  null_when:
    - { source: shared_job_count, ge: 1 }
    - { source: partition, in: [shared, shared-stdby, sharedl] }
```

Fields can be **sourced** from a column (`source:`) or **derived** from other fields (`derive:`). The `role` is either `required` (rows missing this field are skipped) or `optional`.

## Output

```text
data/ingested/jobs_parquet/<run>/
  data.parquet      # Canonical ODA table (oda.job.v0.2.0)
  manifest.json     # Transformation lineage
  mapping.yml       # Reusable mapping spec
```

In the canonical table, the `start_time`, `end_time`, and `submit_time` columns
are written as native Arrow `timestamp(us, tz=UTC)` values, not ISO-8601 strings.

## Validate

```bash
hpc-oda validate data/ingested/jobs_parquet/<run>/data.parquet
```

This writes a quality report to `data.parquet.quality.json`.
