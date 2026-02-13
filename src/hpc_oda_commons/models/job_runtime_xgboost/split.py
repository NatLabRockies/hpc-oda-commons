from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def _to_utc(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    text = str(value)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _floor_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


@dataclass(frozen=True)
class HourlyRollingSplit:
    split_time_iso: str
    split_end_time_iso: str
    split_epoch: int
    day_key: str
    refresh_preprocessing: bool
    train_row_indices: tuple[int, ...]
    test_row_indices: tuple[int, ...]
    train_row_count: int
    test_row_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "split_time": self.split_time_iso,
            "split_end_time": self.split_end_time_iso,
            "split_epoch": self.split_epoch,
            "day_key": self.day_key,
            "refresh_preprocessing": self.refresh_preprocessing,
            "train_row_indices": list(self.train_row_indices),
            "test_row_indices": list(self.test_row_indices),
            "train_row_count": self.train_row_count,
            "test_row_count": self.test_row_count,
        }


def build_hourly_rolling_splits(
    rows: list[dict[str, Any]],
    *,
    n_recent_hours: int = 1000,
    training_lookback_days: int = 100,
    submit_time_field: str = "submit_time",
    end_time_field: str = "end_time",
) -> list[HourlyRollingSplit]:
    """
    Build rolling-hour split windows with strict train/test semantics:
    - train: split_time - lookback_days <= end_time < split_time
    - test: split_time <= submit_time < split_time + 1 hour
    """
    if n_recent_hours <= 0:
        raise ValueError("n_recent_hours must be positive")
    if training_lookback_days <= 0:
        raise ValueError("training_lookback_days must be positive")

    parsed: list[tuple[int, datetime | None, datetime | None]] = []
    max_ts: datetime | None = None
    for idx, row in enumerate(rows):
        submit_ts = _to_utc(row.get(submit_time_field))
        end_ts = _to_utc(row.get(end_time_field))
        parsed.append((idx, submit_ts, end_ts))

        for ts in (submit_ts, end_ts):
            if ts is None:
                continue
            if max_ts is None or ts > max_ts:
                max_ts = ts

    if max_ts is None:
        raise ValueError("No valid submit/end timestamps found; cannot build rolling-hour splits.")

    latest_hour = _floor_hour(max_ts)
    start_hour = latest_hour - timedelta(hours=n_recent_hours - 1)
    split_hours = [start_hour + timedelta(hours=i) for i in range(n_recent_hours)]

    splits: list[HourlyRollingSplit] = []
    previous_day: str | None = None
    for split_time in split_hours:
        split_end = split_time + timedelta(hours=1)
        training_window_start = split_time - timedelta(days=training_lookback_days)
        day_key = split_time.date().isoformat()
        refresh = previous_day is None or day_key != previous_day
        previous_day = day_key

        train_indices = tuple(
            idx
            for idx, _submit_ts, end_ts in parsed
            if end_ts is not None and training_window_start <= end_ts < split_time
        )
        test_indices = tuple(
            idx
            for idx, submit_ts, _end_ts in parsed
            if submit_ts is not None and split_time <= submit_ts < split_end
        )

        splits.append(
            HourlyRollingSplit(
                split_time_iso=_to_iso_z(split_time),
                split_end_time_iso=_to_iso_z(split_end),
                split_epoch=int(split_time.timestamp()),
                day_key=day_key,
                refresh_preprocessing=refresh,
                train_row_indices=train_indices,
                test_row_indices=test_indices,
                train_row_count=len(train_indices),
                test_row_count=len(test_indices),
            )
        )

    return splits


def materialize_split_rows(
    rows: list[dict[str, Any]],
    split: HourlyRollingSplit,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train_rows = [rows[idx] for idx in split.train_row_indices]
    test_rows = [rows[idx] for idx in split.test_row_indices]
    return train_rows, test_rows


class DailyPreprocessingCache:
    """
    Day-keyed cache for preprocessing artifacts.
    Intended usage: compute OHE/SVD once per day_key.
    """

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def get_or_create(self, day_key: str, factory: Callable[[], T]) -> tuple[T, bool]:
        if day_key in self._store:
            return self._store[day_key], False
        value = factory()
        self._store[day_key] = value
        return value, True

    def clear(self) -> None:
        self._store.clear()

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._store.keys()))

    def __len__(self) -> int:
        return len(self._store)
