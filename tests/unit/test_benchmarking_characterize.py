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


def test_short_span_spends_its_whole_self_and_says_what_it_gave_up() -> None:
    """A source too small for the budget still yields a card -- a labelled, smaller one (#191).

    The window covers the entire span either way; what matters is that the card records the
    shortfall, so a reader comparing two cards can see that one of them is running short
    rather than inferring it from the dates.
    """
    char = characterize_table(_table({d: 20 for d in range(40)}))  # 40d < 120d + 30d
    win = select_window(char, train_days=60, test_days=30, history_days=120)

    assert win["healthy"] is True
    assert win["window_start"] == char["full_span"]["start"]
    assert win["window_end"] == char["full_span"]["end"]
    assert win["rule"]["shortfall"] is True
    assert win["rule"]["requested"]["history_days"] == 120
    # Evaluation is protected at the floor; history absorbs the shortfall.
    assert win["rule"]["test_days"] == 30
    assert win["rule"]["history_days"] == 10
    assert "short of the" in win["rationale"]


def test_a_span_that_fits_records_no_shortfall() -> None:
    char = characterize_table(_table({d: 20 for d in range(260)}))
    win = select_window(char, train_days=60, test_days=90, history_days=120)

    assert win["rule"]["history_days"] == 120
    assert win["rule"]["test_days"] == 90
    assert "shortfall" not in win["rule"]


def test_history_must_exist_behind_the_window() -> None:
    """The bug behind #191: a window placed with no room for the history it claims.

    240 days of data, a 120d history budget and a 90d evaluation. The window cannot start
    before day 120, or the earliest scored window would ask for history that is not there
    and silently receive less.
    """
    char = characterize_table(_table({d: 20 for d in range(240)}))
    win = select_window(char, anchor=0.0, train_days=60, test_days=90, history_days=120)

    span_start = datetime.date.fromisoformat(char["full_span"]["start"])
    test_start = datetime.date.fromisoformat(win["test_start"])
    assert (test_start - span_start).days >= 120


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
