from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from hpc_oda_commons.ingest.jobs_parquet.profile import ColumnProfile

_ALIASES: dict[str, tuple[str, ...]] = {
    "job_id": ("job_id", "jobid", "jobid_raw", "slurm_job_id", "slurmjobid"),
    "start_time": ("start_time", "start", "start_ts", "starttime", "start_datetime"),
    "end_time": ("end_time", "end", "end_ts", "endtime", "end_datetime", "finish_time"),
    "submit_time": ("submit_time", "submit", "submit_ts", "submit_time_utc", "submit_time_ts"),
    "state": ("state", "job_state", "status"),
    "runtime_seconds": (
        "runtime_seconds",
        "runtime",
        "elapsed",
        "elapsed_time",
        "elapsed_seconds",
        "wallclock_used",
        "wallclock",
        "duration",
        "run_time",
    ),
    "user": ("user", "user_id", "uid", "username"),
    "account": ("account", "acct", "project", "allocation"),
    "partition": ("partition", "queue", "qos_partition"),
    "qos": ("qos", "quality_of_service"),
    "nodes_requested": ("nodes_requested", "req_nodes", "nodes", "nnodes"),
    "memory_requested": (
        "memory_requested",
        "mem_req",
        "req_mem",
        "reqmem",
        "memory",
        "mem",
    ),
    "processors_requested": (
        "processors_requested",
        "req_cpus",
        "reqcpus",
        "cpus",
        "ncpus",
        "processors",
    ),
    "gpus_requested": (
        "gpus_requested",
        "req_gpus",
        "gpus",
        "ngpus",
        "gres_gpu",
        "reqgres",
        "gres",
    ),
    "wallclock_requested": (
        "wallclock_requested",
        "timelimit",
        "time_limit",
        "wallclock_limit",
        "limit",
    ),
    "name": ("name", "job_name", "jobname"),
    "submit_line": ("submit_line", "command", "command_line", "cmdline"),
    "work_dir": ("work_dir", "workdir", "working_dir", "working_directory"),
}


_FIELD_KINDS: dict[str, set[str]] = {
    "job_id": {"numeric", "categorical"},
    "start_time": {"timestamp", "categorical"},
    "end_time": {"timestamp", "categorical"},
    "submit_time": {"timestamp", "categorical"},
    "state": {"categorical"},
    "runtime_seconds": {"numeric"},
    "user": {"categorical"},
    "account": {"categorical"},
    "partition": {"categorical"},
    "qos": {"categorical"},
    "nodes_requested": {"numeric"},
    "memory_requested": {"numeric"},
    "processors_requested": {"numeric"},
    "gpus_requested": {"numeric", "categorical"},
    "wallclock_requested": {"numeric", "categorical"},
    "name": {"categorical"},
    "submit_line": {"categorical"},
    "work_dir": {"categorical"},
}


def _score_name(normalized: str, aliases: Iterable[str]) -> tuple[float, str]:
    if normalized in aliases:
        return 1.0, "exact alias match"
    for alias in aliases:
        if alias and alias in normalized:
            return 0.7, f"contains alias '{alias}'"
    return 0.0, "no alias match"


def _score_kind(field: str, inferred_kind: str) -> tuple[float, str]:
    expected = _FIELD_KINDS.get(field, {"unknown"})
    if inferred_kind in expected:
        return 0.3, f"kind '{inferred_kind}' is compatible"
    if inferred_kind == "unknown":
        return 0.1, "unknown kind"
    return -0.2, f"kind '{inferred_kind}' is unlikely"


def suggest_mapping(
    profiles: Iterable[ColumnProfile],
) -> dict[str, list[dict[str, Any]]]:
    """
    Suggest candidate column mappings for job-runtime datasets.
    Returns mapping: field -> list of candidates with confidence + reason.
    """
    results: dict[str, list[dict[str, Any]]] = {}
    for field, aliases in _ALIASES.items():
        candidates: list[dict[str, Any]] = []
        for prof in profiles:
            base_score, base_reason = _score_name(prof.normalized, aliases)
            if base_score <= 0.0:
                continue
            kind_score, kind_reason = _score_kind(field, prof.inferred_kind)
            score = max(0.0, min(1.0, base_score + kind_score))
            candidates.append(
                {
                    "column": prof.name,
                    "normalized": prof.normalized,
                    "confidence": round(score, 3),
                    "reason": f"{base_reason}; {kind_reason}",
                }
            )

        candidates.sort(key=lambda c: (-c["confidence"], c["column"]))
        results[field] = candidates
    return results


def suggest_mapping_from_parquet(
    path: str, *, sample_rows: int = 200
) -> dict[str, list[dict[str, Any]]]:
    from hpc_oda_commons.ingest.jobs_parquet.profile import profile_parquet

    profiles = profile_parquet(path, sample_rows=sample_rows)
    return suggest_mapping(profiles)
