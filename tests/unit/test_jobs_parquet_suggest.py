from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hpc_oda_commons.ingest.jobs_parquet.profile import profile_parquet
from hpc_oda_commons.ingest.jobs_parquet.suggest import suggest_mapping


def _write_parquet(path: Path) -> None:
    rows = [
        {
            "JobID": 101,
            "StartTime": "2026-01-01T00:00:00Z",
            "EndTime": "2026-01-01T00:10:00Z",
            "SubmitTime": "2026-01-01T00:00:00Z",
            "State": "COMPLETED",
            "User": "alice",
            "Account": "proj",
            "Partition": "debug",
            "QOS": "normal",
            "ReqNodes": 2,
            "ReqMemMB": 2048,
            "ReqCPUS": 4,
            "ReqGRES": "gpu:1",
            "Elapsed": 600.0,
            "TimeLimit": 1200,
        }
    ]
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)


def test_suggest_mapping_basic(tmp_path: Path) -> None:
    path = tmp_path / "jobs.parquet"
    _write_parquet(path)
    profiles = profile_parquet(path, sample_rows=10)
    suggestions = suggest_mapping(profiles)

    assert suggestions["job_id"][0]["column"] == "JobID"
    assert suggestions["start_time"][0]["column"] == "StartTime"
    assert suggestions["end_time"][0]["column"] == "EndTime"
    assert suggestions["submit_time"][0]["column"] == "SubmitTime"
    assert suggestions["state"][0]["column"] == "State"
    assert suggestions["runtime_seconds"][0]["column"] == "Elapsed"

    assert any(c["column"] == "ReqNodes" for c in suggestions["nodes_requested"])
    assert any(c["column"] == "ReqMemMB" for c in suggestions["memory_requested"])
    assert any(c["column"] == "ReqCPUS" for c in suggestions["processors_requested"])
    assert any(c["column"] == "ReqGRES" for c in suggestions["gpus_requested"])
    assert any(c["column"] == "TimeLimit" for c in suggestions["wallclock_requested"])

