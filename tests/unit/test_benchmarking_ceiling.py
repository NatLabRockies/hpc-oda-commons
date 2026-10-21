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
    kw = dict(n_windows=12, test_window_hours=6)

    reference = build_rolling_splits(rows, **kw, training_lookback_days=30)
    grid = build_split_grid(table, **kw)

    assert grid.split_epochs.size == len(reference)
    for i, ref in enumerate(reference):
        assert int(grid.split_epochs[i]) == ref.split_epoch
        assert sorted(grid.test_indices(i).tolist()) == sorted(ref.test_row_indices)
        got = grid.train_indices(i, 30 * 86400)
        assert sorted(got.tolist()) == sorted(ref.train_row_indices)


# --- causal memorization ---------------------------------------------------------------


def test_training_rows_are_strictly_in_the_past() -> None:
    """The causality guarantee, asserted directly: no training row ends at or after the split.

    Everything the memorization strategy claims rests on this. A row that ended after the
    window opened would be information the predictor could not have had.
    """
    rows = _jobs(400)
    table = _table(rows)
    grid = build_split_grid(table, n_windows=12, test_window_hours=6)
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
    kw = dict(n_windows=6, test_window_hours=6)
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
    grid = build_split_grid(table, n_windows=6, test_window_hours=6)

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
        compute_ceiling(table, feature_fields=["submit_time"], n_windows=1)


# --- power targets and list-valued features (#230) -----------------------------------


@pytest.mark.parametrize(
    "list_type", [pa.list_(pa.float32()), pa.list_(pa.float32(), 2)], ids=["list", "fixed"]
)
def test_identical_embeddings_share_a_signature(list_type: pa.DataType) -> None:
    emb = [[1.0, 0.0], [0.5, 0.5], [1.0, 0.0], None, [0.5, 0.5000001], None]
    # Split across chunks, with a sliced chunk, as Arrow hands them over.
    full = pa.array(emb, type=list_type)
    column = pa.chunked_array([full.slice(0, 2), full.slice(2, 4)])
    codes = signature_codes(pa.table({"embedding": column}), ["embedding"])

    assert codes[0] == codes[2]  # equal vectors
    assert codes[3] == codes[5] == 0  # nulls are one value
    assert len({codes[0], codes[1], codes[4], codes[3]}) == 4  # any differing element splits


def test_an_embedding_refines_the_signature() -> None:
    """Jobs the shared fields can't tell apart, but whose embeddings differ, split up."""
    rows = _jobs(4)
    for i, row in enumerate(rows):
        row["user"] = "u"
        row["embedding"] = [float(i % 2), 0.0]
    table = _table(rows)
    assert len(set(signature_codes(table, ["user"]))) == 1
    assert len(set(signature_codes(table, ["user", "embedding"]))) == 2


def test_ceiling_bounds_the_named_target_and_records_it() -> None:
    rows = _jobs(96)
    for i, row in enumerate(rows):
        row["avgpcon_per_node"] = None if i % 7 == 0 else float(90 + (i % 4))
    result = compute_ceiling(
        _table(rows),
        feature_fields=["partition", "user"],
        n_windows=4,
        test_window_hours=6,
        target_field="avgpcon_per_node",
        with_backoff=False,
    )
    assert result["target_field"] == "avgpcon_per_node"
    # Jobs without a reading are never scored, as in the benchmark.
    windowed = [
        r
        for r in rows
        if r["submit_time"] >= rows[-1]["submit_time"].replace(minute=0) - dt.timedelta(hours=18)
    ]
    assert result["scored_rows"] == sum(r["avgpcon_per_node"] is not None for r in windowed)
    assert 0 <= result["floor"]["mae"] < 4


def _power_parquet(tmp_path) -> str:
    import pyarrow.parquet as pq

    rows = _jobs(96)
    for i, row in enumerate(rows):
        row["avgpcon_per_node"] = float(90 + (i % 4))
        row["embedding"] = [float(i % 3), 1.0]
        row["freq_req"] = 2200.0
    path = tmp_path / "data.parquet"
    pq.write_table(_table(rows), path)
    return str(path)


