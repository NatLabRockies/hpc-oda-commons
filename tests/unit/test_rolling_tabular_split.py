from __future__ import annotations

import datetime as dt
import json

import pytest

from hpc_oda_commons.models.rolling_tabular.split import (
    DailyPreprocessingCache,
    build_rolling_splits,
    materialize_split_rows,
)


def _dt(_s: str):
    """Parse an ISO-8601 Z timestamp to a tz-aware UTC datetime (v0.2 fixtures)."""
    from datetime import datetime

    return datetime.fromisoformat(_s.replace("Z", "+00:00"))


def test_strict_train_test_time_semantics() -> None:
    rows = [
        {
            "job_id": 1,
            "submit_time": _dt("2026-01-01T22:00:00Z"),
            "end_time": _dt("2026-01-01T22:59:00Z"),
        },
        {
            "job_id": 2,
            "submit_time": _dt("2026-01-01T22:59:00Z"),
            "end_time": _dt("2026-01-01T23:00:00Z"),
        },
        {
            "job_id": 3,
            "submit_time": _dt("2026-01-01T23:00:00Z"),
            "end_time": _dt("2026-01-01T23:30:00Z"),
        },
    ]
    splits = build_rolling_splits(rows, n_windows=2, test_window_hours=1)
    assert [split.split_time_iso for split in splits] == [
        "2026-01-01T22:00:00Z",
        "2026-01-01T23:00:00Z",
    ]

    split_22, split_23 = splits
    assert split_22.train_row_indices == ()
    assert split_22.test_row_indices == (0, 1)

    # end_time == split_time is excluded from training by strict '<' rule.
    assert split_23.train_row_indices == (0,)
    # submit_time == split_time is included in testing.
    assert split_23.test_row_indices == (2,)

    train_rows, test_rows = materialize_split_rows(rows, split_23)
    assert [row["job_id"] for row in train_rows] == [1]
    assert [row["job_id"] for row in test_rows] == [3]


def test_daily_refresh_flags_fire_once_per_day() -> None:
    rows = [
        {
            "submit_time": _dt("2026-01-01T22:05:00Z"),
            "end_time": _dt("2026-01-01T22:45:00Z"),
        },
        {
            "submit_time": _dt("2026-01-01T23:15:00Z"),
            "end_time": _dt("2026-01-01T23:30:00Z"),
        },
        {
            "submit_time": _dt("2026-01-02T00:10:00Z"),
            "end_time": _dt("2026-01-02T00:40:00Z"),
        },
        {
            "submit_time": _dt("2026-01-02T01:05:00Z"),
            "end_time": _dt("2026-01-02T01:20:00Z"),
        },
    ]
    splits = build_rolling_splits(rows, n_windows=4, test_window_hours=1)
    assert [split.split_time_iso for split in splits] == [
        "2026-01-01T22:00:00Z",
        "2026-01-01T23:00:00Z",
        "2026-01-02T00:00:00Z",
        "2026-01-02T01:00:00Z",
    ]
    assert [split.refresh_preprocessing for split in splits] == [True, False, True, False]
    assert [split.day_key for split in splits] == [
        "2026-01-01",
        "2026-01-01",
        "2026-01-02",
        "2026-01-02",
    ]


def test_training_lookback_days_limits_training_rows() -> None:
    rows = [
        {
            "job_id": 1,
            "submit_time": _dt("2025-10-15T10:00:00Z"),
            "end_time": _dt("2025-10-15T11:00:00Z"),
        },
        {
            "job_id": 2,
            "submit_time": _dt("2025-12-31T22:05:00Z"),
            "end_time": _dt("2025-12-31T22:30:00Z"),
        },
        {
            "job_id": 3,
            "submit_time": _dt("2026-01-01T00:05:00Z"),
            "end_time": _dt("2026-01-01T00:10:00Z"),
        },
    ]

    default_window = build_rolling_splits(rows, n_windows=1, test_window_hours=1)[0]
    short_window = build_rolling_splits(
        rows,
        n_windows=1,
        training_lookback_days=1,
    )[0]

    assert default_window.train_row_indices == (0, 1)
    assert short_window.train_row_indices == (1,)
    assert short_window.test_row_indices == (2,)


