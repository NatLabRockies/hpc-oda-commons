from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_TS_RE = re.compile(r"^\[(?P<ts>[0-9T:\-\.]+)\]\s+(?P<msg>.*)$")
_ALLOC_RE = re.compile(
    r"Allocate\s+JobId=(?P<job_id>\d+)\s+NodeList=(?P<nodes>\S+)\s+#CPUs=(?P<cpus>\d+)\s+Partition=(?P<part>\S+)"
)
_DONE_RE = re.compile(r"_job_complete:\s+JobId=(?P<job_id>\d+)\s+done")


def _parse_ts(ts: str) -> str:
    # Fixture uses e.g. 2026-01-01T00:00:00.000 (no timezone). Treat as UTC.
    dt = datetime.fromisoformat(ts)
    dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def parse_slurmctld_log(path: Path) -> list[dict[str, Any]]:
    """
    Minimal slurmctld parser for v0.1 runtime prediction.

    Extracts:
      - job_id
      - start_time (from Allocate)
      - end_time (from _job_complete done)
      - runtime_seconds = end_time - start_time
      - allocated_cpus, partition, node_list (when available)
    """
    jobs: dict[int, dict[str, Any]] = {}

    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        m = _TS_RE.match(line)
        if not m:
            continue

        ts = _parse_ts(m.group("ts"))
        msg = m.group("msg")

        m_alloc = _ALLOC_RE.search(msg)
        if m_alloc:
            job_id = int(m_alloc.group("job_id"))
            jobs.setdefault(job_id, {})
            jobs[job_id].update(
                {
                    "job_id": job_id,
                    "start_time": ts,
                    "allocated_cpus": int(m_alloc.group("cpus")),
                    "partition": m_alloc.group("part"),
                    "node_list": m_alloc.group("nodes"),
                }
            )
            continue

        m_done = _DONE_RE.search(msg)
        if m_done:
            job_id = int(m_done.group("job_id"))
            jobs.setdefault(job_id, {})
            jobs[job_id].update({"job_id": job_id, "end_time": ts})
            continue

    # Finalize rows: compute runtime_seconds when possible
    rows: list[dict[str, Any]] = []
    for job_id, rec in sorted(jobs.items()):
        start = rec.get("start_time")
        end = rec.get("end_time")
        runtime = None
        if start and end:
            sdt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            edt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            runtime = max(0.0, (edt - sdt).total_seconds())

        row = {
            "job_id": rec.get("job_id", job_id),
            "start_time": start,
            "end_time": end,
            "runtime_seconds": runtime,
        }
        # Optional fields
        for k in ("allocated_cpus", "partition", "node_list"):
            if k in rec:
                row[k] = rec[k]
        rows.append(row)

    return rows
