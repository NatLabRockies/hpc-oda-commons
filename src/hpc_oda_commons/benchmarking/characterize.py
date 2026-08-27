"""Arrow-native dataset characterization + rolling-benchmark window selection.

Everything here operates on a :class:`pyarrow.Table` (never a Python ``list[dict]``) so it
scales to the largest registered datasets (~14M rows) without materializing the whole table.

Two public entry points:

* :func:`characterize_table` — span, daily-volume profile, job rate, **temporal-gap health**,
  per-column cardinality + missingness, and the runtime-target distribution.
* :func:`select_window` — apply the agreed rule (place a ``train_days + test_days`` window's
  end at ``anchor`` of the healthy span, then health-gate and shift off any missing block).

Both return plain JSON-serializable dicts, matching the report style used elsewhere in the
codebase (e.g. ``schema.quality_rules.build_quality_report``).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc

CARD_SCHEMA_VERSION = "oda.dataset_card.v0.1.0"

# Defaults for the health gate + window rule (see docs/benchmarking/methodology.md).
DEFAULT_ANCHOR = 0.80
DEFAULT_TRAIN_DAYS = 60
# Ninety days of scoring, raised from 30 (#191). Thirty could not contain an allocation
# cycle, a semester boundary, or more than one maintenance outage, so every leaderboard
# number rested on a single month of one machine's life.
DEFAULT_TEST_DAYS = 90
# How much history the earliest scored window must be able to see. This is the budget the
# lookback arms are measured against, and it lives on the card because one value does not
# suit every source: it was the module constant ``matrix.SLICE_HISTORY_DAYS`` (#191).
DEFAULT_HISTORY_DAYS = 120
# The evaluation is what gets given up when a source cannot afford both, but not below this.
# A shorter run than the benchmark's previous length would be a regression, not a compromise.
MIN_TEST_DAYS = 30
DEFAULT_GAP_MIN_DAYS = 3
DEFAULT_GAP_FLOOR_FRAC = 0.05
DEFAULT_ROBUST_Q = 0.001  # trim the outer 0.1% of submit timestamps (corrupt/epoch-era rows)

# Columns characterized for cardinality/missingness when present (categorical features that
# drive per-window model cost). First-present wins across schemas.
DEFAULT_CATEGORICAL_FIELDS = ("queue", "partition", "user", "account", "job_state")

_SECONDS_PER_DAY = 86_400


class CharacterizeError(ValueError):
    """Raised when a table cannot be characterized (missing/empty time axis)."""


def _to_datetime64_seconds(column: pa.ChunkedArray) -> np.ndarray:
    """A timestamp column → int64 epoch-seconds numpy array (nulls dropped)."""
    valid = column.filter(pc.is_valid(column))
    if len(valid) == 0:
        return np.empty(0, dtype="int64")
    arr = valid.to_numpy(zero_copy_only=False).astype("datetime64[s]").astype("int64")
    return arr


def _iso_day(epoch_day: int) -> str:
    return np.datetime64(int(epoch_day), "D").astype("datetime64[D]").astype(str)


def _daily_counts(epoch_seconds: np.ndarray, lo_day: int, hi_day: int) -> np.ndarray:
    """Job counts per calendar day over the inclusive day range ``[lo_day, hi_day]``."""
    days = (epoch_seconds // _SECONDS_PER_DAY).astype("int64")
    n = hi_day - lo_day + 1
    series = np.zeros(n, dtype="int64")
    in_range = days[(days >= lo_day) & (days <= hi_day)] - lo_day
    if in_range.size:
        np.add.at(series, in_range, 1)
    return series


def _find_gap_ranges(
    series: np.ndarray, lo_day: int, floor: float, gap_min_days: int
) -> list[tuple[int, int]]:
    """Missing blocks: runs of ``>= gap_min_days`` consecutive days below ``floor``.

    Returned as inclusive ``(start_day, end_day)`` epoch-day integer ranges.
    """
    dead = series < floor
    ranges: list[tuple[int, int]] = []
    i = 0
    n = len(series)
    while i < n:
        if not dead[i]:
            i += 1
            continue
        j = i
        while j < n and dead[j]:
            j += 1
        if j - i >= gap_min_days:
            ranges.append((lo_day + i, lo_day + j - 1))
        i = j
    return ranges


def _gaps_to_dicts(ranges: list[tuple[int, int]]) -> list[dict[str, Any]]:
    return [{"start": _iso_day(a), "end": _iso_day(b), "days": int(b - a + 1)} for a, b in ranges]


def characterize_table(
    table: pa.Table,
    *,
    submit_field: str = "submit_time",
    runtime_field: str = "runtime_seconds",
    categorical_fields: tuple[str, ...] = DEFAULT_CATEGORICAL_FIELDS,
    gap_min_days: int = DEFAULT_GAP_MIN_DAYS,
    gap_floor_frac: float = DEFAULT_GAP_FLOOR_FRAC,
    robust_q: float = DEFAULT_ROBUST_Q,
) -> dict[str, Any]:
    """Characterize a canonical job table for benchmark-window selection.

    Returns a dict with ``n_rows``, ``full_span``, ``healthy_span`` (outlier-trimmed),
    ``daily_volume`` stats, ``rate_per_day``, ``gaps`` (missing blocks), per-column
    ``columns`` cardinality/missingness, ``runtime_seconds`` distribution, and the private
    ``_daily`` series used by :func:`select_window`.
    """
    if submit_field not in table.column_names:
        raise CharacterizeError(f"table has no {submit_field!r} column to characterize")

    epoch = _to_datetime64_seconds(table.column(submit_field))
    if epoch.size == 0:
        raise CharacterizeError(f"{submit_field!r} is entirely null; cannot characterize")

    full_lo, full_hi = int(epoch.min()), int(epoch.max())
    # Robust healthy span: trim the outer robust_q on each side (drops corrupt/epoch rows).
    lo_s, hi_s = (int(x) for x in np.quantile(epoch, [robust_q, 1.0 - robust_q]))
    lo_day, hi_day = lo_s // _SECONDS_PER_DAY, hi_s // _SECONDS_PER_DAY
    span_days = int(hi_day - lo_day + 1)

    series = _daily_counts(epoch, lo_day, hi_day)
    active = series[series > 0]
    daily_median = float(np.median(active)) if active.size else 0.0
    floor = max(1.0, gap_floor_frac * daily_median)
    gap_ranges = _find_gap_ranges(series, lo_day, floor, gap_min_days)
    gaps = _gaps_to_dicts(gap_ranges)
    rows_in_span = int(series.sum())

    columns: dict[str, Any] = {}
    for field in categorical_fields:
        if field not in table.column_names:
            continue
        col = table.column(field)
        n = table.num_rows or 1
        columns[field] = {
            "cardinality": int(pc.count_distinct(col).as_py()),
            "missingness": round(pc.sum(pc.is_null(col)).as_py() / n, 6),
        }

    runtime_stats: dict[str, Any] = {}
    if runtime_field in table.column_names:
        rt = table.column(runtime_field)
        rt = rt.filter(pc.is_valid(rt))
        if len(rt):
            vals = rt.to_numpy(zero_copy_only=False).astype("float64")
            q = np.quantile(vals, [0.5, 0.9, 0.99])
            runtime_stats = {
                "min": float(vals.min()),
                "median": round(float(q[0]), 1),
                "p90": round(float(q[1]), 1),
                "p99": round(float(q[2]), 1),
                "max": float(vals.max()),
            }

    return {
        "n_rows": table.num_rows,
        "full_span": {
            "start": _iso_day(full_lo // _SECONDS_PER_DAY),
            "end": _iso_day(full_hi // _SECONDS_PER_DAY),
        },
        "healthy_span": {
            "start": _iso_day(lo_day),
            "end": _iso_day(hi_day),
            "days": span_days,
            "rows": rows_in_span,
        },
        "daily_volume": {
            "median": round(daily_median, 1),
            "min": int(active.min()) if active.size else 0,
            "max": int(series.max()) if series.size else 0,
            "gap_floor": round(floor, 1),
        },
        "rate_per_day": round(rows_in_span / span_days, 1) if span_days else 0.0,
        "gaps": gaps,
        "columns": columns,
        "runtime_seconds": runtime_stats,
        # private: consumed by select_window, stripped before the card is written.
        "_daily": {
            "lo_day": int(lo_day),
            "series": series.tolist(),
            "floor": float(floor),
            "gaps": [[int(a), int(b)] for a, b in gap_ranges],
        },
    }


def _overlapping_gaps(
    gap_ranges: list[tuple[int, int]], start_day: int, end_day: int
) -> list[tuple[int, int]]:
    """Missing blocks that intersect ``[start_day, end_day]`` at all (even partially)."""
    return [(a, b) for (a, b) in gap_ranges if a <= end_day and b >= start_day]


def fit_history_budget(
    span_days: int,
    *,
    history_days: int = DEFAULT_HISTORY_DAYS,
    test_days: int = DEFAULT_TEST_DAYS,
    train_days: int = DEFAULT_TRAIN_DAYS,
    min_test_days: int = MIN_TEST_DAYS,
) -> dict[str, Any]:
    """The largest ``(history, test, train)`` a span can support, and what it cost.

    The window rule used to check only that ``train_days + test_days`` fitted the healthy
    span. It never checked that the history the split needs *before* that window exists, which
    is how ``atlas_opentrinity`` came to run a "120d" lookback arm against a source holding 80
    days in total: the slice asked to reach back, got nothing, and said nothing (#191).

    Evaluation is surrendered before history. An arm labelled 120d that silently trained on 50
    is a *wrong* number; a shorter evaluation is merely a weaker one, and it says so.
    """
    requested = {
        "history_days": int(history_days),
        "test_days": int(test_days),
        "train_days": int(train_days),
    }
    history, test = int(history_days), int(test_days)
    if history + test > span_days:
        test = max(min_test_days, span_days - history)
    if history + test > span_days:
        history = span_days - test
    if history < 1:
        # A span too small for even the floor: split it rather than fail. Characterizing a
        # tiny table is still useful, and the shortfall flag carries the news.
        test = max(1, span_days // 3)
        history = max(1, span_days - test)
    # Never claim more in-window training than the budget itself covers.
    train = min(int(train_days), history)
    return {
        "history_days": int(history),
        "test_days": int(test),
        "train_days": int(train),
        "requested": requested,
        "shortfall": (history, test) != (requested["history_days"], requested["test_days"]),
    }


def select_window(
    characterization: dict[str, Any],
    *,
    anchor: float = DEFAULT_ANCHOR,
    train_days: int = DEFAULT_TRAIN_DAYS,
    test_days: int = DEFAULT_TEST_DAYS,
    history_days: int = DEFAULT_HISTORY_DAYS,
    gap_min_days: int = DEFAULT_GAP_MIN_DAYS,
) -> dict[str, Any]:
    """Choose the rolling-benchmark window per the agreed rule + health gate.

    Places the ``train_days + test_days`` window's END at ``anchor`` of the healthy span,
    then rejects any window that **overlaps a missing block at all** (even partially -- so the
    window never clips the edge of an outage) and shifts to the nearest window clear of every
    block. Returns dates, in-window rows/rate, health verdict, and rationale.

    A candidate must also leave ``history_days`` of data behind its test region, so the
    longest lookback arm is backed by real history rather than by whatever happens to exist
    (#191). History may contain gaps -- a model simply trains on the rows that are there --
    but it may not be absent.
    """
    daily = characterization.get("_daily")
    if daily is None:
        raise CharacterizeError("characterization is missing daily series; run characterize_table")
    lo_day = int(daily["lo_day"])
    series = np.asarray(daily["series"], dtype="int64")
    gap_ranges = [(int(a), int(b)) for a, b in daily.get("gaps", [])]
    span_days = len(series)

    budget = fit_history_budget(
        span_days, history_days=history_days, test_days=test_days, train_days=train_days
    )
    train_days = budget["train_days"]
    test_days = budget["test_days"]
    history_days = budget["history_days"]
    win_days = train_days + test_days
    shortfall_note = (
        ""
        if not budget["shortfall"]
        else (
            f" Source affords {span_days}d, short of the "
            f"{budget['requested']['history_days']}d history + "
            f"{budget['requested']['test_days']}d evaluation requested, so this card runs "
            f"{history_days}d + {test_days}d."
        )
    )

    max_end = lo_day + span_days - 1
    # The earliest end that leaves both a full window and its history behind it.
    min_end = lo_day + max(win_days, history_days + test_days) - 1
    if min_end > max_end:
        # Cannot happen once the budget has been fitted, but a caller may pass a span the
        # budget could only degrade; use the whole span rather than return a window that
        # reaches outside it.
        start_day, end_day = lo_day, max_end
        overlaps = _overlapping_gaps(gap_ranges, start_day, end_day)
        return _window_result(
            lo_day,
            series,
            start_day,
            end_day,
            train_days,
            test_days,
            history_days,
            anchor,
            _gaps_to_dicts(overlaps),
            healthy=not overlaps,
            budget=budget,
            rationale=(
                f"healthy span is only {span_days}d; used the whole span."
                f"{shortfall_note} {_gap_note(_gaps_to_dicts(overlaps))}"
            ),
        )

    def _clamp(e: int) -> int:
        return max(min_end, min(max_end, e))

    anchor_end = _clamp(lo_day + int(round(anchor * (span_days - 1))))

    # Candidate ends: the anchor first, then nearest neighbours outward, all within bounds.
    seen: set[int] = set()
    for delta in range(0, span_days):
        for cand in (anchor_end + delta, anchor_end - delta):
            e = _clamp(cand)
            if e in seen:
                continue
            seen.add(e)
            if not _overlapping_gaps(gap_ranges, e - win_days + 1, e):
                shift = abs(e - anchor_end)
                rationale = (
                    f"window END at {anchor:.0%} of healthy span; clear of all missing blocks."
                    if shift == 0
                    else (
                        f"anchor ({anchor:.0%}) window overlapped a missing block; shifted "
                        f"{shift}d to the nearest window clear of every block."
                    )
                )
                return _window_result(
                    lo_day,
                    series,
                    e - win_days + 1,
                    e,
                    train_days,
                    test_days,
                    history_days,
                    anchor,
                    [],
                    healthy=True,
                    budget=budget,
                    rationale=rationale + shortfall_note,
                )

    # No block-free window anywhere -- return the anchor window flagged unhealthy.
    overlaps = _overlapping_gaps(gap_ranges, anchor_end - win_days + 1, anchor_end)
    return _window_result(
        lo_day,
        series,
        anchor_end - win_days + 1,
        anchor_end,
        train_days,
        test_days,
        history_days,
        anchor,
        _gaps_to_dicts(overlaps),
        healthy=False,
        budget=budget,
        rationale=(
            "NO window clear of all missing blocks exists at this size; returned the anchor "
            f"window.{shortfall_note} {_gap_note(_gaps_to_dicts(overlaps))} — seek other "
            "months or widen the window."
        ),
    )


def _gap_note(gaps: list[dict[str, Any]]) -> str:
    if not gaps:
        return "No missing blocks."
    parts = ", ".join(f"{g['start']}..{g['end']} ({g['days']}d)" for g in gaps)
    return f"Missing block(s): {parts}."


def _window_result(
    lo_day: int,
    series: np.ndarray,
    start_day: int,
    end_day: int,
    train_days: int,
    test_days: int,
    history_days: int,
    anchor: float,
    gaps: list[dict[str, Any]],
    *,
    healthy: bool,
    rationale: str,
    budget: dict[str, Any] | None = None,
) -> dict[str, Any]:
    a, b = start_day - lo_day, end_day - lo_day
    rows = int(series[max(0, a) : b + 1].sum())
    win_days = train_days + test_days
    test_start_day = end_day - test_days + 1
    rule: dict[str, Any] = {
        "anchor": anchor,
        "train_days": train_days,
        "test_days": test_days,
        "history_days": history_days,
    }
    if budget is not None and budget.get("shortfall"):
        # Named, not silently smaller: a reader comparing two cards must be able to see that
        # one of them is running a shorter evaluation and why (#191).
        rule["requested"] = budget["requested"]
        rule["shortfall"] = True
    return {
        "rule": rule,
        "window_start": _iso_day(start_day),
        "window_end": _iso_day(end_day),
        "test_start": _iso_day(test_start_day),
        "test_end": _iso_day(end_day),
        "n_rows": rows,
        "rate_per_day": round(rows / win_days, 1) if win_days else 0.0,
        "gaps_in_window": gaps,
        "healthy": bool(healthy),
        "rationale": rationale,
    }
