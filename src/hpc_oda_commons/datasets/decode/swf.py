"""
Standard Workload Format (SWF) decoder for the Parallel Workloads Archive.

SWF is plain ASCII: ``;``-prefixed header/comment lines followed by one job per
line with 18 whitespace-separated columns; ``-1`` marks an unavailable value. SWF
submit/wait times are *relative* to the start of the log, so absolute UTC timestamps
are reconstructed from the header's ``UnixStartTime`` (seconds since the epoch):

    submit = UnixStartTime + submit_offset
    start  = submit + wait
    end    = start + run_time

If the header lacks ``UnixStartTime`` the offsets are emitted as-is (epoch base 0),
which is schema-valid but not absolute -- prefer logs that carry ``UnixStartTime``.

Output columns are named for a descriptor mapping onto ``oda.job.v0.2.0``:
``swf_job``, ``submit_time``/``start_time``/``end_time`` (epoch seconds), ``run_time``,
``req_time``, ``procs_alloc``, ``req_procs``, ``req_mem_kb``, ``status``, ``user``,
``group``, ``queue``, ``partition``.

Ref: https://www.cs.huji.ac.il/labs/parallel/workload/swf.html
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from hpc_oda_commons.datasets.decode.base import DecodeError

_UNIX_START = re.compile(r";\s*UnixStartTime\s*:\s*([0-9]+)", re.IGNORECASE)


def _num(value: str) -> float | None:
    """Parse an SWF numeric field; ``-1`` (and blanks) mean unavailable -> None."""
    try:
        parsed = float(value)
    except ValueError:
        return None
    return None if parsed == -1 else parsed


def _field(fields: list[str], idx: int) -> str | None:
    """Return SWF text field ``idx`` (or None if absent / marked unavailable)."""
    return fields[idx] if idx < len(fields) and fields[idx] != "-1" else None


def _decode_file(path: Path, rows: list[dict[str, Any]]) -> None:
    base = 0.0
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(";"):
                match = _UNIX_START.match(stripped)
                if match:
                    base = float(match.group(1))
                continue
            fields = stripped.split()
            if len(fields) < 4:
                continue
            submit, wait, run_time = _num(fields[1]), _num(fields[2]), _num(fields[3])
            submit_epoch = base + submit if submit is not None else None
            start_epoch = base + submit + wait if submit is not None and wait is not None else None
            end_epoch = (
                start_epoch + run_time if start_epoch is not None and run_time is not None else None
            )

            rows.append(
                {
                    "swf_job": fields[0],
                    "submit_time": submit_epoch,
                    "start_time": start_epoch,
                    "end_time": end_epoch,
                    "run_time": run_time,
                    "procs_alloc": _num(fields[4]) if len(fields) > 4 else None,
                    "req_procs": _num(fields[7]) if len(fields) > 7 else None,
                    "req_time": _num(fields[8]) if len(fields) > 8 else None,
                    "req_mem_kb": _num(fields[9]) if len(fields) > 9 else None,
                    "status": _field(fields, 10),
                    "user": _field(fields, 11),
                    "group": _field(fields, 12),
                    "queue": _field(fields, 14),
                    "partition": _field(fields, 15),
                }
            )


def decode_swf(files: Sequence[Path], dest: Path) -> None:
    if not files:
        raise DecodeError("no input files to decode")
    rows: list[dict[str, Any]] = []
    for f in files:
        _decode_file(Path(f), rows)
    if not rows:
        raise DecodeError("no SWF job records parsed")
    dest.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), dest)
