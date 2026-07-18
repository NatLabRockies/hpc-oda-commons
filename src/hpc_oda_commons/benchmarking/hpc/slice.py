"""Slice a canonical job table to a dataset card's 90-day benchmark window.

The rolling-split benchmark keys **test** windows on ``submit_time`` and **training**
windows on ``end_time`` (``split_time - lookback <= end_time < split_time``). A job
submitted before the window but *ending* inside it is therefore a legitimate training
row. So the slice keeps every job whose ``[submit_time, end_time]`` interval overlaps the
card window — an overlap predicate, not a naive ``submit_time``-only cut — otherwise the
earliest rolling windows would silently lose training data.

Row count after slicing can slightly exceed the card's (submit-based) ``n_rows`` for
exactly this reason; that is expected.
"""

from __future__ import annotations

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


def slice_to_window(
    table: pa.Table,
    window_start: str,
    window_end: str,
    *,
    submit_field: str = "submit_time",
    end_field: str = "end_time",
) -> pa.Table:
    """Return rows whose ``[submit, end]`` interval overlaps ``[window_start, window_end]``.

    ``window_start``/``window_end`` are inclusive ISO day strings (``YYYY-MM-DD``); the
    upper bound is expanded to the end of ``window_end``'s day.
    """
    submit = _pick_field(table, submit_field, "start_time")
    end = _pick_field(table, end_field, submit)

    lo = _day_start_utc(window_start)
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
) -> int:
    """Read ``source`` parquet, slice to the window, write ``out``. Returns rows written."""
    table = pq.read_table(source)
    sliced = slice_to_window(table, window_start, window_end)
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(sliced, out)
    return sliced.num_rows
