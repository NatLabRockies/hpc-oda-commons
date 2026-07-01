# slurmctld Adapter

This adapter parses slurmctld logs into `oda.job.v0.2.0` rows for runtime
prediction.

## Supported Patterns

- Allocate lines:
  - `Allocate JobId=<id> NodeList=<nodes> #CPUs=<n> Partition=<name>`
- Completion lines:
  - `_job_complete: JobId=<id> done`

## Output Fields

Required fields:
1. `job_id`
2. `start_time`
3. `end_time`
4. `runtime_seconds`

`start_time` and `end_time` are emitted as UTC `datetime` objects — native Arrow
`timestamp(us, tz=UTC)` values, not ISO-8601 strings.

Optional fields:
1. `allocated_cpus`
2. `partition`
3. `node_list`

## Limitations

- Incomplete jobs (missing start or end) are skipped to preserve schema validity.
- This parser is intentionally minimal.
