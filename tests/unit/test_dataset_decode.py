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
        decode_to_parquet("json", [tmp_path / "x"], tmp_path / "out.parquet")


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


_SWF_SAMPLE = """; SWFversion: 2.2
; UnixStartTime: 1000000000
; MaxJobs: 3
1 0 10 100 4 -1 -1 4 3600 -1 1 5 2 -1 1 0 -1 -1
2 50 20 200 8 -1 -1 8 7200 -1 1 6 2 -1 1 0 -1 -1
3 100 -1 -1 -1 -1 -1 -1 -1 -1 5 7 2 -1 1 0 -1 -1
"""


def test_decode_swf_absolute_times(tmp_path: Path) -> None:
    swf = tmp_path / "log.swf"
    swf.write_text(_SWF_SAMPLE, encoding="utf-8")
    dest = tmp_path / "out.parquet"

    decode_to_parquet("swf", [swf], dest)

    table = pq.read_table(dest)
    rows = table.to_pylist()
    assert len(rows) == 3
    # UnixStartTime 1_000_000_000 + submit(0) + wait(10) -> start; + run(100) -> end.
    assert rows[0]["start_time"] == 1_000_000_010.0
    assert rows[0]["end_time"] == 1_000_000_110.0
    assert rows[0]["run_time"] == 100.0
    assert rows[0]["req_time"] == 3600.0
    assert rows[0]["procs_alloc"] == 4.0
    # Row 3 has run_time -1 (unavailable) -> None target, None end.
    assert rows[2]["run_time"] is None
    assert rows[2]["end_time"] is None
    assert rows[2]["status"] == "5"


def test_decode_swf_from_gz(tmp_path: Path) -> None:
    import gzip

    gz = tmp_path / "log.swf.gz"
    with gzip.open(gz, "wt", encoding="utf-8") as fh:
        fh.write(_SWF_SAMPLE)
    dest = tmp_path / "out.parquet"

    decode_to_parquet("swf", [gz], dest)

    assert pq.read_table(dest).num_rows == 3


def test_decode_parquet_unifies_tz_and_duration(tmp_path: Path) -> None:
    # Hive-partition-style members with the same columns stored differently: one member
    # in UTC / duration(us), another in a local offset / duration(ns). They must concat.
    a = tmp_path / "a.parquet"
    b = tmp_path / "b.parquet"
    _write_parquet(
        a,
        pa.table(
            {
                "ts": pa.array([1_672_531_200_000_000], pa.timestamp("us", tz="UTC")),
                "dur": pa.array([1_000_000], pa.duration("us")),
            }
        ),
    )
    _write_parquet(
        b,
        pa.table(
            {
                "ts": pa.array([1_685_602_800_000_000], pa.timestamp("us", tz="-07:00")),
                "dur": pa.array([2_000_000_000], pa.duration("ns")),
            }
        ),
    )
    dest = tmp_path / "out.parquet"

    decode_to_parquet("parquet", [a, b], dest)

    table = pq.read_table(dest)
    assert table.num_rows == 2
    assert table.schema.field("ts").type == pa.timestamp("us", tz="UTC")
    assert table.schema.field("dur").type == pa.duration("us")


def test_decode_parquet_columns_option(tmp_path: Path) -> None:
    src = tmp_path / "a.parquet"
    _write_parquet(src, pa.table({"keep": [1, 2, 3], "drop": [4, 5, 6]}))
    dest = tmp_path / "out.parquet"

    decode_to_parquet("parquet", [src], dest, options={"columns": ["keep"]})

    table = pq.read_table(dest)
    assert table.column_names == ["keep"]
    assert table.num_rows == 3
