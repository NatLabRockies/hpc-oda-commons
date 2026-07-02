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


def test_decode_parquet_from_zip(tmp_path: Path) -> None:
    import zipfile

    inner = tmp_path / "inner.parquet"
    _write_parquet(inner, pa.table({"x": [1, 2, 3]}))
    zpath = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.write(inner, arcname="data/inner.parquet")
    dest = tmp_path / "out.parquet"

    decode_to_parquet("parquet", [zpath], dest)

    assert pq.read_table(dest).num_rows == 3


def test_decode_csv_from_targz(tmp_path: Path) -> None:
    import tarfile

    csv = tmp_path / "inner.tsv"
    csv.write_text("x\ty\n1\ta\n2\tb\n3\tc\n", encoding="utf-8")
    tpath = tmp_path / "bundle.tar.gz"
    with tarfile.open(tpath, "w:gz") as tar:
        tar.add(csv, arcname="inner.tsv")
    dest = tmp_path / "out.parquet"

    decode_to_parquet("csv", [tpath], dest, options={"delimiter": "\t"})

    table = pq.read_table(dest)
    assert table.num_rows == 3
    assert set(table.column_names) == {"x", "y"}


def test_decode_csv_gz(tmp_path: Path) -> None:
    import gzip

    gz = tmp_path / "data.csv.gz"
    with gzip.open(gz, "wt", encoding="utf-8") as fh:
        fh.write("x,y\n1,a\n2,b\n")
    dest = tmp_path / "out.parquet"

    decode_to_parquet("csv", [gz], dest)

    assert pq.read_table(dest).num_rows == 2