def test_cli_ceiling_on_a_power_target_with_extra_features(tmp_path) -> None:
    import json

    from typer.testing import CliRunner

    from hpc_oda_commons.qst.cli import app

    out = tmp_path / "power.ceiling.json"
    args = ["datasets", "ceiling", _power_parquet(tmp_path), "--out", str(out)]
    args += ["--target", "avgpcon_per_node", "--n-windows", "4", "--test-window-hours", "6"]
    args += ["--skip-windows", "0", "--extra-feature", "embedding"]
    result = CliRunner().invoke(app, [*args, "--extra-feature", "freq_req"])

    assert result.exit_code == 0, result.output
    written = json.loads(out.read_text())
    assert written["target_field"] == "avgpcon_per_node"
    assert {"embedding", "freq_req", "partition", "user"} <= set(written["feature_fields"])


def test_cli_ceiling_refuses_the_target_as_a_feature(tmp_path) -> None:
    from typer.testing import CliRunner

    from hpc_oda_commons.qst.cli import app

    args = ["datasets", "ceiling", _power_parquet(tmp_path), "--target", "avgpcon_per_node"]
    result = CliRunner().invoke(app, [*args, "--extra-feature", "avgpcon_per_node"])
    assert result.exit_code == 1
    assert "cannot also be a feature" in result.output


def test_equal_embeddings_match_across_chunks_with_and_without_null_elements() -> None:
    """Arrow returns float64 for a chunk with a null element and float32 otherwise."""
    with_null = pa.array([[1.0, 0.0], [None, 2.0]], type=pa.list_(pa.float32()))
    without = pa.array([[1.0, 0.0]], type=pa.list_(pa.float32()))
    codes = signature_codes(
        pa.table({"embedding": pa.chunked_array([with_null, without])}), ["embedding"]
    )
    assert codes[0] == codes[2]
    assert codes[1] != codes[0]


def test_signature_codes_agree_on_a_subset_of_rows() -> None:
    """The feature-cost pass recodes a taken subset; it must group rows exactly the same."""
    emb = pa.chunked_array(
        [
            pa.array([[1.0, None], [1.0, 0.0]], type=pa.list_(pa.float32())),
            pa.array([[1.0, 0.0], [2.0, 0.0], [1.0, None]], type=pa.list_(pa.float32())),
        ]
    )
    table = pa.table({"embedding": emb})
    rows = np.array([0, 2, 3, 4])
    full = signature_codes(table, ["embedding"])[rows]
    taken = signature_codes(table.take(pa.array(rows)), ["embedding"])
    assert len(np.unique(full)) == len(np.unique(taken)) == len(np.unique(full * 100 + taken))


def test_feature_costs_are_never_negative() -> None:
    """Dropping a feature merges groups, so a floor without it can only be higher."""
    rows = _jobs(96)
    for i, row in enumerate(rows):
        row["avgpcon_per_node"] = float(90 + (i * 7) % 11)
        row["embedding"] = [float(i % 4), 0.0]
    result = compute_ceiling(
        _table(rows),
        feature_fields=["embedding", "partition", "user"],
        n_windows=4,
        test_window_hours=6,
        target_field="avgpcon_per_node",
        with_backoff=False,
    )
    assert all(c["cost"] >= 0 for c in result["feature_cost"])


# --- the walk-forward burn-in (#238) ---------------------------------------------------


def _gapped_jobs() -> list[dict]:
    """Two days of jobs every 30 minutes, with none submitted in one 6 h window near the end.

    The 6 h windows run back from the last submit, so with 8 windows the gap is window 2.
    """
    rows = _jobs(96)
    last = rows[-1]["submit_time"].replace(minute=0)
    gap_start = last - dt.timedelta(hours=6 * 5)
    return [
        r for r in rows if not gap_start <= r["submit_time"] < gap_start + dt.timedelta(hours=6)
    ]


def _windows_with_jobs(table: pa.Table, n_windows: int) -> list[np.ndarray]:
    grid = build_split_grid(table, n_windows=n_windows, test_window_hours=6)
    tests = [grid.test_indices(i) for i in range(n_windows)]
    return [t for t in tests if t.size]


