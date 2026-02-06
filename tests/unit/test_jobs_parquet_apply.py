from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hpc_oda_commons.ingest.jobs_parquet.apply import apply_mapping_spec
from hpc_oda_commons.kernel.artifacts.mapping_spec import new_mapping_spec, write_mapping_spec


def _write_parquet(path: Path) -> None:
    rows = [
        {
            "JobID": 1,
            "StartTime": "2026-01-01T00:00:00Z",
            "EndTime": "2026-01-01T00:05:00Z",
            "SubmitTime": "2026-01-01T00:00:00Z",
            "State": "COMPLETED",
            "User": "alice",
            "Elapsed": 300.0,
        },
        {
            "JobID": 2,
            "StartTime": "2026-01-01T01:00:00Z",
            "EndTime": None,
            "SubmitTime": "2026-01-01T01:00:00Z",
            "State": "RUNNING",
            "User": "bob",
            "Elapsed": None,
        },
    ]
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)


def test_apply_mapping_spec_derives_runtime(tmp_path: Path) -> None:
    input_path = tmp_path / "jobs.parquet"
    _write_parquet(input_path)

    mapping = new_mapping_spec(
        kind="jobs_parquet",
        output_schema_version="oda.job.v0.1.0",
        fields={
            "job_id": {"source": "JobID"},
            "start_time": {
                "source": "StartTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "end_time": {
                "source": "EndTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "runtime_seconds": {"derive": "end_time - start_time"},
            "submit_time": {
                "source": "SubmitTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "state": {"source": "State"},
            "user": {"source": "User", "transform": {"type": "hash_identifier"}},
        },
    )
    mapping_path = tmp_path / "mapping.yml"
    write_mapping_spec(mapping_path, mapping, validate=True)

    out_path = tmp_path / "out.parquet"
    summary = apply_mapping_spec(input_path, mapping_path, out_path)
    assert summary["rows_kept"] == 1
    assert summary["rows_skipped"] == 1

    table = pq.read_table(out_path)
    rows = table.to_pylist()
    assert rows[0]["job_id"] == 1
    assert rows[0]["runtime_seconds"] == 300.0
    assert rows[0]["submit_time"].endswith("Z")
    assert rows[0]["user"] != "alice"
