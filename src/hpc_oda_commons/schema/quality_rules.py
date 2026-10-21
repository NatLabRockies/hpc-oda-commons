"""
Pluggable data quality rules (v0.1 defaults live here).
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_dt(value: Any) -> datetime | None:
    # v0.2 canonical job tables carry tz-aware datetimes; anything else is "missing".
    if isinstance(value, datetime):
        return value
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
        sdt = _parse_dt(start)
        edt = _parse_dt(end)
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


QUALITY_RULESET_VERSION = "v0.1"


class QualityAccumulator:
    """The quality report's counts, added up one batch of rows at a time, so a table too
    large to hold as Python rows can still be reported on (#249). Every count is a sum, so
    the report is the same however the rows are batched."""

    def __init__(self, label_field: str | None = None) -> None:
        self.label_field = label_field
        self.rows = 0
        self.totals: Counter[str] = Counter()
        self.missing: Counter[str] = Counter()
        self.timestamp_issues = 0
        self.negative_runtime = 0
        self.labels: Counter[str] = Counter()

    def add(self, rows: list[dict[str, Any]]) -> None:
        self.rows += len(rows)
        for row in rows:
            for key in row.keys():
                self.totals[key] += 1
                val = row.get(key)
                if val is None or val == "":
                    self.missing[key] += 1
        self.timestamp_issues += compute_timestamp_issues(rows)
        self.negative_runtime += compute_negative_runtime(rows)
        if self.label_field:
            self.labels.update(compute_label_distribution(rows, self.label_field))

    def report(self, *, schema_version: str, ruleset_version: str) -> dict[str, Any]:
        report: dict[str, Any] = {
            "schema_version": schema_version,
            "ruleset_version": ruleset_version,
            "generated_at": _now_utc_iso(),
            "row_count": self.rows,
            "missingness": {
                key: self.missing[key] / float(self.totals[key]) for key in sorted(self.totals)
            },
            "timestamp_issues": self.timestamp_issues,
            "negative_runtime": self.negative_runtime,
        }
        if self.label_field:
            report["label_distribution"] = dict(self.labels)
        return report


def build_quality_report(
    rows: list[dict[str, Any]],
    *,
    schema_version: str,
    label_field: str | None = None,
    ruleset_version: str = QUALITY_RULESET_VERSION,
) -> dict[str, Any]:
    accumulator = QualityAccumulator(label_field)
    accumulator.add(rows)
    return accumulator.report(schema_version=schema_version, ruleset_version=ruleset_version)
