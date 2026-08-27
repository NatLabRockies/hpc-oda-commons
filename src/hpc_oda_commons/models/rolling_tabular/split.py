from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, TypeVar

import numpy as np
from tqdm import tqdm

T = TypeVar("T")


def _to_utc(value: Any) -> datetime | None:
    # v0.2 canonical job tables store timestamps as Arrow timestamp(tz=UTC), so
    # rows materialize as tz-aware datetimes. Non-datetimes (incl. legacy ISO
    # strings) are not supported and are treated as missing.
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _epoch_or_nan(value: Any) -> float:
    """UTC epoch seconds, or NaN when the value is missing or not a datetime."""
    parsed = _to_utc(value)
    return float("nan") if parsed is None else parsed.timestamp()


def _to_iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _floor_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


@dataclass(frozen=True)
class RollingSplit:
    """One rolling window. Row memberships are derived on access, not stored.

    ``train_row_indices`` and ``test_row_indices`` used to be tuples of Python ints built
    by scanning every row once per window. At the benchmark's scale -- 120 windows over a
    multi-million-row slice, with a 120-day lookback that holds most of it -- that is
    hundreds of millions of int objects at ~36 bytes each, and O(n_windows x n_rows)
    comparisons in Python (#176). It is the in-memory twin of the metrics bloat in #167.

    Membership is a predicate on two timestamps, so it is recomputed from shared epoch
    arrays instead: the windows hold bounds, and each access returns a fresh int64 array in
    ascending row order. Only the window being processed is ever materialised.
    """

    split_time_iso: str
    split_end_time_iso: str
    split_epoch: int
    day_key: str
    refresh_preprocessing: bool
    train_row_count: int
    test_row_count: int
    # Shared across every window of a run; never copied.
    _submit_epochs: np.ndarray = field(repr=False, compare=False)
    _end_epochs: np.ndarray = field(repr=False, compare=False)
    _train_start_epoch: float = field(repr=False)
    _split_epoch_exact: float = field(repr=False)
    _split_end_epoch: float = field(repr=False)

    @property
    def train_row_indices(self) -> np.ndarray:
        """Rows that FINISHED within the lookback, ascending by row index.

        Ascending row order is not incidental: ``docs/known-issues.md`` records that
        reordering training rows can flip a TF-IDF neighbour tie, so the sequence is part
        of the contract, not just the set.
        """
        ends = self._end_epochs
        return np.flatnonzero((ends >= self._train_start_epoch) & (ends < self._split_epoch_exact))

    @property
    def test_row_indices(self) -> np.ndarray:
        """Rows SUBMITTED within the window, ascending by row index."""
        sub = self._submit_epochs
        return np.flatnonzero((sub >= self._split_epoch_exact) & (sub < self._split_end_epoch))

    def to_dict(self) -> dict[str, Any]:
        """Serializable window description -- counts, not the index lists.

        The indices stay on the dataclass because the models slice rows with them, but
        they are deliberately **not** persisted. They are the expansion of a deterministic
        function of values the bundle already records (``n_windows``,
        ``test_window_hours``, ``training_lookback_days``, and the table hash), so writing
        them stores no information and costs the whole training set per window: a 120-window
        run over a multi-million-row slice produced a 7.3 GB ``metrics.json`` per cell, and
        121 GB across one fleet run (#167). That made ``collect`` a many-hour transfer and
        ``aggregate`` -- which json.loads each bundle to read one MAE -- memory-hostile.
        """
        return {
            "split_time": self.split_time_iso,
            "split_end_time": self.split_end_time_iso,
            "split_epoch": self.split_epoch,
            "day_key": self.day_key,
            "refresh_preprocessing": self.refresh_preprocessing,
            "train_row_count": self.train_row_count,
            "test_row_count": self.test_row_count,
        }


