"""
Pluggable data quality rules (v0.1 defaults live here).
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_dt(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def compute_missingness(rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        return {}

    totals: Counter[str] = Counter()
    missing: Counter[str] = Counter()
    for row in rows:
        for key in row.keys():
            totals[key] += 1
            val = row.get(key)
            if val is None or val == "":
                missing[key] += 1

    return {key: missing[key] / float(totals[key]) for key in sorted(totals.keys())}


def compute_timestamp_issues(rows: list[dict[str, Any]]) -> int:
    issues = 0
    for row in rows:
        start = row.get("start_time")
        end = row.get("end_time")
        if not start or not end:
            continue
        sdt = _parse_dt(str(start))
        edt = _parse_dt(str(end))
        if sdt is None or edt is None:
            issues += 1
            continue
        if sdt > edt:
            issues += 1
    return issues


def compute_negative_runtime(rows: list[dict[str, Any]]) -> int:
    issues = 0
    for row in rows:
        runtime = row.get("runtime_seconds")
        if runtime is None:
            continue
        try:
            if float(runtime) < 0:
                issues += 1
        except (TypeError, ValueError):
            issues += 1
    return issues


def compute_label_distribution(rows: list[dict[str, Any]], label_field: str) -> dict[str, int]:
    values: Counter[str] = Counter()
    for row in rows:
        if label_field not in row:
            continue
        val = row.get(label_field)
        if val is None:
            continue
        values[str(val)] += 1
    return dict(values)


def build_quality_report(
    rows: list[dict[str, Any]],
    *,
    schema_version: str,
    label_field: str | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": schema_version,
        "generated_at": _now_utc_iso(),
        "row_count": len(rows),
        "missingness": compute_missingness(rows),
        "timestamp_issues": compute_timestamp_issues(rows),
        "negative_runtime": compute_negative_runtime(rows),
    }

    if label_field:
        report["label_distribution"] = compute_label_distribution(rows, label_field)

    return report
