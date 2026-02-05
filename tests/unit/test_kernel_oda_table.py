from __future__ import annotations

from pathlib import Path

import pytest

from hpc_oda_commons.kernel.artifacts.oda_table import (
    peek_columns,
    read_table_parquet,
    table_hash,
    write_table_parquet,
)


def test_write_read_roundtrip_parquet(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "data.parquet"
    rows = [
        {"job_id": 1, "partition": "debug", "runtime_seconds": 12.5},
        {"job_id": 2, "partition": "compute", "runtime_seconds": 99.0},
    ]

    write_table_parquet(rows, out)
    assert out.exists()

    back = read_table_parquet(out)
    assert back == rows


def test_table_hash_changes_on_change(tmp_path: Path) -> None:
    out = tmp_path / "data.parquet"

    rows1 = [{"job_id": 1, "partition": "debug"}]
    write_table_parquet(rows1, out)
    h1 = table_hash(out)

    rows2 = [{"job_id": 2, "partition": "debug"}]
    write_table_parquet(rows2, out)
    h2 = table_hash(out)

    assert h1 != h2


def test_peek_columns(tmp_path: Path) -> None:
    out = tmp_path / "data.parquet"
    rows = [{"job_id": 1, "partition": "debug", "runtime_seconds": 12.5}]
    write_table_parquet(rows, out)

    cols = peek_columns(out)
    assert cols == ["job_id", "partition", "runtime_seconds"]


def test_write_empty_raises(tmp_path: Path) -> None:
    out = tmp_path / "data.parquet"
    with pytest.raises(ValueError, match="rows must be non-empty"):
        write_table_parquet([], out)
