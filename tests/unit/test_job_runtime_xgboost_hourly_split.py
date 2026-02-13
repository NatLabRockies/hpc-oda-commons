from __future__ import annotations

from hpc_oda_commons.models.job_runtime_xgboost.split import (
    DailyPreprocessingCache,
    build_hourly_rolling_splits,
    materialize_split_rows,
)


def test_strict_train_test_time_semantics() -> None:
    rows = [
        {
            "job_id": 1,
            "submit_time": "2026-01-01T22:00:00Z",
            "end_time": "2026-01-01T22:59:00Z",
        },
        {
            "job_id": 2,
            "submit_time": "2026-01-01T22:59:00Z",
            "end_time": "2026-01-01T23:00:00Z",
        },
        {
            "job_id": 3,
            "submit_time": "2026-01-01T23:00:00Z",
            "end_time": "2026-01-01T23:30:00Z",
        },
    ]
    splits = build_hourly_rolling_splits(rows, n_recent_hours=2)
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
            "submit_time": "2026-01-01T22:05:00Z",
            "end_time": "2026-01-01T22:45:00Z",
        },
        {
            "submit_time": "2026-01-01T23:15:00Z",
            "end_time": "2026-01-01T23:30:00Z",
        },
        {
            "submit_time": "2026-01-02T00:10:00Z",
            "end_time": "2026-01-02T00:40:00Z",
        },
        {
            "submit_time": "2026-01-02T01:05:00Z",
            "end_time": "2026-01-02T01:20:00Z",
        },
    ]
    splits = build_hourly_rolling_splits(rows, n_recent_hours=4)
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