def test_skipping_counts_only_windows_that_hold_jobs() -> None:
    """Walk-forward's burn-in skips the first windows every arm scored, and a window with no
    test jobs is never scored, so an empty window must not use up the burn-in."""
    table = _table(_gapped_jobs())
    kw = dict(feature_fields=["partition", "user"], n_windows=8, test_window_hours=6)
    with_jobs = _windows_with_jobs(table, 8)
    assert len(with_jobs) == 7  # guard: the gap left one window empty

    result = compute_ceiling(table, **kw, skip_windows=3, with_backoff=False)

    assert result["split"] == {
        "n_windows": 8,
        "test_window_hours": 6,
        "skip_windows": 3,
        "windows_with_jobs": 7,
        "scored_windows": 4,
    }
    assert result["scored_rows"] == sum(t.size for t in with_jobs[3:])


def test_causal_memorization_scores_the_same_rows_as_the_floor() -> None:
    table = _table(_gapped_jobs())
    result = compute_ceiling(
        table, feature_fields=["partition", "user"], n_windows=8, skip_windows=2
    )
    rows = {s["rows"] for s in result["causal_memorization"]["sweep"].values()}
    assert rows == {result["scored_rows"]}
    assert result["causal_memorization"]["backoff_at_best"]["rows"] == result["scored_rows"]


def test_skipping_every_window_with_jobs_is_an_error() -> None:
    table = _table(_gapped_jobs())
    with pytest.raises(CeilingError, match="nothing would be left to score"):
        compute_ceiling(table, feature_fields=["user"], n_windows=8, skip_windows=7)


def test_the_ceiling_records_no_training_lookback() -> None:
    """Nothing in it trains on a lookback: the floor and feature costs use the scored rows,
    and causal memorization sweeps its own (#238)."""
    result = compute_ceiling(_table(_jobs(96)), feature_fields=["user"], n_windows=4)
    assert "training_lookback_days" not in result["split"]


def test_the_schema_accepts_ceilings_with_and_without_the_old_lookback() -> None:
    from hpc_oda_commons.kernel.validate import validate_json

    result = compute_ceiling(_table(_jobs(96)), feature_fields=["user"], n_windows=4)
    validate_json(result, "oda.ceiling.v0.1.0")
    old = {
        **result,
        "split": {"n_windows": 4, "test_window_hours": 6, "training_lookback_days": 120},
    }
    validate_json(old, "oda.ceiling.v0.1.0")


def _card(tmp_path, test_days: int):
    import json

    path = tmp_path / "x.card.json"
    rule = {"train_days": 1, "test_days": test_days, "history_days": 1}
    path.write_text(json.dumps({"benchmark_window": {"rule": rule}}))
    return str(path)


def test_cli_ceiling_takes_its_windows_from_the_card(tmp_path) -> None:
    import json

    from typer.testing import CliRunner

    from hpc_oda_commons.qst.cli import app

    out = tmp_path / "runtime.ceiling.json"
    args = ["datasets", "ceiling", _power_parquet(tmp_path), "--out", str(out)]
    result = CliRunner().invoke(app, [*args, "--card", _card(tmp_path, 1), "--skip-windows", "1"])

    assert result.exit_code == 0, result.output
    split = json.loads(out.read_text())["split"]
    # One test day is four 6 h windows; the first is skipped.
    assert (split["n_windows"], split["skip_windows"], split["scored_windows"]) == (4, 1, 3)


def test_cli_ceiling_needs_a_card_or_a_window_count(tmp_path) -> None:
    from typer.testing import CliRunner

    from hpc_oda_commons.qst.cli import app

    result = CliRunner().invoke(app, ["datasets", "ceiling", _power_parquet(tmp_path)])
    assert result.exit_code == 1
    assert "--card" in result.output


def test_cli_ceiling_skips_the_burn_in_by_default(tmp_path) -> None:
    """20 windows, the walk-forward burn-in: four windows leave nothing to score."""
    from typer.testing import CliRunner

    from hpc_oda_commons.qst.cli import app

    args = ["datasets", "ceiling", _power_parquet(tmp_path), "--n-windows", "4"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1
    assert "nothing would be left to score" in result.output
