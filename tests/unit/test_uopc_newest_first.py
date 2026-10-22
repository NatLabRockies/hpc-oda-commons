"""The fixed UoPC context is the user's newest theta jobs, found without a full sort (#259)."""

from __future__ import annotations

import random

from hpc_oda_commons.models.uopc.model import _newest_first


def _by_full_sort(rows: list[dict], keys: list[float], theta: int) -> list[dict]:
    """What the loop did before: a stable descending sort of the whole history."""
    order = sorted(range(len(rows)), key=lambda i: keys[i], reverse=True)
    return [rows[i] for i in order[:theta]]


def test_matches_a_full_stable_sort_with_many_ties() -> None:
    rng = random.Random(7)
    for _ in range(500):
        n = rng.randint(0, 120)
        # Few distinct end times, so ties straddle the theta boundary often.
        keys = sorted(float(rng.randint(0, 8)) for _ in range(n))
        rows = [{"i": i} for i in range(n)]
        theta = rng.randint(1, 60)
        assert _newest_first(rows, keys, theta) == _by_full_sort(rows, keys, theta)


def test_short_history_returns_all_of_it_newest_first() -> None:
    rows = [{"i": i} for i in range(3)]
    assert _newest_first(rows, [1.0, 2.0, 3.0], 50) == [rows[2], rows[1], rows[0]]
    assert _newest_first([], [], 50) == []
