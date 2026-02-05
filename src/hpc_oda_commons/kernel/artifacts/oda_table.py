from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


def write_table_parquet(rows: list[dict[str, Any]], path: Path) -> None:
    """
    Write an ODA Table as a Parquet file.

    v0.1 policy:
    - Always create parent directories.
    - Canonical implementation: PyArrow Table.from_pylist + parquet.write_table
    - Empty rows are not allowed (schema would be ambiguous).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        raise ValueError("rows must be non-empty")

    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)


def read_table_parquet(path: Path) -> list[dict[str, Any]]:
    """
    Read an ODA Table from Parquet into list[dict] (validator-friendly).
    """
    path = Path(path)
    table = pq.read_table(path)
    return table.to_pylist()


def table_hash(path: Path) -> str:
    """
    Stable sha256 over the Parquet file bytes (read in chunks).
    """
    path = Path(path)
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def peek_columns(path: Path) -> list[str]:
    """
    Fast column-name peek: reads Parquet schema only (no full scan).
    """
    path = Path(path)
    return list(pq.read_schema(path).names)
