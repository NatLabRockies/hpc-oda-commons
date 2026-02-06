from __future__ import annotations

from hpc_oda_commons.intelligence.mapping import suggest_job_runtime_mappings


def test_suggest_job_runtime_mappings() -> None:
    rows = [
        {"job_id": 1, "start_time": "2026-01-01T00:00:00Z", "runtime_seconds": 10.0},
        {"job_id": 2, "end_time": "2026-01-01T00:01:00Z", "allocated_cpus": 4},
    ]
    suggestions = suggest_job_runtime_mappings(rows)
    assert any(s["field"] == "job_id" and s["confidence"] == 1.0 for s in suggestions)
