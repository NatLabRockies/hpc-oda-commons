"""
JSONSchema validation + additional semantic checks glue.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from hpc_oda_commons.kernel.validate import (
    SchemaValidationError,
    validate_json,
    validate_parquet_rows,
)
from hpc_oda_commons.schema.quality_rules import build_quality_report

JOB_SCHEMA_ID = "oda.job.v0.1.0"


def validate_rows(rows: list[dict[str, Any]], schema_id: str) -> None:
    for row in rows:
        validate_json(row, schema_id)


def validate_job_semantics(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for idx, row in enumerate(rows):
        runtime = row.get("runtime_seconds")
        if runtime is not None:
            try:
                if float(runtime) < 0:
                    errors.append(f"row {idx}: runtime_seconds is negative")
            except (TypeError, ValueError):
                errors.append(f"row {idx}: runtime_seconds is not numeric")

        start = row.get("start_time")
        end = row.get("end_time")
        if start and end:
            from datetime import datetime

            try:
                sdt = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
                edt = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
                if sdt > edt:
                    errors.append(f"row {idx}: start_time is after end_time")
            except ValueError:
                errors.append(f"row {idx}: invalid timestamp format")
    return errors


def validate_parquet_with_quality(
    path: Path,
    *,
    schema_id: str = JOB_SCHEMA_ID,
    sample: int = 10,
    report_path: Path | None = None,
) -> dict[str, Any]:
    """
    Validate parquet rows against schema and emit a quality report.
    """
    validate_parquet_rows(path, schema_id, sample=sample)

    table = pq.read_table(path)
    rows: list[dict[str, Any]] = table.to_pylist()

    if schema_id == JOB_SCHEMA_ID:
        semantic_errors = validate_job_semantics(rows)
        if semantic_errors:
            raise SchemaValidationError(
                schema_id=schema_id,
                message="Semantic validation failed:\n- " + "\n- ".join(semantic_errors[:20]),
                path=str(path),
            )

    report = build_quality_report(rows, schema_version=schema_id)

    if report_path:
        import json

        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    return report
