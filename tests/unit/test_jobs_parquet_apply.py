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


def test_apply_mapping_spec_filters_by_state_allowlist(tmp_path: Path) -> None:
    input_path = tmp_path / "jobs.parquet"
    rows = [
        {
            "JobID": 1,
            "StartTime": "2026-01-01T00:00:00Z",
            "EndTime": "2026-01-01T00:05:00Z",
            "SubmitTime": "2026-01-01T00:00:00Z",
            "State": "COMPLETED",
            "Elapsed": 300.0,
        },
        {
            "JobID": 2,
            "StartTime": "2026-01-01T01:00:00Z",
            "EndTime": "2026-01-01T01:04:00Z",
            "SubmitTime": "2026-01-01T01:00:00Z",
            "State": "FAILED",
            "Elapsed": 240.0,
        },
        {
            "JobID": 3,
            "StartTime": "2026-01-01T02:00:00Z",
            "EndTime": "2026-01-01T02:03:00Z",
            "SubmitTime": "2026-01-01T02:00:00Z",
            "State": "RUNNING",
            "Elapsed": 180.0,
        },
    ]
    pq.write_table(pa.Table.from_pylist(rows), input_path)

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
            "runtime_seconds": {
                "source": "Elapsed",
                "transform": {"type": "duration", "unit": "seconds"},
            },
            "submit_time": {
                "source": "SubmitTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "state": {"source": "State"},
        },
    )
    mapping_path = tmp_path / "mapping.yml"
    write_mapping_spec(mapping_path, mapping, validate=True)

    out_path = tmp_path / "out.parquet"
    summary = apply_mapping_spec(
        input_path,
        mapping_path,
        out_path,
        state_allowlist={"COMPLETED", "FAILED"},
    )

    table = pq.read_table(out_path)
    out_rows = table.to_pylist()
    assert len(out_rows) == 2
    assert {row["state"] for row in out_rows} == {"COMPLETED", "FAILED"}
    assert summary["rows_total"] == 3
    assert summary["rows_kept"] == 2
    assert summary["rows_skipped_state_filter"] == 1
    assert summary["state_filter_values"] == ["COMPLETED", "FAILED"]


def test_apply_mapping_spec_accepts_space_separated_timestamp_with_short_tz(tmp_path: Path) -> None:
    input_path = tmp_path / "jobs.parquet"
    rows = [
        {
            "JobID": 1,
            "StartTime": "2024-04-07 02:28:25+09",
            "EndTime": "2024-04-07 02:33:25+09",
            "SubmitTime": "2024-04-07 02:20:00+09",
            "Elapsed": 300.0,
            "State": "COMPLETED",
        }
    ]
    pq.write_table(pa.Table.from_pylist(rows), input_path)

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
            "runtime_seconds": {
                "source": "Elapsed",
                "transform": {"type": "duration", "unit": "seconds"},
            },
            "submit_time": {
                "source": "SubmitTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "state": {"source": "State"},
        },
    )
    mapping_path = tmp_path / "mapping.yml"
    write_mapping_spec(mapping_path, mapping, validate=True)

    out_path = tmp_path / "out.parquet"
    _summary = apply_mapping_spec(input_path, mapping_path, out_path)

    table = pq.read_table(out_path)
    out_rows = table.to_pylist()
    assert out_rows[0]["start_time"].endswith("Z")
    assert out_rows[0]["end_time"].endswith("Z")


def test_apply_mapping_spec_omits_optional_null_fields(tmp_path: Path) -> None:
    input_path = tmp_path / "jobs.parquet"
    rows = [
        {
            "JobID": 1,
            "StartTime": "2026-01-01T00:00:00Z",
            "EndTime": "2026-01-01T00:05:00Z",
            "SubmitTime": "2026-01-01T00:00:00Z",
            "State": "COMPLETED",
            "Partition": None,
            "QOS": None,
            "Elapsed": 300.0,
        }
    ]
    pq.write_table(pa.Table.from_pylist(rows), input_path)

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
            "runtime_seconds": {
                "source": "Elapsed",
                "transform": {"type": "duration", "unit": "seconds"},
            },
            "submit_time": {
                "source": "SubmitTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "state": {"source": "State"},
            "partition": {"source": "Partition"},
            "qos": {"source": "QOS"},
        },
    )
    mapping_path = tmp_path / "mapping.yml"
    write_mapping_spec(mapping_path, mapping, validate=True)

    out_path = tmp_path / "out.parquet"
    apply_mapping_spec(input_path, mapping_path, out_path)
    out_rows = pq.read_table(out_path).to_pylist()
    assert "partition" not in out_rows[0]
    assert "qos" not in out_rows[0]
