"""
Unit tests for schema validation and data quality rules.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from hpc_oda_commons.kernel.artifacts.oda_table import write_table_parquet
from hpc_oda_commons.kernel.validate import SchemaValidationError
from hpc_oda_commons.schema.quality_rules import build_quality_report, compute_missingness
from hpc_oda_commons.schema.validator import validate_parquet_with_quality


def _dt(_s: str):
    """Parse an ISO-8601 Z timestamp to a tz-aware UTC datetime (v0.2 fixtures)."""
    from datetime import datetime

    return datetime.fromisoformat(_s.replace("Z", "+00:00"))


def test_compute_missingness() -> None:
    rows = [
        {"job_id": 1, "partition": "debug", "runtime_seconds": 10.0},
        {"job_id": 2, "partition": None, "runtime_seconds": None},
    ]
    missing = compute_missingness(rows)
    assert missing["partition"] == 0.5
    assert missing["runtime_seconds"] == 0.5


def test_build_quality_report() -> None:
    rows = [
        {
            "job_id": 1,
            "start_time": _dt("2026-01-01T00:00:00Z"),
            "end_time": _dt("2026-01-01T00:01:00Z"),
        }
    ]
    report = build_quality_report(rows, schema_version="oda.job.v0.1.0")
    assert report["schema_version"] == "oda.job.v0.1.0"
    assert report["ruleset_version"] == "v0.1"
    assert report["row_count"] == 1


def test_validate_parquet_with_quality_writes_report(tmp_path: Path) -> None:
    parquet_path = tmp_path / "data.parquet"
    rows = [
        {
            "job_id": 1,
            "start_time": _dt("2026-01-01T00:00:00Z"),
            "end_time": _dt("2026-01-01T00:01:00Z"),
            "runtime_seconds": 60.0,
        }
    ]
    write_table_parquet(rows, parquet_path)

    report_path = tmp_path / "data.parquet.quality.json"
    report = validate_parquet_with_quality(parquet_path, report_path=report_path)

    assert report_path.exists()
    assert report["row_count"] == 1


def test_validate_parquet_with_quality_rejects_negative_runtime(tmp_path: Path) -> None:
    parquet_path = tmp_path / "data.parquet"
    rows = [
        {
            "job_id": 1,
            "start_time": _dt("2026-01-01T00:00:00Z"),
            "end_time": _dt("2026-01-01T00:01:00Z"),
            "runtime_seconds": -1.0,
        }
    ]
    write_table_parquet(rows, parquet_path)

    with pytest.raises(SchemaValidationError):
        validate_parquet_with_quality(parquet_path)


def test_validate_parquet_with_quality_rejects_inverted_timestamps(tmp_path: Path) -> None:
    parquet_path = tmp_path / "data.parquet"
    rows = [
        {
            "job_id": 1,
            "start_time": _dt("2026-01-01T00:02:00Z"),
            "end_time": _dt("2026-01-01T00:01:00Z"),
            "runtime_seconds": 60.0,
        }
    ]
    write_table_parquet(rows, parquet_path)

    with pytest.raises(SchemaValidationError):
        validate_parquet_with_quality(parquet_path)


def test_validate_parquet_with_quality_rejects_bad_timestamp(tmp_path: Path) -> None:
    parquet_path = tmp_path / "data.parquet"
    rows = [
        {
            "job_id": 1,
            "start_time": "not-a-time",
            "end_time": _dt("2026-01-01T00:01:00Z"),
            "runtime_seconds": 60.0,
        }
    ]
    write_table_parquet(rows, parquet_path)

    with pytest.raises(SchemaValidationError):
        validate_parquet_with_quality(parquet_path)


def test_validate_parquet_with_quality_non_strict_collects_issues(tmp_path: Path) -> None:
    parquet_path = tmp_path / "data.parquet"
    rows = [
        # start_time after end_time (semantic) + negative runtime (schema: minimum 0)
        {
            "job_id": 1,
            "start_time": _dt("2026-01-01T00:02:00Z"),
            "end_time": _dt("2026-01-01T00:01:00Z"),
            "runtime_seconds": -5.0,
        },
        {
            "job_id": 2,
            "start_time": _dt("2026-01-01T01:00:00Z"),
            "end_time": _dt("2026-01-01T01:10:00Z"),
            "runtime_seconds": 5.0,
        },
    ]
    write_table_parquet(rows, parquet_path)

    report = validate_parquet_with_quality(
        parquet_path,
        strict=False,
        error_example_limit=3,
    )

    validation = report["validation"]
    assert validation["strict"] is False
    assert validation["schema_error_count"] >= 1
    assert validation["semantic_error_count"] >= 1
    assert validation["schema_errors"]
    assert validation["semantic_errors"]

    first_semantic = validation["semantic_errors"][0]
    assert first_semantic["count"] >= 1
    assert first_semantic["examples"]


def test_validate_parquet_with_quality_allows_null_optional_fields(tmp_path: Path) -> None:
    # Regression for #8: an optional column populated in only some rows is stored
    # as null for the unpopulated rows (columnar Parquet). Strict validation must
    # accept that null rather than rejecting "None is not of type 'integer'".
    parquet_path = tmp_path / "data.parquet"
    rows = [
        {
            "job_id": 1,
            "start_time": _dt("2026-01-01T00:00:00Z"),
            "end_time": _dt("2026-01-01T00:01:00Z"),
            "runtime_seconds": 60.0,
            "allocated_cpus": 4,
            "partition": "debug",
            "node_list": "node[01-02]",
        },
        {
            "job_id": 2,
            "start_time": _dt("2026-01-01T00:02:00Z"),
            "end_time": _dt("2026-01-01T00:03:00Z"),
            "runtime_seconds": 60.0,
            "allocated_cpus": None,
            "partition": None,
            "node_list": None,
        },
    ]
    write_table_parquet(rows, parquet_path)

    # strict=True (the default) must not raise on the null optional cells.
    report = validate_parquet_with_quality(parquet_path)
    assert report["row_count"] == 2
    assert report["validation"]["schema_error_count"] == 0


def test_validate_parquet_with_quality_non_strict_serializes_datetime_examples(
    tmp_path: Path,
) -> None:
    parquet_path = tmp_path / "data.parquet"
    rows = [
        # negative runtime triggers a schema error (minimum 0); the example row then
        # carries a datetime start_time, which must serialize to a string in the report.
        {
            "job_id": 1,
            "start_time": datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
            "end_time": datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
            "runtime_seconds": -1.0,
        }
    ]
    write_table_parquet(rows, parquet_path)

    report_path = tmp_path / "data.parquet.quality.json"
    validate_parquet_with_quality(
        parquet_path,
        strict=False,
        report_path=report_path,
    )

    assert report_path.exists()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["validation"]["schema_error_count"] >= 1
    first_schema = payload["validation"]["schema_errors"][0]
    assert first_schema["examples"]
    assert isinstance(first_schema["examples"][0]["row"]["start_time"], str)
