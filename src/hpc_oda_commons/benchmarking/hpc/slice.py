"""Slice a canonical job table to a dataset card's 90-day benchmark window.

The rolling-split benchmark keys **test** windows on ``submit_time`` and **training**
windows on ``end_time`` (``split_time - lookback <= end_time < split_time``). A job
submitted before the window but *ending* inside it is therefore a legitimate training
row. So the slice keeps every job whose ``[submit_time, end_time]`` interval overlaps the
card window — an overlap predicate, not a naive ``submit_time``-only cut — otherwise the
earliest rolling windows would silently lose training data.

Row count after slicing can slightly exceed the card's (submit-based) ``n_rows`` for
exactly this reason; that is expected.

A recipe may ask for a longer training lookback than the card's window was sized for
(the card rule is ``train_days`` + ``test_days``). The earliest rolling windows would
then train on truncated history. ``extra_lookback_days`` extends the **lower** bound
by that shortfall — ``training_lookback_days - card.train_days`` — leaving the test
region untouched, so the run scores exactly the rows the card window defines (#143).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


class SliceError(ValueError):
    """Raised when a table cannot be sliced to a window (missing temporal columns)."""


def _day_start_utc(iso_day: str) -> datetime:
    return datetime.strptime(iso_day, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _pick_field(table: pa.Table, preferred: str, fallback: str) -> str:
    if preferred in table.column_names:
        return preferred
    if fallback in table.column_names:
        return fallback
    raise SliceError(
        f"table has neither {preferred!r} nor {fallback!r}; cannot slice to a window "
        f"(columns: {', '.join(table.column_names)})."
    )


def effective_start(window_start: str, extra_lookback_days: int = 0) -> str:
    """The ISO day a slice actually begins at, once the lookback extension is applied."""
    if extra_lookback_days < 0:
        raise SliceError(f"extra_lookback_days must be >= 0, got {extra_lookback_days}")
    return (_day_start_utc(window_start) - timedelta(days=extra_lookback_days)).strftime("%Y-%m-%d")


def slice_to_window(
    table: pa.Table,
    window_start: str,
    window_end: str,
    *,
    submit_field: str = "submit_time",
    end_field: str = "end_time",
    extra_lookback_days: int = 0,
) -> pa.Table:
    """Return rows whose ``[submit, end]`` interval overlaps ``[window_start, window_end]``.

    ``window_start``/``window_end`` are inclusive ISO day strings (``YYYY-MM-DD``); the
    upper bound is expanded to the end of ``window_end``'s day.

    ``extra_lookback_days`` moves the lower bound earlier by that many days and leaves
    the upper bound alone, so a recipe whose ``training_lookback_days`` exceeds the
    card's ``train_days`` still scores exactly the card's test region (#143).
    """
    submit = _pick_field(table, submit_field, "start_time")
    end = _pick_field(table, end_field, submit)

    lo = _day_start_utc(effective_start(window_start, extra_lookback_days))
    hi = _day_start_utc(window_end) + timedelta(days=1)  # inclusive of the whole end day

    submit_col = table.column(submit)
    end_col = table.column(end)

    # overlap: submit_time < hi  AND  end_time >= lo. Nulls in either bound → dropped.
    mask = pc.and_(
        pc.less(submit_col, pa.scalar(hi, type=submit_col.type)),
        pc.greater_equal(end_col, pa.scalar(lo, type=end_col.type)),
    )
    return table.filter(mask, null_selection_behavior="drop")


def slice_dataset(
    source: Path,
    out: Path,
    window_start: str,
    window_end: str,
    *,
    extra_lookback_days: int = 0,
) -> int:
    """Read ``source`` parquet, slice to the window, write ``out``. Returns rows written.

    Also writes ``slice.json`` beside ``out``. Windowed parquets all land at the same
    path whatever window they hold, so without it a recipe pointing at one cannot say
    which window it got — the ambiguity #143 exists to remove.
    """
    table = pq.read_table(source)
    sliced = slice_to_window(
        table, window_start, window_end, extra_lookback_days=extra_lookback_days
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(sliced, out)
    (out.parent / "slice.json").write_text(
        json.dumps(
            {
                "source_table": str(source),
                "card_window": {"start": window_start, "end": window_end},
                "extra_lookback_days": extra_lookback_days,
                "effective_window": {
                    "start": effective_start(window_start, extra_lookback_days),
                    "end": window_end,
                },
                "rows": sliced.num_rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return sliced.num_rows
