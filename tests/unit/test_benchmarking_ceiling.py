"""Unit tests for the ceiling analysis (#169)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pyarrow as pa
import pytest

from hpc_oda_commons.benchmarking.ceiling import (
    CeilingError,
    build_split_grid,
    causal_memorization,
    compute_ceiling,
    grouped_floor,
    signature_codes,
)
from hpc_oda_commons.models.rolling_tabular.split import build_rolling_splits

UTC = dt.timezone.utc


def _table(rows: list[dict]) -> pa.Table:
    cols = {k: [r.get(k) for r in rows] for k in rows[0]}
    return pa.table(cols)


def _jobs(n: int, *, start: dt.datetime | None = None, step_min: int = 30) -> list[dict]:
    start = start or dt.datetime(2026, 1, 1, tzinfo=UTC)
    out = []
    for i in range(n):
        s = start + dt.timedelta(minutes=i * step_min)
        out.append(
            {
                "submit_time": s,
                "end_time": s + dt.timedelta(minutes=10),
                "partition": "debug" if i % 2 == 0 else "compute",
                "user": f"u{i % 3}",
                "runtime_seconds": float(100 + (i % 5) * 10),
            }
        )
    return out


# --- the floor is exact ---------------------------------------------------------------


def test_floor_is_the_hand_computed_minimum() -> None:
    """Skewed on purpose so median != mean, which pins the statistic, not just the value.

    Group A [10, 20, 300]: median 20, mean 110. Group B [100, 140]: both 120.
    """
    y = np.array([10.0, 20.0, 300.0, 100.0, 140.0])
    codes = np.array([0, 0, 0, 1, 1])

    f = grouped_floor(y, codes)

    # MAE uses MEDIANS (20, 120): 10 + 0 + 280 + 20 + 20 = 330, over 5 rows
    assert f.mae == pytest.approx(66.0)
    # RMSE uses MEANS (110, 120): 100^2 + 90^2 + 190^2 + 20^2 + 20^2 = 55,000, over 5
    assert f.rmse == pytest.approx(np.sqrt(11_000.0))
    assert f.n_groups == 2
    # and the mismatched pairing is strictly worse in both directions
    assert f.mae < np.abs(y - np.array([110.0, 110.0, 110.0, 120.0, 120.0])).mean()


def test_the_minimising_statistic_matches_the_metric() -> None:
    """Median minimises MAE, mean minimises RMSE. Pairing them wrongly is strictly worse."""
    rng = np.random.default_rng(0)
    y = rng.lognormal(3.0, 1.5, size=2000)
    codes = rng.integers(0, 40, size=2000)

    f = grouped_floor(y, codes)

    order = np.lexsort((y, codes))
    cs, ys = codes[order], y[order]
    starts = np.concatenate(([0], np.flatnonzero(np.diff(cs)) + 1))
    sizes = np.diff(np.concatenate((starts, [cs.size])))
    means = np.repeat(np.add.reduceat(ys, starts) / sizes, sizes)
    mid = starts + sizes // 2
    meds = np.repeat(
        np.where(sizes % 2 == 1, ys[mid], (ys[np.maximum(mid - 1, starts)] + ys[mid]) / 2.0), sizes
    )

    assert f.mae < np.abs(ys - means).mean()  # median beats mean for MAE
    assert f.rmse < np.sqrt(((ys - meds) ** 2).mean())  # mean beats median for RMSE


def test_a_group_of_one_contributes_no_error() -> None:
    """Correct, not a leak: a function mapping that signature to that value exists.

    This is what makes the number a bound rather than an estimate, and it is why the
    group-size distribution has to be reported with it.
    """
    f = grouped_floor(np.array([5.0, 7.0, 999.0]), np.array([0, 0, 1]))

    assert f.group_sizes.tolist() == [2, 1]
    assert f.size_summary()["singleton_row_share"] == pytest.approx(1 / 3)
    assert f.mae == pytest.approx((1.0 + 1.0 + 0.0) / 3)


def test_a_finer_grouping_never_raises_the_floor() -> None:
    """Floors are monotone in the fineness of Z -- and reach zero when every row is alone."""
    rng = np.random.default_rng(1)
    y = rng.normal(500, 100, size=600)
    coarse = rng.integers(0, 5, size=600)
    finer = coarse * 100 + rng.integers(0, 100, size=600)

    assert grouped_floor(y, finer).mae <= grouped_floor(y, coarse).mae
    assert grouped_floor(y, np.arange(600)).mae == pytest.approx(0.0)


# --- signatures -----------------------------------------------------------------------


def test_nulls_are_a_signature_value_not_missing_data() -> None:
    """Two jobs that both omitted a field are indistinguishable in exactly the way we mean."""
    t = pa.table({"a": ["x", None, None, "x"], "b": [1, 1, 1, 2]})

    codes = signature_codes(t, ["a", "b"])

    assert codes[1] == codes[2]  # both null-a, b=1
    assert codes[0] != codes[3]  # same a, different b


# --- the split grid matches the shipped implementation ---------------------------------


def test_split_grid_matches_build_rolling_splits() -> None:
    """The grid is recomputed with searchsorted for cost; equivalence is pinned, not assumed.

    ``build_rolling_splits`` materialises a Python tuple of row indices per window from a
    full scan, which at benchmark scale costs hundreds of millions of int objects.
    """
    rows = _jobs(400)
    table = _table(rows)
    kw = dict(n_windows=12, test_window_hours=6, training_lookback_days=30)

    reference = build_rolling_splits(rows, **kw)
    grid = build_split_grid(table, **kw)

    assert grid.split_epochs.size == len(reference)
    for i, ref in enumerate(reference):
        assert int(grid.split_epochs[i]) == ref.split_epoch
        assert sorted(grid.test_indices(i).tolist()) == sorted(ref.test_row_indices)
        got = grid.train_indices(i, kw["training_lookback_days"] * 86400)
        assert sorted(got.tolist()) == sorted(ref.train_row_indices)


# --- causal memorization ---------------------------------------------------------------


def test_training_rows_are_strictly_in_the_past() -> None:
    """The causality guarantee, asserted directly: no training row ends at or after the split.

    Everything the memorization strategy claims rests on this. A row that ended after the
    window opened would be information the predictor could not have had.
    """
    rows = _jobs(400)
    table = _table(rows)
    grid = build_split_grid(table, n_windows=12, test_window_hours=6, training_lookback_days=30)
    ends = np.array([r["end_time"].replace(tzinfo=UTC).timestamp() for r in rows], dtype=float)
    lookback = 30 * 86400

    seen_any = False
    for i in range(grid.split_epochs.size):
        t = grid.split_epochs[i]
        train = grid.train_indices(i, lookback)
        if train.size:
            seen_any = True
            assert ends[train].max() < t
            assert ends[train].min() >= t - lookback
    assert seen_any  # guard: an empty grid would pass the loop vacuously


def test_memorization_ignores_rows_it_can_never_see() -> None:
    """Changing rows outside every train and test window must not move the score."""
    rows = _jobs(300)
    table_a = _table(rows)
    kw = dict(n_windows=6, test_window_hours=6, training_lookback_days=1)
    grid = build_split_grid(table_a, **kw)

    reachable = set()
    for i in range(grid.split_epochs.size):
        reachable.update(grid.test_indices(i).tolist())
        reachable.update(grid.train_indices(i, 86400).tolist())
    untouched = [i for i in range(len(rows)) if i not in reachable]
    assert untouched  # guard: the point of the test is that some rows are unreachable

    edited = [dict(r) for r in rows]
    for i in untouched:
        edited[i]["runtime_seconds"] = 9_999_999.0
    table_b = _table(edited)

    def score(tbl, rws):
        y = np.array([r["runtime_seconds"] for r in rws], dtype=float)
        codes = [signature_codes(tbl, ["partition", "user"])]
        g = build_split_grid(tbl, **kw)
        return causal_memorization(y, codes, g, lookback_days=1)["mae"]

    assert score(table_a, rows) == pytest.approx(score(table_b, edited))


def test_unlimited_lookback_is_not_the_configured_lookback() -> None:
    """Regression: None once meant both 'unlimited' and 'the configured value' (#169)."""
    rows = _jobs(600, step_min=240)  # spans ~100 days
    table = _table(rows)
    grid = build_split_grid(table, n_windows=6, test_window_hours=6, training_lookback_days=5)

    unlimited = grid.train_indices(3, None)
    limited = grid.train_indices(3, 5 * 86400)

    assert unlimited.size > limited.size


# --- end to end ------------------------------------------------------------------------


def test_compute_ceiling_is_deterministic_and_self_consistent() -> None:
    """Unlike fitted-model metrics, this is exactly reproducible -- no BLAS, no fitting."""
    table = _table(_jobs(500))
    kw = dict(feature_fields=["partition", "user"], n_windows=10, test_window_hours=6)

    a = compute_ceiling(table, **kw)
    b = compute_ceiling(table, **kw)

    assert a == b
    assert a["floor"]["mae"] <= a["causal_memorization"]["sweep"]["all"]["mae"]
    assert a["scored_rows"] > 0
    assert [c["cost"] for c in a["feature_cost"]] == sorted(c["cost"] for c in a["feature_cost"])


def test_a_table_without_the_target_is_rejected() -> None:
    table = pa.table({"submit_time": [dt.datetime(2026, 1, 1, tzinfo=UTC)]})

    with pytest.raises(CeilingError, match="runtime_seconds"):
        compute_ceiling(table, feature_fields=["submit_time"])
