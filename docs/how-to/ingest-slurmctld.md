# Ingest slurmctld Logs

## Supported Log Format

The adapter recognizes two slurmctld log patterns:

```text
[2026-01-01T00:00:00.000] sched: Allocate JobId=1001 NodeList=node01 #CPUs=4 Partition=debug
[2026-01-01T00:00:05.000] _job_complete: JobId=1001 done
```

- **Allocate** lines record the job start: `job_id`, `start_time`, `allocated_cpus`, `partition`, `node_list`
- **_job_complete** lines record the job end: `job_id`, `end_time`
- `runtime_seconds` is computed as `end_time - start_time`
- Jobs missing either an Allocate or _job_complete event are skipped

## Command

```bash
hpc-oda ingest slurmctld --path /path/to/slurmctld.log
```

## Example Output

The command validates the ingested table, prints any ingest-check warnings, and
reports where the run was written. For a clean log with no schema, semantic, or
ingest-check issues:

```text
Validation summary: no schema or semantic issues detected.
Ingest complete → data/ingested/slurmctld/slurmctld-20260301-120000
```

If validation finds problems, the summary line reports the counts and lists the
offending rows, and any ingest checks are printed as `Ingest check: <message>`
lines before the final `Ingest complete → ...` line.

## Output Directory

```text
data/ingested/slurmctld/<run>/
  data.parquet      # Canonical ODA table (oda.job.v0.2.0)
  manifest.json     # Transformation lineage (oda.manifest.v0.1.0)
```

## Validate

```bash
hpc-oda validate data/ingested/slurmctld/<run>/data.parquet
```

This runs schema validation and semantic checks (negative runtimes, timestamp ordering) and writes a quality report to `data.parquet.quality.json`.

## Ingest Checks

The adapter performs deterministic checks and prints warnings when:
- Required fields are missing (`job_id`, `start_time`, `end_time`, `runtime_seconds`)
- Timestamps are unparseable or inconsistent (`start_time > end_time`)
- No jobs were parsed (empty or unrecognized log format)
