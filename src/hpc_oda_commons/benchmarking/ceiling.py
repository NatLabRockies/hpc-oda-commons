"""How much accuracy was actually available? The floor no submit-time model can beat.

A leaderboard MAE is uncalibrated on its own: 11,731 on one machine and 4,006 on another
says nothing about how much was obtainable in either. This computes that bound.

Two jobs whose submit-time features are identical cannot be told apart by any predictor
restricted to those features. So for a conditioning set ``Z`` (the feature signature) and a
metric ``M``, the smallest achievable error over the scored rows is

    Floor_M(Z) = min_f (1/N) sum_i M(y_i, f(z_i))

which decomposes per group and has a closed form. **The minimising statistic depends on the
metric**: the median for MAE, the mean for RMSE. Measured on one dataset, pairing them the
wrong way costs 17% (MAE via mean) and 12% (RMSE via median), so they are computed as a pair
rather than picking one statistic for both.

This is **exact, not an estimate**. A group of one contributing zero error is correct: a
function mapping that signature to that value exists and is a legitimate predictor. That is
what makes it a bound rather than a guess. It also means floors are monotone -- refine ``Z``
and the floor falls, reaching zero when every row is its own group -- so the group-size
distribution is reported alongside, without which a floor cannot be judged tight or vacuous.

Alongside the bound, ``causal_memorization`` measures a *real* strategy: predict from
same-signature jobs that finished strictly earlier. It is not a bound (a better causal
predictor could pool across similar signatures) but it is deployable, and on several
datasets it beats every fitted model in the benchmark.

Deliberately absent: leave-one-out. It is neither the floor (the optimal function has no
"leave out" in its definition) nor achievable (a row's peers include jobs that ran *after*
it, so it is not causal). It answers neither question. See #169.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc

CEILING_SCHEMA_VERSION = "oda.ceiling.v0.1.0"

DEFAULT_LOOKBACKS: tuple[tuple[str, int | None], ...] = (
    ("1d", 1),
    ("10d", 10),
    ("30d", 30),
    ("60d", 60),
    ("120d", 120),
    ("all", None),
)
_DAY_SECONDS = 86_400.0


class CeilingError(ValueError):
    """Raised when a table cannot support a ceiling analysis."""


# --- signatures ---------------------------------------------------------------------


def _column_codes(column: pa.ChunkedArray) -> np.ndarray:
    """Dense integer codes for a column's distinct values; nulls get their own code.

    Nulls are a value here, not missing data: two jobs that both omitted a field are
    indistinguishable in exactly the way this analysis is about.
    """
    encoded = pc.dictionary_encode(column.combine_chunks())
    idx = encoded.indices.fill_null(-1).to_numpy(zero_copy_only=False)
    return idx.astype(np.int64) + 1


def signature_codes(table: pa.Table, fields: list[str]) -> np.ndarray:
    """Dense codes identifying each row's distinct combination of ``fields``.

    Combined pairwise and re-compacted at each step, so the code space stays bounded by the
    row count instead of by the product of cardinalities.
    """
    if not fields:
        return np.zeros(table.num_rows, dtype=np.int64)
    codes = _column_codes(table.column(fields[0]))
    for name in fields[1:]:
        nxt = _column_codes(table.column(name))
        combined = codes * (int(nxt.max()) + 1) + nxt
        codes = np.unique(combined, return_inverse=True)[1].astype(np.int64)
    return codes


# --- grouped statistics -------------------------------------------------------------


@dataclass(frozen=True)
class GroupedFloor:
    """Exact minimum error over all functions of the grouping, for both metrics."""

    mae: float
    rmse: float
    n_rows: int
    n_groups: int
    group_sizes: np.ndarray  # per group, ascending code order

    def size_summary(self) -> dict[str, Any]:
        s = self.group_sizes
        if s.size == 0:
            return {"min": 0, "median": 0, "max": 0, "singleton_row_share": 0.0}
        return {
            "min": int(s.min()),
            "median": float(np.median(s)),
            "max": int(s.max()),
            # share of ROWS in groups of one -- the rows the bound cannot constrain
            "singleton_row_share": float(s[s == 1].sum() / s.sum()),
        }


def grouped_floor(y: np.ndarray, codes: np.ndarray) -> GroupedFloor:
    """Exact ``Floor_MAE`` (group medians) and ``Floor_RMSE`` (group means)."""
    if y.size == 0:
        return GroupedFloor(0.0, 0.0, 0, 0, np.empty(0, dtype=np.int64))

    order = np.lexsort((y, codes))  # by group, then by value within group
    cs, ys = codes[order], y[order]
    starts = np.concatenate(([0], np.flatnonzero(np.diff(cs)) + 1))
    sizes = np.diff(np.concatenate((starts, [cs.size])))

    # Median of a sorted run. For even sizes any point between the two central order
    # statistics minimises the absolute deviation; the midpoint is one such point.
    mid = starts + sizes // 2
    odd = (sizes % 2) == 1
    med = np.where(odd, ys[mid], (ys[np.maximum(mid - 1, starts)] + ys[mid]) / 2.0)
    mean = np.add.reduceat(ys, starts) / sizes

    per_row_med = np.repeat(med, sizes)
    per_row_mean = np.repeat(mean, sizes)
    return GroupedFloor(
        mae=float(np.abs(ys - per_row_med).mean()),
        rmse=float(np.sqrt(((ys - per_row_mean) ** 2).mean())),
        n_rows=int(y.size),
        n_groups=int(sizes.size),
        group_sizes=sizes,
    )


def _group_medians(y: np.ndarray, codes: np.ndarray, n_codes: int) -> np.ndarray:
    """Lookup array of per-code medians; NaN for codes absent from ``codes``."""
    out = np.full(n_codes, np.nan)
    if y.size == 0:
        return out
    order = np.lexsort((y, codes))
    cs, ys = codes[order], y[order]
    starts = np.concatenate(([0], np.flatnonzero(np.diff(cs)) + 1))
    sizes = np.diff(np.concatenate((starts, [cs.size])))
    mid = starts + sizes // 2
    odd = (sizes % 2) == 1
    out[cs[starts]] = np.where(odd, ys[mid], (ys[np.maximum(mid - 1, starts)] + ys[mid]) / 2.0)
    return out


# --- the rolling split grid ---------------------------------------------------------


def _epoch_seconds(column: pa.ChunkedArray) -> np.ndarray:
    """Timestamps as float epoch seconds; NaN where null."""
    arr = column.combine_chunks()
    if not pa.types.is_timestamp(arr.type):
        raise CeilingError(f"expected a timestamp column, got {arr.type}")
    # Scale from the column's own unit rather than casting to seconds: a cast would refuse
    # microsecond data as lossy, and sub-second precision matters at window boundaries.
    ticks = {"s": 1.0, "ms": 1e3, "us": 1e6, "ns": 1e9}[arr.type.unit]
    raw = arr.cast(pa.int64()).to_numpy(zero_copy_only=False).astype("float64")
    out = raw / ticks
    out[pc.is_null(arr).to_numpy(zero_copy_only=False)] = np.nan
    return out


@dataclass(frozen=True)
class SplitGrid:
    """The benchmark's rolling windows, as index arrays rather than Python tuples."""

    split_epochs: np.ndarray  # window start, seconds
    test_window_seconds: int
    lookback_seconds: int
    _submit_order: np.ndarray
    _submit_sorted: np.ndarray
    _end_order: np.ndarray
    _end_sorted: np.ndarray

    def test_indices(self, i: int) -> np.ndarray:
        """Rows SUBMITTED within window ``i``."""
        t = self.split_epochs[i]
        lo = np.searchsorted(self._submit_sorted, t, "left")
        hi = np.searchsorted(self._submit_sorted, t + self.test_window_seconds, "left")
        return self._submit_order[lo:hi]

    def train_indices(self, i: int, lookback_seconds: float | None) -> np.ndarray:
        """Rows that FINISHED strictly before window ``i`` starts, within the lookback.

        ``lookback_seconds=None`` means unlimited history. It is required rather than
        defaulted: letting None also mean "the configured lookback" made the unlimited arm
        of the sweep silently run at 120 days.
        """
        t = self.split_epochs[i]
        hi = np.searchsorted(self._end_sorted, t, "left")
        lo = (
            0
            if lookback_seconds is None
            else np.searchsorted(self._end_sorted, t - lookback_seconds, "left")
        )
        return self._end_order[lo:hi]


