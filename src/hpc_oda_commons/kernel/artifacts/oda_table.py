from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from hpc_oda_commons.kernel.hashing import sha256_file
from hpc_oda_commons.kernel.paths import ensure_parent_dir


def write_table_parquet(rows: list[dict[str, Any]], path: Path) -> None:
    ensure_parent_dir(path)
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)


def read_table_parquet(path: Path) -> list[dict[str, Any]]:
    table = pq.read_table(path)
    return table.to_pylist()


def peek_columns(path: Path) -> list[str]:
    table = pq.read_table(path)
    return list(table.column_names)


def table_hash(path: Path) -> str:
    return sha256_file(path)
