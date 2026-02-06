from __future__ import annotations

from hpc_oda_commons.intelligence.synthetic_scoring import score_job_runtime_rows


def test_score_job_runtime_rows() -> None:
    rows = [
        {
            "job_id": 1,
            "start_time": "2026-01-01T00:00:00Z",
            "end_time": "2026-01-01T00:01:00Z",
            "runtime_seconds": 60.0,
            "partition": "debug",
            "allocated_cpus": 2,
        },
        {
            "job_id": 2,
            "start_time": "2026-01-01T00:00:00Z",
            "end_time": "2026-01-01T00:02:00Z",
            "runtime_seconds": 120.0,
            "partition": "compute",
            "allocated_cpus": 4,
        },
    ]
    report = score_job_runtime_rows(rows)
    assert report["row_count"] == 2
    assert report["partition_diversity"] == 2
    assert report["cpu_min"] == 2