def build_split_grid(
    table: pa.Table,
    *,
    n_windows: int,
    test_window_hours: int,
    training_lookback_days: int,
    submit_field: str = "submit_time",
    end_field: str = "end_time",
) -> SplitGrid:
    """The same window grid ``build_rolling_splits`` defines, computed with searchsorted.

    The shipped implementation materialises a Python tuple of row indices per window from a
    full scan, which at benchmark scale (120 windows over millions of rows) costs hundreds
    of millions of int objects. The rule itself is simple and exactly specified, so this
    derives the same windows in O(n log n) once. Equivalence is pinned by a conformance
    test against ``build_rolling_splits`` rather than assumed.
    """
    submit = _epoch_seconds(table.column(submit_field))
    end = _epoch_seconds(table.column(end_field))
    if not np.isfinite(submit).any():
        raise CeilingError(f"{submit_field!r} is entirely null; cannot build split windows")

    hour = 3600.0
    latest_hour = np.floor(np.nanmax(submit) / hour) * hour
    step = test_window_hours * hour
    start = latest_hour - (n_windows - 1) * step
    split_epochs = start + np.arange(n_windows) * step

    s_ok = np.flatnonzero(np.isfinite(submit))
    s_order = s_ok[np.argsort(submit[s_ok], kind="stable")]
    e_ok = np.flatnonzero(np.isfinite(end))
    e_order = e_ok[np.argsort(end[e_ok], kind="stable")]
    return SplitGrid(
        split_epochs=split_epochs,
        test_window_seconds=int(step),
        lookback_seconds=int(training_lookback_days * _DAY_SECONDS),
        _submit_order=s_order,
        _submit_sorted=submit[s_order],
        _end_order=e_order,
        _end_sorted=end[e_order],
    )


