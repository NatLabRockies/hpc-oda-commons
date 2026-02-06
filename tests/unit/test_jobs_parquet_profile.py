from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hpc_oda_commons.ingest.jobs_parquet.profile import ColumnProfile, profile_parquet


def _write_parquet(path: Path) -> None:
    rows = [
        {
            "JobID": 1,
            "StartTime": "2026-01-01T00:00:00Z",
            "EndTime": "2026-01-01T00:10:00Z",
            "User": "alice",
            "Elapsed": 600.0,
        },
        {
            "JobID": 2,
            "StartTime": "2026-01-01T01:00:00Z",
            "EndTime": "2026-01-01T01:05:00Z",
            "User": None,
            "Elapsed": 300.0,
        },
    ]
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)


def test_profile_parquet_basic(tmp_path: Path) -> None:
    path = tmp_path / "jobs.parquet"
    _write_parquet(path)

    profiles = profile_parquet(path, sample_rows=10)
    assert profiles
    assert all(isinstance(p, ColumnProfile) for p in profiles)

    by_name = {p.name: p for p in profiles}
    assert "JobID" in by_name
    assert by_name["JobID"].normalized == "jobid"
    assert by_name["Elapsed"].inferred_kind == "numeric"
    assert by_name["User"].null_rate == 0.5
    assert by_name["StartTime"].sample_values

