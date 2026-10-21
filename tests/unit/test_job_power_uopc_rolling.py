"""UoPC on the shared rolling protocol (#204)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from hpc_oda_commons.benchmark import runner
from hpc_oda_commons.models.uopc.rolling import (
    UopcRollingConfig,
    UopcRollingModel,
)

TARGET = "avgpcon_per_node"
METRICS = [{"name": "mae", "target": TARGET}, {"name": "rmse", "target": TARGET}]
BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _job(i: int, user: str, hour: float, power: float, cores: float = 48.0) -> dict:
    submit = BASE + timedelta(hours=hour)
    return {
        "job_id": i,
        "user": user,
        "submit_time": submit,
        "end_time": submit + timedelta(minutes=30),
        "num_cores_req": cores,
        "num_nodes_req": 1.0,
        "freq_req": 2200.0,
        "embedding": [cores / 48.0, 1.0],
        TARGET: power,
    }


def _rows() -> list[dict]:
    """Two regular users with ten jobs of history, then a test hour with a newcomer."""
    rows = []
    for i in range(10):
        rows.append(_job(len(rows), "alice", i, 100.0))
        rows.append(_job(len(rows), "bob", i + 0.5, 300.0))
    # The test window: the last hour. `carol` has no history at all.
    rows.append(_job(len(rows), "alice", 20.0, 100.0))
    rows.append(_job(len(rows), "bob", 20.2, 300.0))
    rows.append(_job(len(rows), "carol", 20.4, 999.0))
    return rows


def _model(**overrides) -> UopcRollingModel:
    cfg = {"n_windows": 1, "test_window_hours": 1, "training_lookback_days": 2, "theta": 5, "k": 3}
    return UopcRollingModel(UopcRollingConfig(**{**cfg, **overrides}))


def test_each_user_is_predicted_from_their_own_history() -> None:
    result = _model().evaluate(_rows(), metric_defs=METRICS, capture_artifacts=True)

    pairs = sorted(zip(result["_y_true"], result["_y_pred"], strict=True))
    # alice and bob are predicted exactly from their own jobs; carol falls back.
    assert pairs[0] == (100.0, 100.0)
    assert pairs[1] == (300.0, 300.0)
    assert result["summary"]["rows_scored"] == 3


def test_a_user_without_k_training_jobs_gets_the_window_mean() -> None:
    """Every model must be scored on the same rows, so a cold-start job is predicted, not
    dropped -- with the rolling baseline's prediction -- and counted."""
    result = _model().evaluate(_rows(), metric_defs=METRICS, capture_artifacts=True)

    carol = [p for t, p in zip(result["_y_true"], result["_y_pred"], strict=True) if t == 999.0]
    assert carol == [200.0]  # the mean of alice's 100 W and bob's 300 W training jobs
    assert result["summary"]["rows_fallback"] == 1


def test_scores_exactly_the_rows_and_windows_the_baseline_does() -> None:
    split = {
        "method": "rolling",
        "n_windows": 1,
        "test_window_hours": 1,
        "training_lookback_days": 2,
    }
    _, uopc, _ = runner.run_rolling_uopc(_rows(), split={**split, "k": 3}, metric_defs=METRICS)
    _, base, _ = runner.run_rolling_baseline(_rows(), split=split, metric_defs=METRICS)

    for key in ("windows_total", "windows_scored", "rows_scored"):
        assert uopc["summary"][key] == base["summary"][key]


def test_context_is_only_the_newest_theta_training_jobs() -> None:
    """With theta=3, alice's three newest jobs (all 500 W) outvote her seven older ones."""
    rows = _rows()
    for row in rows:
        if row["user"] == "alice" and 7 <= row["submit_time"].hour < 10:
            row[TARGET] = 500.0
    result = _model(theta=3).evaluate(rows, metric_defs=METRICS, capture_artifacts=True)

    alice = [p for t, p in zip(result["_y_true"], result["_y_pred"], strict=True) if t == 100.0]
    assert alice == [500.0]


def test_test_jobs_never_shape_the_feature_scaling() -> None:
    """Scaling is fitted on the window's training rows only: no look-ahead, unlike the
    paper protocol. Changing a test job's features changes no other job's prediction."""
    rows = _rows()
    before = _model().evaluate(rows, metric_defs=METRICS, capture_artifacts=True)
    rows[-3]["num_cores_req"] = 4800.0  # alice's test job
    after = _model().evaluate(rows, metric_defs=METRICS, capture_artifacts=True)

    others = slice(1, None)  # results are grouped by user; alice sorts first
    assert before["_y_pred"][others] == after["_y_pred"][others]


def test_rows_without_an_embedding_are_an_error() -> None:
    rows = _rows()
    rows[0]["embedding"] = None
    with pytest.raises(ValueError, match="embedding"):
        _model().evaluate(rows, metric_defs=METRICS)


def test_the_target_cannot_be_a_feature() -> None:
    with pytest.raises(ValueError, match="prediction target"):
        UopcRollingModel(UopcRollingConfig(target_field="num_cores_req"))
