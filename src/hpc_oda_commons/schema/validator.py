"""
JSONSchema validation + additional semantic checks glue.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from jsonschema import Draft202012Validator

from hpc_oda_commons.kernel.schemas import load_schema
from hpc_oda_commons.kernel.serialization import to_jsonable
from hpc_oda_commons.kernel.validate import (
    SchemaValidationError,
    validate_json,
)
from hpc_oda_commons.schema.quality_rules import build_quality_report

JOB_SCHEMA_ID = "oda.job.v0.2.0"

# v0.2 canonical job tables store timestamps as native Arrow timestamp(us, tz=UTC).
# JSON Schema cannot express that, so the column types are validated structurally
# here rather than as JSON strings.
_JOB_TIMESTAMP_COLUMNS = ("start_time", "end_time", "submit_time")
_EXPECTED_TIMESTAMP_TYPE = pa.timestamp("us", tz="UTC")


def collect_job_table_type_issues(table: pa.Table) -> list[str]:
    """Structural type check for the canonical job table's timestamp columns."""
    issues: list[str] = []
    for column in _JOB_TIMESTAMP_COLUMNS:
        if column not in table.column_names:
            continue
        actual = table.schema.field(column).type
        if not (pa.types.is_timestamp(actual) and actual.tz is not None):
            issues.append(f"column '{column}': expected timestamp(tz=UTC), got {actual}")
    return issues


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
        if start is not None and end is not None:
            if isinstance(start, datetime) and isinstance(end, datetime):
                if start > end:
                    errors.append(f"row {idx}: start_time is after end_time")
            else:
                errors.append(f"row {idx}: invalid timestamp format")
    return errors


def _format_jsonschema_issue(error: Any) -> str:
    loc = "$"
    for item in list(getattr(error, "path", [])):
        loc += f".{item}"
    return f"{loc}: {error.message}"


def _append_issue_example(
    issues: dict[str, dict[str, Any]],
    *,
    issue: str,
    row_index: int,
    row: dict[str, Any],
    example_limit: int,
) -> None:
    bucket = issues.setdefault(issue, {"count": 0, "examples": []})
    bucket["count"] = int(bucket["count"]) + 1
    examples = bucket["examples"]
    if len(examples) < example_limit:
        examples.append({"row_index": row_index, "row": to_jsonable(row)})


def collect_schema_issues(
    rows: list[dict[str, Any]],
    *,
    schema_id: str,
    example_limit: int = 3,
) -> dict[str, dict[str, Any]]:
    schema = load_schema(schema_id)
    validator = Draft202012Validator(schema)

    issues: dict[str, dict[str, Any]] = {}
    for idx, row in enumerate(rows):
        errors = sorted(validator.iter_errors(row), key=lambda err: list(err.path))
        for error in errors:
            _append_issue_example(
                issues,
                issue=_format_jsonschema_issue(error),
                row_index=idx,
                row=row,
                example_limit=example_limit,
            )
    return issues


def collect_job_semantic_issues(
    rows: list[dict[str, Any]],
    *,
    example_limit: int = 3,
) -> dict[str, dict[str, Any]]:
    issues: dict[str, dict[str, Any]] = {}
    for idx, row in enumerate(rows):
        runtime = row.get("runtime_seconds")
        if runtime is not None:
            try:
                if float(runtime) < 0:
                    _append_issue_example(
                        issues,
                        issue="runtime_seconds is negative",
                        row_index=idx,
                        row=row,
                        example_limit=example_limit,
                    )
            except (TypeError, ValueError):
                _append_issue_example(
                    issues,
                    issue="runtime_seconds is not numeric",
                    row_index=idx,
                    row=row,
                    example_limit=example_limit,
                )

        start = row.get("start_time")
        end = row.get("end_time")
        if start is not None and end is not None:
            if isinstance(start, datetime) and isinstance(end, datetime):
                if start > end:
                    _append_issue_example(
                        issues,
                        issue="start_time is after end_time",
                        row_index=idx,
                        row=row,
                        example_limit=example_limit,
                    )
            else:
                _append_issue_example(
                    issues,
                    issue="invalid timestamp format",
                    row_index=idx,
                    row=row,
                    example_limit=example_limit,
                )
    return issues


def _summarize_issues(issues: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for issue, payload in sorted(
        issues.items(), key=lambda item: (-int(item[1]["count"]), item[0])
    ):
        out.append(
            {
                "issue": issue,
                "count": int(payload["count"]),
                "examples": payload["examples"],
            }
        )
    return out


def validate_parquet_with_quality(
    path: Path,
    *,
    schema_id: str = JOB_SCHEMA_ID,
    sample: int = 10,
    report_path: Path | None = None,
    ruleset_version: str = "v0.1",
    strict: bool = True,
    error_example_limit: int = 3,
) -> dict[str, Any]:
    """
    Validate parquet rows against schema and emit a quality report.
    """
    table = pq.read_table(path)
    rows: list[dict[str, Any]] = table.to_pylist()

    if not rows:
        raise SchemaValidationError(
            schema_id=schema_id,
            message="No rows to validate.",
            path=str(path),
        )

    schema_issue_map = collect_schema_issues(
        rows,
        schema_id=schema_id,
        example_limit=error_example_limit,
    )
    semantic_issue_map: dict[str, dict[str, Any]] = {}
    type_issues: list[str] = []
    if schema_id == JOB_SCHEMA_ID:
        semantic_issue_map = collect_job_semantic_issues(
            rows,
            example_limit=error_example_limit,
        )
        type_issues = collect_job_table_type_issues(table)

    for issue in type_issues:
        schema_issue_map.setdefault(issue, {"issue": issue, "count": 0, "examples": []})[
            "count"
        ] += 1

    schema_issues = _summarize_issues(schema_issue_map)
    semantic_issues = _summarize_issues(semantic_issue_map)

    validation_summary = {
        "strict": strict,
        "schema_error_count": sum(int(item["count"]) for item in schema_issues),
        "semantic_error_count": sum(int(item["count"]) for item in semantic_issues),
        "schema_errors": schema_issues,
        "semantic_errors": semantic_issues,
        "schema_sample_rows_requested": sample,
        "schema_rows_checked": len(rows),
    }

    if strict and (
        validation_summary["schema_error_count"] or validation_summary["semantic_error_count"]
    ):
        lines: list[str] = ["Validation failed:"]
        if validation_summary["schema_error_count"]:
            lines.append("Schema errors:")
            for issue in schema_issues[:20]:
                lines.append(f"- {issue['issue']} (count={issue['count']})")
        if validation_summary["semantic_error_count"]:
            lines.append("Semantic errors:")
            for issue in semantic_issues[:20]:
                lines.append(f"- {issue['issue']} (count={issue['count']})")
        raise SchemaValidationError(
            schema_id=schema_id,
            message="\n".join(lines),
            path=str(path),
        )

    report = build_quality_report(
        rows,
        schema_version=schema_id,
        ruleset_version=ruleset_version,
    )
    report["validation"] = validation_summary

    if report_path:
        import json

        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    return report