# --- causal memorization ------------------------------------------------------------


def causal_memorization(
    y: np.ndarray,
    codes_by_level: list[np.ndarray],
    grid: SplitGrid,
    *,
    lookback_days: int | None,
    max_backoff: int = 0,
) -> dict[str, float]:
    """Predict from same-signature jobs that finished strictly earlier. A real strategy.

    ``codes_by_level[0]`` is the full signature; each later level drops one more feature,
    cheapest-first by measured information cost, and is consulted only for rows the previous
    level could not match. ``max_backoff=0`` disables backoff, leaving a global-median
    fallback whose share is reported as ``coverage``.
    """
    back = None if lookback_days is None else int(lookback_days * _DAY_SECONDS)
    n_codes = [int(c.max()) + 1 if c.size else 1 for c in codes_by_level]
    finite = y[np.isfinite(y)]
    global_median = float(np.median(finite)) if finite.size else 0.0

    total_abs = 0.0
    n = 0
    matched = 0
    for i in range(grid.split_epochs.size):
        test = grid.test_indices(i)
        test = test[np.isfinite(y[test])]
        if test.size == 0:
            continue
        train = grid.train_indices(i, back)
        train = train[np.isfinite(y[train])]
        n += test.size

        pred = np.full(test.size, np.nan)
        if train.size:
            for level in range(min(max_backoff, len(codes_by_level) - 1) + 1):
                need = ~np.isfinite(pred)
                if not need.any():
                    break
                lookup = _group_medians(y[train], codes_by_level[level][train], n_codes[level])
                got = lookup[codes_by_level[level][test[need]]]
                pred[np.flatnonzero(need)] = got
                if level == 0:
                    matched += int(np.isfinite(got).sum())
            fallback = float(np.median(y[train]))
        else:
            fallback = global_median
        pred = np.where(np.isfinite(pred), pred, fallback)
        total_abs += float(np.abs(y[test] - pred).sum())

    return {
        "mae": total_abs / n if n else float("nan"),
        "coverage": matched / n if n else 0.0,
        "rows": n,
    }


