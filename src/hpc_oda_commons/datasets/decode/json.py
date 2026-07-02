"""
JSON decoder: flatten a nested workload/record JSON into one flat table.

The shape it handles (e.g. the IC2 workloads dataset): a top-level list of groups, each a
dict carrying scalar group fields plus one list of records under ``record_path`` (e.g.
``tasklist``). Each record becomes a row, carrying the group's scalar fields alongside the
record's scalar fields; nested list/dict values (e.g. per-node metric arrays) are dropped.
With no ``record_path``, each top-level object is itself a row (its scalar fields only).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from hpc_oda_commons.datasets.decode.base import DecodeError


def _scalars(obj: Mapping[str, Any]) -> dict[str, Any]:
    """Scalar (non-list/dict) fields of a mapping."""
    return {k: v for k, v in obj.items() if not isinstance(v, (list, dict))}


def decode_json(
    files: Sequence[Path], dest: Path, *, options: Mapping[str, Any] | None = None
) -> None:
    if not files:
        raise DecodeError("no input files to decode")
    record_path = (options or {}).get("record_path")
    rows: list[dict[str, Any]] = []
    for f in files:
        with Path(f).open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        groups = data if isinstance(data, list) else [data]
        for group in groups:
            if not isinstance(group, dict):
                continue
            if record_path:
                parent = _scalars(group)
                records = group.get(record_path) or []
            else:
                parent, records = {}, [group]
            for record in records:
                if not isinstance(record, dict):
                    continue
                rows.append({**parent, **_scalars(record)})
    if not rows:
        raise DecodeError("no JSON records parsed")

    # Build each column independently so a field with mixed scalar types across records
    # (e.g. cpus "24" vs 24) falls back to string rather than failing type inference.
    keys: dict[str, None] = {}
    for row in rows:
        for key in row:
            keys.setdefault(key, None)
    columns: dict[str, pa.Array] = {}
    for key in keys:
        values = [row.get(key) for row in rows]
        try:
            columns[key] = pa.array(values)
        except (pa.ArrowInvalid, pa.ArrowTypeError):
            columns[key] = pa.array(
                [None if v is None else str(v) for v in values], type=pa.string()
            )
    dest.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(columns), dest)
