from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from hpc_oda_commons.schema.quality_rules import compute_missingness

REQUIRED_FIELDS = ("job_id", "start_time", "end_time", "runtime_seconds")


def score_job_runtime_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("No rows to score.")

    missingness = compute_missingness(rows)
    required_missing = [missingness.get(field, 1.0) for field in REQUIRED_FIELDS]
    coverage_score = 1.0 - (sum(required_missing) / float(len(required_missing)))

    runtimes = [float(r["runtime_seconds"]) for r in rows if r.get("runtime_seconds") is not None]
    runtime_positive = [v for v in runtimes if v > 0]
    runtime_positive_rate = len(runtime_positive) / float(len(runtimes)) if runtimes else 0.0

    partitions = {str(r.get("partition")) for r in rows if r.get("partition") not in (None, "")}
    cpus = [int(r["allocated_cpus"]) for r in rows if r.get("allocated_cpus") is not None]

    return {
        "row_count": len(rows),
        "missingness": missingness,
        "coverage_score": coverage_score,
        "runtime_positive_rate": runtime_positive_rate,
        "runtime_mean": (sum(runtimes) / float(len(runtimes))) if runtimes else 0.0,
        "partition_diversity": len(partitions),
        "cpu_min": min(cpus) if cpus else None,
        "cpu_max": max(cpus) if cpus else None,
    }


def score_job_runtime_parquet(path: Path) -> dict[str, Any]:
    table = pq.read_table(path)
    rows: list[dict[str, Any]] = table.to_pylist()
    return score_job_runtime_rows(rows)
