"""Slice a canonical job table to a window: a runtime card's, or a recipe's declared one.

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
-- by default the card's ``history_days - train_days`` (``matrix.slice_extension_for``) --
leaving the test region untouched, so the run scores exactly the rows the card window
defines (#143, #170).

``read_window`` applies a recipe's declared ``dataset.window`` the same way at scan time,
so a recipe can read a full prepared table without a slice on disk.
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


def _pick_name(names: list[str], preferred: str, fallback: str) -> str:
    if preferred in names:
        return preferred
    if fallback in names:
        return fallback
    raise SliceError(
        f"table has neither {preferred!r} nor {fallback!r}; cannot slice to a window "
        f"(columns: {', '.join(names)})."
    )


def read_window(
    source: Path,
    window_start: str | None = None,
    window_end: str | None = None,
    *,
    extra_lookback_days: int = 0,
    require_nonnull: tuple[str, ...] | list[str] = (),
    drop_columns: tuple[str, ...] | list[str] = (),
    by: str = "overlap",
) -> pa.Table:
    """Read the rows of ``source`` that overlap a window, and have every column in
    ``require_nonnull``, filtering as the file is scanned (#249).

    The window keeps the same rows as :func:`slice_to_window`, in the same order. Filtering
    one batch at a time keeps memory to the rows kept, and keeps a large list column such
    as F-DATA's ``embedding`` clear of pyarrow's ``take``/``filter`` bug past 2^30 values
    (docs/known-issues.md). A window bound left as None does not filter on time.

    ``by="submit"`` keeps the jobs *submitted* in the window instead, for a benchmark
    defined by when jobs were submitted, as a source cut into submit months is (F-DATA).
    """
    if by not in ("overlap", "submit"):
        raise SliceError(f"window by must be 'overlap' or 'submit', got {by!r}")
    import pyarrow.dataset as ds

    dataset = ds.dataset(str(source), format="parquet")
    names = list(dataset.schema.names)
    expr = None
    if window_start is not None or window_end is not None:
        if window_start is None or window_end is None:
            raise SliceError("a window needs both a start and an end")
        submit = _pick_name(names, "submit_time", "start_time")
        end = _pick_name(names, "end_time", submit)
        lo = _day_start_utc(effective_start(window_start, extra_lookback_days))
        hi = _day_start_utc(window_end) + timedelta(days=1)  # inclusive of the whole end day
        bound = end if by == "overlap" else submit
        expr = (ds.field(submit) < pa.scalar(hi, type=dataset.schema.field(submit).type)) & (
            ds.field(bound) >= pa.scalar(lo, type=dataset.schema.field(bound).type)
        )
    for column in require_nonnull:
        if column not in names:
            raise SliceError(f"require_nonnull names {column!r}, which the table lacks")
        expr = ds.field(column).is_valid() if expr is None else expr & ds.field(column).is_valid()
    columns = [name for name in names if name not in set(drop_columns)]
    return dataset.to_table(columns=columns, filter=expr)


def slice_dataset(
    source: Path,
    out: Path,
    window_start: str,
    window_end: str,
    *,
    extra_lookback_days: int = 0,
    window_key: str = "card_window",
    drop_columns: tuple[str, ...] = (),
) -> int:
    """Read ``source`` parquet, slice to the window, write ``out``. Returns rows written.

    Also writes ``slice.json`` beside ``out``. Windowed parquets all land at the same
    path whatever window they hold, so without it a recipe pointing at one cannot say
    which window it got — the ambiguity #143 exists to remove. ``window_key`` names the
    requested window there: ``card_window`` when it came from a dataset card, ``window``
    when it was given by hand (``hpc-oda datasets slice``, #217).
    """
    sliced = read_window(
        source,
        window_start,
        window_end,
        extra_lookback_days=extra_lookback_days,
        drop_columns=drop_columns,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(sliced, out)
    (out.parent / "slice.json").write_text(
        json.dumps(
            {
                "source_table": str(source),
                window_key: {"start": window_start, "end": window_end},
                "extra_lookback_days": extra_lookback_days,
                "dropped_columns": list(drop_columns),
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
