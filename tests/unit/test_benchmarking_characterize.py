"""Unit tests for dataset characterization, health-gating, and window selection."""

from __future__ import annotations

import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hpc_oda_commons.benchmarking import (
    build_card,
    characterize_table,
    select_window,
    write_card,
)
from hpc_oda_commons.benchmarking.characterize import CharacterizeError
from hpc_oda_commons.kernel.schemas import load_schema

_BASE = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)


def _table(daily_counts: dict[int, int]) -> pa.Table:
    """Build a canonical-ish job table from {day_offset: job_count}."""
    submit, runtime, queue = [], [], []
    for day, count in daily_counts.items():
        for i in range(count):
            submit.append(_BASE + datetime.timedelta(days=day, hours=i % 24))
            runtime.append(float(100 + (i % 7) * 10))
            queue.append(f"q{i % 3}")
    return pa.table(
        {
            "submit_time": pa.array(submit, type=pa.timestamp("us", tz="UTC")),
            "runtime_seconds": pa.array(runtime, type=pa.float64()),
            "queue": pa.array(queue),
        }
    )


def test_characterize_detects_no_gap_and_picks_anchor_window() -> None:
    char = characterize_table(_table({d: 50 for d in range(200)}))
    assert char["n_rows"] == 200 * 50
    assert char["gaps"] == []
    assert char["columns"]["queue"]["cardinality"] == 3
    assert char["runtime_seconds"]["median"] == pytest.approx(130, abs=20)

    win = select_window(char, anchor=0.80, train_days=60, test_days=30)
    assert win["healthy"] is True
    assert win["gaps_in_window"] == []
    assert "clear of all missing blocks" in win["rationale"]


def test_missing_block_is_detected_and_window_avoids_it_entirely() -> None:
    counts = {d: 50 for d in range(200)}
    for d in range(150, 161):  # an 11-day hole inside the 80% anchor region
        counts[d] = 0
    char = characterize_table(_table(counts))
    assert len(char["gaps"]) == 1
    assert char["gaps"][0]["days"] == 11

    win = select_window(char, anchor=0.80, train_days=60, test_days=30)
    assert win["healthy"] is True  # shifted clear of the block
    assert win["gaps_in_window"] == []
    assert "shift" in win["rationale"].lower()
    # The window must not overlap the outage at all — not even clip its leading edge.
    block_start = (_BASE + datetime.timedelta(days=150)).date().isoformat()
    assert win["window_end"] < block_start


def test_short_span_falls_back_to_whole_span() -> None:
    char = characterize_table(_table({d: 20 for d in range(40)}))  # 40d < 90d window
    win = select_window(char, train_days=60, test_days=30)
    assert win["healthy"] is True
    assert "whole" in win["rationale"].lower()


def test_no_gap_free_window_is_flagged_unhealthy() -> None:
    # Span is exactly one window long, with a hole in it -> nowhere to shift.
    counts = {d: 30 for d in range(90)}
    for d in range(40, 50):
        counts[d] = 0
    char = characterize_table(_table(counts))
    win = select_window(char, train_days=60, test_days=30)
    assert win["healthy"] is False
    assert win["gaps_in_window"]


def test_characterize_requires_a_submit_time_column() -> None:
    with pytest.raises(CharacterizeError):
        characterize_table(pa.table({"runtime_seconds": pa.array([1.0, 2.0])}))


def test_card_builds_strips_private_series_and_validates(tmp_path: Path) -> None:
    table = _table({d: 50 for d in range(120)})
    parquet = tmp_path / "x.parquet"
    pq.write_table(table, parquet)

    char = characterize_table(table)
    win = select_window(char)
    card = build_card(
        "dataset.job_runtime.test", parquet, char, win, source={"system": "TestSystem"}
    )

    assert "_daily" not in card["characterization"]  # private series stripped
    load_schema("oda.dataset_card.v0.1.0")  # schema id resolves via the loader
    import jsonschema

    jsonschema.validate(card, load_schema("oda.dataset_card.v0.1.0"))

    json_path, md_path = write_card(card, tmp_path / "cards", stem="test")
    assert json_path.exists() and md_path.exists()
    assert "Benchmark window" in md_path.read_text()
