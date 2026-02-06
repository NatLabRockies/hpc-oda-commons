from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from hpc_oda_commons.adapters.slurmctld.adapter import SlurmctldAdapter

JOB_FIELDS = (
    "job_id",
    "start_time",
    "end_time",
    "runtime_seconds",
    "allocated_cpus",
    "partition",
    "node_list",
)


def suggest_job_runtime_mappings(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Suggest mappings for job runtime prediction based on observed row fields.
    Deterministic and adapter-agnostic.
    """
    present = set()
    for row in rows:
        present.update(row.keys())

    suggestions: list[dict[str, Any]] = []
    for field in JOB_FIELDS:
        if field in present:
            suggestions.append(
                {
                    "field": field,
                    "mapped_to": field,
                    "confidence": 1.0,
                    "reason": "field present in parsed rows",
                }
            )
        else:
            suggestions.append(
                {
                    "field": field,
                    "mapped_to": None,
                    "confidence": 0.0,
                    "reason": "field missing from parsed rows",
                }
            )
    return suggestions


def suggest_slurmctld_mappings(path: str | Path) -> list[dict[str, Any]]:
    adapter = SlurmctldAdapter()
    rows = adapter.parse(Path(path))
    return suggest_job_runtime_mappings(rows)
