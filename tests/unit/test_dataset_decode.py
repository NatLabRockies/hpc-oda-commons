from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hpc_oda_commons.datasets.decode import DecodeError, decode_to_parquet


def _write_parquet(path: Path, table: pa.Table) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)


def test_decode_parquet_single(tmp_path: Path) -> None:
    src = tmp_path / "a.parquet"
    _write_parquet(src, pa.table({"x": [1, 2, 3]}))
    dest = tmp_path / "out.parquet"

    decode_to_parquet("parquet", [src], dest)

    assert pq.read_table(dest).num_rows == 3


def test_decode_parquet_multi_concat(tmp_path: Path) -> None:
    a = tmp_path / "a.parquet"
    b = tmp_path / "b.parquet"
    _write_parquet(a, pa.table({"x": [1, 2]}))
    _write_parquet(b, pa.table({"x": [3]}))
    dest = tmp_path / "out.parquet"

    decode_to_parquet("parquet", [a, b], dest)

    assert pq.read_table(dest).num_rows == 3


def test_decode_csv(tmp_path: Path) -> None:
    src = tmp_path / "a.csv"
    src.write_text("x,y\n1,a\n2,b\n", encoding="utf-8")
    dest = tmp_path / "out.parquet"

    decode_to_parquet("csv", [src], dest, options={"delimiter": ","})

    table = pq.read_table(dest)
    assert table.num_rows == 2
    assert set(table.column_names) == {"x", "y"}


def test_decode_unsupported_format(tmp_path: Path) -> None:
    with pytest.raises(DecodeError, match="unsupported decode format"):
        decode_to_parquet("swf", [tmp_path / "x"], tmp_path / "out.parquet")


def test_decode_empty_files(tmp_path: Path) -> None:
    with pytest.raises(DecodeError):
        decode_to_parquet("parquet", [], tmp_path / "out.parquet")
