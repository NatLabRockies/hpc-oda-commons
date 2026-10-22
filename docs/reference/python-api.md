# Python API

Most of hpc-oda-commons is used through the `hpc-oda` command ([CLI reference](cli.md)). A few
functions are offered only as a library, for code that imports the package. They live in
`hpc_oda_commons.intelligence`, are deterministic, and no CLI command calls them.
`tests/unit/test_python_api_doc.py` checks that every function the package exports there is
listed on this page.

```python
from hpc_oda_commons.intelligence import (
    build_metadata_graph_payload,
    score_job_runtime_parquet,
    suggest_slurmctld_mappings,
)
```

## Mapping suggestions

- `suggest_job_runtime_mappings(rows)`: for each core job field (`job_id`, `start_time`,
  `end_time`, `runtime_seconds`, `allocated_cpus`, `partition`, `node_list`), whether the parsed
  `rows` (an iterable of dicts) have it. Returns one dict per field: `field`, `mapped_to` (the
  field, or `None`), `confidence` (1.0 or 0.0) and `reason`.
- `suggest_slurmctld_mappings(path)`: the same, for the rows the slurmctld adapter parses from
  the log at `path`.

The jobs-parquet ingest wizard makes its own, richer suggestions
([Ingest jobs Parquet exports](../how-to/ingest-jobs-parquet.md)).

## Synthetic-data scoring

- `score_job_runtime_rows(rows)`: simple coverage and realism measures for a list of job rows.
  Returns `row_count`, per-field `missingness`, `coverage_score` (1 minus the mean missingness
  of `job_id`, `start_time`, `end_time` and `runtime_seconds`), `runtime_positive_rate`,
  `runtime_mean`, `partition_diversity` (distinct partitions), and `cpu_min` and `cpu_max`.
  Raises `ValueError` on no rows.
- `score_job_runtime_parquet(path)`: the same, for a Parquet job table.

## Metadata graph

- `build_metadata_graph(snapshot)`: a graph of a registry snapshot. Each entry is a node,
  linked to nodes for its tags (`has_tag`), problem domains (`has_domain`), supported sources
  (`supports_source`) and input and output schemas (`input_schema`, `output_schema`). Returns
  `{"nodes": [...], "edges": [...]}`.
- `build_metadata_graph_payload(path=None)`: the same, for the package's registry, or for a
  registry snapshot file at `path`.
