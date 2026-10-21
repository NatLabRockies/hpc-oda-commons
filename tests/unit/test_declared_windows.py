"""A recipe declares the window it reads (#249), applied as the table is scanned."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hpc_oda_commons.benchmarking.hpc.slice import SliceError, read_window, slice_to_window
from hpc_oda_commons.qst import cli
from tests.unit.test_benchmark_model_resolution import _first_result_bundle, _write_recipe


def _ts(day: int, hour: int) -> datetime:
    return datetime(2026, 1, day, hour, tzinfo=timezone.utc)


def _jobs(path: Path) -> None:
    """Eight jobs over four days; one ends the day after it was submitted, one lacks power."""
    rows = []
    for i, (day, hour, end_day) in enumerate(
        [(1, 3, 1), (1, 22, 2), (2, 4, 2), (2, 9, 2), (3, 1, 3), (3, 7, 3), (4, 2, 4), (4, 9, 4)]
    ):
        rows.append(
            {
                "job_id": str(i),
                "submit_time": _ts(day, hour),
                "start_time": _ts(day, hour),
                "end_time": _ts(end_day, 23),
                "runtime_seconds": 60.0 * (i + 1),
                "partition": "p",
                "avgpcon_per_node": None if i == 4 else 100.0 + i,
            }
        )
    pq.write_table(pa.Table.from_pylist(rows), path, row_group_size=3)


def test_the_scanned_window_keeps_what_the_slice_keeps(tmp_path: Path) -> None:
    path = tmp_path / "jobs.parquet"
    _jobs(path)
    table = pq.read_table(path)
    for start, end, extra in [("2026-01-02", "2026-01-03", 0), ("2026-01-03", "2026-01-04", 1)]:
        expected = slice_to_window(table, start, end, extra_lookback_days=extra)
        got = read_window(path, start, end, extra_lookback_days=extra)
        assert got.combine_chunks().equals(expected.combine_chunks())
    # A job submitted on the 1st that ends on the 2nd overlaps a window starting the 2nd.
    assert read_window(path, "2026-01-02", "2026-01-03").column("job_id").to_pylist() == [
        "1",
        "2",
        "3",
        "4",
        "5",
    ]


def test_required_columns_and_dropped_columns(tmp_path: Path) -> None:
    path = tmp_path / "jobs.parquet"
    _jobs(path)
    got = read_window(path, require_nonnull=["avgpcon_per_node"], drop_columns=["partition"])
    assert got.num_rows == 7
    assert "partition" not in got.column_names
    with pytest.raises(SliceError, match="lacks"):
        read_window(path, require_nonnull=["embedding"])
    with pytest.raises(SliceError, match="both"):
        read_window(path, "2026-01-02", None)


def test_the_runner_reads_the_declared_window_and_records_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "jobs.parquet"
    _jobs(path)
    recipe = tmp_path / "recipe.yml"
    _write_recipe(
        recipe,
        model_id="model.baseline",
        split_block="  method: fixed\n  train_fraction: 0.5\n  seed: 1",
        table_path=path,
    )
    text = recipe.read_text(encoding="utf-8").replace(
        f"  table_path: {path.as_posix()}\n",
        f"  table_path: {path.as_posix()}\n"
        '  window: { start: "2026-01-02", end: "2026-01-04" }\n'
        "  require_nonnull: [avgpcon_per_node]\n",
    )
    recipe.write_text(text, encoding="utf-8")
    seen: list[int] = []
    to_rows = cli.table_to_rows
    monkeypatch.setattr(cli, "table_to_rows", lambda t: seen.append(t.num_rows) or to_rows(t))

    cli.benchmark(recipe)

    assert seen == [6]  # jobs 1-7 overlap the window, and job 4 has no power
    result = json.loads((_first_result_bundle(tmp_path / "runs") / "result.json").read_text())
    assert result["dataset"]["window"] == {"start": "2026-01-02", "end": "2026-01-04"}
    assert result["dataset"]["require_nonnull"] == ["avgpcon_per_node"]