def build_rolling_splits(
    rows: list[dict[str, Any]],
    *,
    n_windows: int = 1000,
    test_window_hours: int = 6,
    training_lookback_days: int = 100,
    submit_time_field: str = "submit_time",
    end_time_field: str = "end_time",
    verbose: bool = False,
) -> list[RollingSplit]:
    """
    Build rolling split windows with strict train/test semantics:
    - train: split_time - lookback_days <= end_time < split_time
    - test: split_time <= submit_time < split_time + test_window_hours
    """
    if n_windows <= 0:
        raise ValueError("n_windows must be positive")
    if test_window_hours <= 0:
        raise ValueError("test_window_hours must be positive")
    if training_lookback_days <= 0:
        raise ValueError("training_lookback_days must be positive")

    if verbose:
        print(
            "[split][verbose] building rolling splits "
            f"rows={len(rows)} "
            f"n_windows={n_windows} "
            f"training_lookback_days={training_lookback_days}"
        )

    # Epoch seconds in row order, NaN where absent. float64 holds microsecond precision
    # at present-day timestamps (~1e9 s), so this is not a lossy shortcut.
    submit_epochs = np.fromiter(
        (_epoch_or_nan(row.get(submit_time_field)) for row in rows),
        dtype=np.float64,
        count=len(rows),
    )
    end_epochs = np.fromiter(
        (_epoch_or_nan(row.get(end_time_field)) for row in rows),
        dtype=np.float64,
        count=len(rows),
    )

    if not np.isfinite(submit_epochs).any():
        raise ValueError("No valid submit timestamps found; cannot build rolling splits.")
    max_submit_ts = datetime.fromtimestamp(float(np.nanmax(submit_epochs)), tz=timezone.utc)

    latest_hour = _floor_hour(max_submit_ts)
    start_hour = latest_hour - timedelta(hours=(n_windows - 1) * test_window_hours)
    split_hours = [start_hour + timedelta(hours=i * test_window_hours) for i in range(n_windows)]
    if verbose:
        print(
            "[split][verbose] split window "
            f"start={_to_iso_z(start_hour)} end={_to_iso_z(latest_hour)} "
            f"latest_hour={_to_iso_z(latest_hour)}"
        )

    splits: list[RollingSplit] = []
    previous_day: str | None = None
    for split_time in tqdm(split_hours, total=len(split_hours)):
        split_end = split_time + timedelta(hours=test_window_hours)
        training_window_start = split_time - timedelta(days=training_lookback_days)
        day_key = split_time.date().isoformat()
        refresh = previous_day is None or day_key != previous_day
        previous_day = day_key

        train_start_epoch = training_window_start.timestamp()
        split_epoch_exact = split_time.timestamp()
        split_end_epoch = split_end.timestamp()
        n_train = int(
            np.count_nonzero((end_epochs >= train_start_epoch) & (end_epochs < split_epoch_exact))
        )
        n_test = int(
            np.count_nonzero(
                (submit_epochs >= split_epoch_exact) & (submit_epochs < split_end_epoch)
            )
        )

        splits.append(
            RollingSplit(
                split_time_iso=_to_iso_z(split_time),
                split_end_time_iso=_to_iso_z(split_end),
                split_epoch=int(split_time.timestamp()),
                day_key=day_key,
                refresh_preprocessing=refresh,
                train_row_count=n_train,
                test_row_count=n_test,
                _submit_epochs=submit_epochs,
                _end_epochs=end_epochs,
                _train_start_epoch=train_start_epoch,
                _split_epoch_exact=split_epoch_exact,
                _split_end_epoch=split_end_epoch,
            )
        )

    if verbose:
        nonempty_train = sum(1 for split in splits if split.train_row_count > 0)
        nonempty_test = sum(1 for split in splits if split.test_row_count > 0)
        refresh_points = sum(1 for split in splits if split.refresh_preprocessing)
        print(
            "[split][verbose] built splits "
            f"total={len(splits)} "
            f"nonempty_train={nonempty_train} "
            f"nonempty_test={nonempty_test} "
            f"refresh_points={refresh_points}"
        )

    return splits


def materialize_split_rows(
    rows: list[dict[str, Any]],
    split: RollingSplit,
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

    def get(self, day_key: str) -> Any:
        """Return a previously-built artifact. Read-only, so safe to call from
        worker threads once every day has been built."""
        return self._store[day_key]

    def clear(self) -> None:
        self._store.clear()

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._store.keys()))

    def __len__(self) -> int:
        return len(self._store)
