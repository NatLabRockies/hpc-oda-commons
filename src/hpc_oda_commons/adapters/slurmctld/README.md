# slurmctld Adapter

This adapter parses slurmctld logs into `oda.job.v0.1.0` rows for runtime
prediction.

## Supported Patterns (v0.1)

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

Optional fields:
1. `allocated_cpus`
2. `partition`
3. `node_list`

## Limitations

- Incomplete jobs (missing start or end) are skipped to preserve schema validity.
- This parser is intentionally minimal for v0.1.
