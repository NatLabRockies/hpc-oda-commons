"""
Unit tests for schema validation and data quality rules.
"""

from __future__ import annotations

from pathlib import Path

from hpc_oda_commons.kernel.artifacts.oda_table import write_table_parquet
from hpc_oda_commons.schema.quality_rules import build_quality_report, compute_missingness
from hpc_oda_commons.schema.validator import validate_parquet_with_quality


def test_compute_missingness() -> None:
    rows = [
        {"job_id": 1, "partition": "debug", "runtime_seconds": 10.0},
        {"job_id": 2, "partition": None, "runtime_seconds": None},
    ]
    missing = compute_missingness(rows)
    assert missing["partition"] == 0.5
    assert missing["runtime_seconds"] == 0.5


def test_build_quality_report() -> None:
    rows = [{"job_id": 1, "start_time": "2026-01-01T00:00:00Z", "end_time": "2026-01-01T00:01:00Z"}]
    report = build_quality_report(rows, schema_version="oda.job.v0.1.0")
    assert report["schema_version"] == "oda.job.v0.1.0"
    assert report["ruleset_version"] == "v0.1"
    assert report["row_count"] == 1


def test_validate_parquet_with_quality_writes_report(tmp_path: Path) -> None:
    parquet_path = tmp_path / "data.parquet"
    rows = [
        {
            "job_id": 1,
            "start_time": "2026-01-01T00:00:00Z",
            "end_time": "2026-01-01T00:01:00Z",
            "runtime_seconds": 60.0,
        }
    ]
    write_table_parquet(rows, parquet_path)

    report_path = tmp_path / "data.parquet.quality.json"
    report = validate_parquet_with_quality(parquet_path, report_path=report_path)

    assert report_path.exists()
    assert report["row_count"] == 1
