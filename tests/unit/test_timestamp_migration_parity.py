"""Parity gate for the native-timestamp migration (#23).

The rolling-split train/test row-index assignments are representation-independent:
they depend only on the instant each job submitted/ended, not on whether the
timestamp is an ISO-8601 string (v0.1) or an Arrow timestamp / datetime (v0.2).
This snapshot of the canonical synthetic dataset MUST stay identical across the
migration, because those assignments drive every rolling model's evaluation.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq

from hpc_oda_commons.datasets.synthetic import generate_tiny_runtime_dataset
from hpc_oda_commons.models.rolling_tabular.split import build_rolling_splits

# (train_row_count, test_row_count, test_row_indices) per window, captured on the
# pre-migration (ISO-string) dataset with the config below.
_EXPECTED: list[tuple[int, int, list[int]]] = [
    (0, 0, []),
    (0, 0, []),
    (0, 5, [0, 1, 2, 3, 4]),
    (5, 6, [5, 6, 7, 8, 9, 10]),
    (11, 6, [11, 12, 13, 14, 15, 16]),
    (17, 6, [17, 18, 19, 20, 21, 22]),
    (23, 6, [23, 24, 25, 26, 27, 28]),
    (29, 1, [29]),
]


def test_rolling_split_assignments_are_stable(tmp_path: Path) -> None:
    table_path, _ = generate_tiny_runtime_dataset(tmp_path / "ds")
    rows = pq.read_table(table_path).to_pylist()

    splits = build_rolling_splits(rows, n_windows=8, test_window_hours=6, training_lookback_days=2)
    got = [(s.train_row_count, s.test_row_count, list(s.test_row_indices)) for s in splits]
    assert got == _EXPECTED