# --- the analysis -------------------------------------------------------------------


def compute_ceiling(
    table: pa.Table,
    *,
    feature_fields: list[str],
    n_windows: int = 120,
    test_window_hours: int = 6,
    training_lookback_days: int = 120,
    target_field: str = "runtime_seconds",
    lookbacks: tuple[tuple[str, int | None], ...] = DEFAULT_LOOKBACKS,
    with_backoff: bool = True,
) -> dict[str, Any]:
    """Floor, per-feature information cost, and the causal lookback sweep for one table."""
    if target_field not in table.column_names:
        raise CeilingError(f"table has no {target_field!r} column")
    present = [f for f in feature_fields if f in table.column_names]
    if not present:
        raise CeilingError("none of the requested feature fields are present in the table")

    y = table.column(target_field).combine_chunks().to_numpy(zero_copy_only=False).astype(float)
    grid = build_split_grid(
        table,
        n_windows=n_windows,
        test_window_hours=test_window_hours,
        training_lookback_days=training_lookback_days,
    )

    scored = np.unique(np.concatenate([grid.test_indices(i) for i in range(n_windows)]))
    scored = scored[np.isfinite(y[scored])]
    if scored.size == 0:
        raise CeilingError("no scored rows: every rolling test window is empty")

    full = signature_codes(table, present)
    floor = grouped_floor(y[scored], full[scored])

    # Per-feature information cost: how much the floor rises without that feature. This
    # also orders the backoff -- cheapest first -- so the fallback gives up least.
    scored_table = table.take(pa.array(scored))
    y_scored = y[scored]
    costs = []
    for f in present:
        others = [x for x in present if x != f]
        alt = grouped_floor(y_scored, signature_codes(scored_table, others)) if others else None
        rise = (alt.mae - floor.mae) if alt else float("nan")
        costs.append({"feature": f, "floor_mae_without": alt.mae if alt else None, "cost": rise})
    costs.sort(key=lambda c: c["cost"] if c["cost"] == c["cost"] else -1.0)
    backoff_order = [c["feature"] for c in costs]

    codes_by_level = [full]
    for k in range(1, min(4, len(present))):
        kept = [f for f in present if f not in set(backoff_order[:k])]
        codes_by_level.append(signature_codes(table, kept) if kept else np.zeros_like(full))

    sweep = {}
    for label, days in lookbacks:
        sweep[label] = causal_memorization(y, codes_by_level, grid, lookback_days=days)
    best = min(sweep, key=lambda k: sweep[k]["mae"])

    result: dict[str, Any] = {
        "schema_version": CEILING_SCHEMA_VERSION,
        "split": {
            "n_windows": n_windows,
            "test_window_hours": test_window_hours,
            "training_lookback_days": training_lookback_days,
        },
        "scored_rows": int(scored.size),
        "feature_fields": present,
        "floor": {
            "mae": floor.mae,
            "rmse": floor.rmse,
            "signatures": floor.n_groups,
            "group_sizes": floor.size_summary(),
        },
        "feature_cost": costs,
        "causal_memorization": {
            "sweep": sweep,
            "best_lookback": best,
            "backoff_order": backoff_order,
        },
    }
    if with_backoff:
        bd = dict(lookbacks)[best]
        result["causal_memorization"]["backoff_at_best"] = causal_memorization(
            y, codes_by_level, grid, lookback_days=bd, max_backoff=3
        )
    return result