def test_daily_preprocessing_cache_recomputes_once_per_day() -> None:
    cache = DailyPreprocessingCache()
    calls: list[str] = []

    def _factory(day: str) -> dict[str, str]:
        calls.append(day)
        return {"day": day, "token": f"fit-{len(calls)}"}

    refreshed: list[bool] = []
    days = ["2026-01-01", "2026-01-01", "2026-01-02", "2026-01-02"]
    for day in days:
        payload, was_refreshed = cache.get_or_create(day, lambda day=day: _factory(day))
        refreshed.append(was_refreshed)
        assert payload["day"] == day

    assert refreshed == [True, False, True, False]
    assert calls == ["2026-01-01", "2026-01-02"]
    assert len(cache) == 2
    assert cache.keys() == ("2026-01-01", "2026-01-02")


def test_lookback_days_must_be_positive() -> None:
    rows = [{"submit_time": _dt("2026-01-01T00:00:00Z"), "end_time": _dt("2026-01-01T00:10:00Z")}]
    with pytest.raises(ValueError, match="training_lookback_days must be positive"):
        build_rolling_splits(rows, test_window_hours=1, training_lookback_days=0)


def test_build_rolling_splits_verbose_prints_summary(capsys: pytest.CaptureFixture[str]) -> None:
    rows = [
        {
            "submit_time": _dt("2026-01-01T22:05:00Z"),
            "end_time": _dt("2026-01-01T22:45:00Z"),
        },
        {
            "submit_time": _dt("2026-01-01T23:15:00Z"),
            "end_time": _dt("2026-01-01T23:30:00Z"),
        },
    ]
    splits = build_rolling_splits(rows, n_windows=2, test_window_hours=1, verbose=True)
    assert len(splits) == 2
    captured = capsys.readouterr()
    assert "[split][verbose] building rolling splits" in captured.out
    assert "[split][verbose] split window" in captured.out
    assert "[split][verbose] built splits" in captured.out


def test_rolling_splits_anchor_to_latest_submit_not_late_end_time() -> None:
    """Long-running jobs can end after the last submission; windows must follow submits."""
    rows = [
        {
            "job_id": 1,
            "submit_time": _dt("2024-04-28T10:00:00Z"),
            "end_time": _dt("2024-04-28T12:00:00Z"),
        },
        {
            "job_id": 2,
            "submit_time": _dt("2024-04-30T14:30:00Z"),
            "end_time": _dt("2024-05-13T17:00:00Z"),
        },
    ]
    splits = build_rolling_splits(rows, n_windows=2, test_window_hours=6)

    assert splits[-1].split_time_iso == "2024-04-30T14:00:00Z"
    assert splits[-1].test_row_count >= 1
    assert any(split.test_row_count > 0 for split in splits)


# --- serialized payload size (#167) -------------------------------------------------


def _rows_ending_hourly(n: int) -> list[dict]:
    """n rows, one per hour, so a lookback window covers most of them."""
    start = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    return [
        {
            "submit_time": start + dt.timedelta(hours=i),
            "end_time": start + dt.timedelta(hours=i, minutes=30),
        }
        for i in range(n)
    ]


def test_serialized_window_carries_counts_not_index_lists() -> None:
    """Indices are the expansion of a deterministic function of recorded inputs (#167)."""
    splits = build_rolling_splits(
        _rows_ending_hourly(50), n_windows=3, test_window_hours=1, training_lookback_days=120
    )

    payload = splits[-1].to_dict()

    assert "train_row_indices" not in payload
    assert "test_row_indices" not in payload
    assert payload["train_row_count"] == len(splits[-1].train_row_indices)
    assert payload["test_row_count"] == len(splits[-1].test_row_indices)


def test_serialized_window_size_does_not_grow_with_the_training_set() -> None:
    """The regression that produced a 7.3 GB metrics.json per cell (#167).

    Serializing the indices made each window's payload scale with the lookback, so the
    file grew with the dataset while carrying the same handful of numbers.
    """
    small = build_rolling_splits(
        _rows_ending_hourly(50), n_windows=1, test_window_hours=1, training_lookback_days=120
    )
    large = build_rolling_splits(
        _rows_ending_hourly(5_000), n_windows=1, test_window_hours=1, training_lookback_days=120
    )

    # guard: the two really do differ in training-set size, or this proves nothing
    assert large[-1].train_row_count > 50 * small[-1].train_row_count

    small_len = len(json.dumps(small[-1].to_dict()))
    large_len = len(json.dumps(large[-1].to_dict()))

    # A 58x bigger training set may only widen the digits of train_row_count. Before the
    # fix this difference was the training set itself, one integer per row.
    assert large_len - small_len < 32, (small_len, large_len)
