"""Dataset preparation streams (#249): the results don't depend on how rows are batched."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hpc_oda_commons.datasets.decode.parquet import decode_parquet
from hpc_oda_commons.schema import validator


def _month(path: Path, start: int, n: int, *, tz: str = "UTC") -> None:
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    pq.write_table(
        pa.table(
            {
                "job_id": [str(start + i) for i in range(n)],
                "submit_time": pa.array(
                    [t0 + timedelta(hours=start + i) for i in range(n)], pa.timestamp("us", tz=tz)
                ),
                "start_time": pa.array(
                    [t0 + timedelta(hours=start + i) for i in range(n)], pa.timestamp("ms", tz=tz)
                ),
                "end_time": pa.array(
                    # One job ends before it starts, a semantic issue.
                    [t0 + timedelta(hours=start + i + (-1 if i == 1 else 1)) for i in range(n)],
                    pa.timestamp("us", tz=tz),
                ),
                "runtime_seconds": [3600.0] * n,
                "embedding": [[float(i), 1.0] for i in range(n)],
            }
        ),
        path,
    )


def test_decode_writes_files_one_at_a_time_as_a_concat_would(tmp_path: Path) -> None:
    files = [tmp_path / "a.parquet", tmp_path / "b.parquet"]
    _month(files[0], 0, 4)
    _month(files[1], 10, 3, tz="Asia/Tokyo")
    out = tmp_path / "out.parquet"

    decode_parquet(files, out)

    got = pq.read_table(out)
    assert got.num_rows == 7
    assert got.schema.field("start_time").type == pa.timestamp("us", tz="UTC")
    assert got.column("job_id").to_pylist() == ["0", "1", "2", "3", "10", "11", "12"]


def test_quality_report_is_the_same_however_it_is_batched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "jobs.parquet"
    _month(path, 0, 7)

    whole = validator.validate_parquet_with_quality(path, strict=False)
    monkeypatch.setattr(validator, "_VALIDATION_BATCH_ROWS", 2)
    batched = validator.validate_parquet_with_quality(path, strict=False)

    for report in (whole, batched):
        report.pop("generated_at")
    assert batched == whole
    assert whole["validation"]["schema_rows_checked"] == 7
    assert whole["validation"]["semantic_error_count"] == 1
