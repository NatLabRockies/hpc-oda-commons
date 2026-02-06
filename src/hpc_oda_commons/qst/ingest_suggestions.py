from __future__ import annotations

from pathlib import Path
from typing import Any

from hpc_oda_commons.adapters.slurmctld.adapter import SlurmctldAdapter

REQUIRED_FIELDS = ("job_id", "start_time", "end_time", "runtime_seconds")


def build_ingest_suggestions(path: Path) -> list[dict[str, Any]]:
    """
    Deterministic ingest checks for slurmctld logs.
    Returns a list of suggestion dicts with severity and message.
    """
    adapter = SlurmctldAdapter()
    rows = adapter.parse(path)
    suggestions: list[dict[str, Any]] = []

    if not rows:
        suggestions.append(
            {
                "level": "error",
                "message": "No rows parsed from slurmctld log; check format or adapter.",
            }
        )
        return suggestions

    sample = rows[: min(50, len(rows))]

    for field in REQUIRED_FIELDS:
        missing = sum(1 for row in sample if row.get(field) in (None, ""))
        if missing:
            suggestions.append(
                {
                    "level": "warning",
                    "message": f"Field '{field}' missing in {missing}/{len(sample)} rows.",
                }
            )

    for row in sample:
        start = row.get("start_time")
        end = row.get("end_time")
        if start and end:
            try:
                from datetime import datetime

                sdt = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
                edt = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
                if sdt > edt:
                    suggestions.append(
                        {
                            "level": "warning",
                            "message": "Found start_time after end_time; check timestamps.",
                        }
                    )
                    break
            except ValueError:
                suggestions.append(
                    {
                        "level": "warning",
                        "message": "Found invalid timestamp format; check parser mapping.",
                    }
                )
                break

    return suggestions
