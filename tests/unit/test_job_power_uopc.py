from __future__ import annotations

import math

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hpc_oda_commons.models.job_power_uopc.model import JobPowerUopcModel


def _write_uopc_dataset(path) -> None:
    rows = []
    for idx in range(30):
        user = "alice" if idx < 20 else "bob"
        rows.append(
            {
                "usr": user,
                "jnam": f"job_{idx % 3}",
                "cnumr": 64 + (idx % 4) * 8,
                "nnumr": 1 + (idx % 2),
                "edt": f"2024-04-01T{idx % 24:02d}:00:00+09:00",
                "maxpcon": 1000.0 + idx * 10.0 + (idx % 3) * 5.0,
            }
        )
    pq.write_table(pa.Table.from_pylist(rows), path)


def test_uopc_fixed_predicts_with_user_history(tmp_path) -> None:
    table_path = tmp_path / "uopc.parquet"
    _write_uopc_dataset(table_path)
    rows = pq.read_table(table_path).to_pylist()

    result = JobPowerUopcModel().evaluate_fixed(
        rows,
        split={"train_fraction": 0.7, "seed": 1},
        metric_defs=[
            {"name": "mae", "target": "maxpcon"},
            {"name": "rmse", "target": "maxpcon"},
        ],
    )

    assert math.isfinite(result["mae"]) and result["mae"] >= 0.0
    assert math.isfinite(result["rmse"]) and result["rmse"] >= 0.0
    assert result["summary"]["rows_scored"] > 0
    assert result["summary"]["theta"] == 50
    assert result["summary"]["k"] == 5


def test_uopc_requires_finite_target() -> None:
    rows = [{"usr": "alice", "jnam": "x", "cnumr": 1, "nnumr": 1, "edt": "2024-04-01T00:00:00+09:00"}]
    with pytest.raises(ValueError, match="No rows with a finite target"):
        JobPowerUopcModel().evaluate_fixed(rows, split={"train_fraction": 0.8, "seed": 1})
