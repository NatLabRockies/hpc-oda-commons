"""Unit tests for the MoE XGBoost model."""

from __future__ import annotations

import math

import pytest

from hpc_oda_commons.models.job_runtime_moe_xgboost.model import (
    MoEXGBoostConfig,
    MoEXGBoostModel,
)

pytest.importorskip("xgboost")
pytest.importorskip("sklearn")


def _dt(_s: str):
    """Parse an ISO-8601 Z timestamp to a tz-aware UTC datetime."""
    from datetime import datetime

    return datetime.fromisoformat(_s.replace("Z", "+00:00"))


def _make_rows():
    """Create minimal test rows with enough diversity for MoE binning.

    Includes two users with different wallclock clusters to test routing.
    """
    from datetime import datetime, timedelta, timezone

    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    base_rows = []
    # User A — many short jobs (will be power user with enough rows)
    for i in range(60):
        submit = base_time + timedelta(minutes=i * 10)
        end = submit + timedelta(seconds=60 + i * 5)
        base_rows.append(
            {
                "job_id": f"a_{i}",
                "user": "user_a",
                "submit_time": submit,
                "end_time": end,
                "runtime_seconds": 60.0 + i * 5,
                "requested_seconds": 3600.0,  # <=2h bin
                "partition": "compute",
            }
        )
    # User B — fewer longer jobs
    for i in range(40):
        submit = base_time + timedelta(minutes=i * 15)
        end = submit + timedelta(seconds=1800 + i * 100)
        base_rows.append(
            {
                "job_id": f"b_{i}",
                "user": "user_b",
                "submit_time": submit,
                "end_time": end,
                "runtime_seconds": 1800.0 + i * 100,
                "requested_seconds": 18000.0,  # 4-24h bin
                "partition": "gpu",
            }
        )
    return base_rows


def test_moe_xgboost_evaluate_returns_valid_metrics() -> None:
    """Test that evaluate() returns finite MAE and RMSE."""
    rows = _make_rows()
    config = MoEXGBoostConfig(
        n_windows=2,
        test_window_hours=1,
        training_lookback_days=1,
        max_svd_components=8,
        target_max_one_hot_width=64,
        n_estimators=10,
        max_depth=3,
        min_bin_rows=10,
        power_user_percentile=0.50,  # lower threshold so test data creates bins
    )
    model = MoEXGBoostModel(config)
    payload = model.evaluate(rows)

    assert math.isfinite(payload["mae"]) and payload["mae"] >= 0.0
    assert math.isfinite(payload["rmse"]) and payload["rmse"] >= 0.0
    assert payload["summary"]["rows_scored"] >= 1


def test_moe_xgboost_config_defaults() -> None:
    """Test that config defaults are set correctly."""
    config = MoEXGBoostConfig()
    assert config.time_decay_rate == 0.05
    assert config.power_user_percentile == 0.99
    assert config.min_bin_rows == 100
    assert config.n_estimators == 200
    assert config.max_depth == 12
    assert config.estimator_n_jobs == 1


def test_moe_xgboost_bin_routing() -> None:
    """Test that the model creates bins based on user and wallclock."""
    rows = _make_rows()
    config = MoEXGBoostConfig(
        n_windows=2,
        test_window_hours=1,
        training_lookback_days=1,
        max_svd_components=8,
        target_max_one_hot_width=64,
        n_estimators=10,
        max_depth=3,
        min_bin_rows=10,
        power_user_percentile=0.50,
    )
    model = MoEXGBoostModel(config)

    bins, power_users = model._build_bins(rows)

    # Should have at least 2 bins (different users/wallclock combinations)
    assert len(bins) >= 2
    # Power users set should be non-empty with low percentile
    assert len(power_users) >= 1


def test_moe_xgboost_empty_rows_raises() -> None:
    """Test that evaluate() raises on empty input."""
    model = MoEXGBoostModel()
    with pytest.raises(ValueError, match="non-empty"):
        model.evaluate([])


def test_moe_xgboost_summary_has_bin_details() -> None:
    """Test that the summary includes per-bin breakdown."""
    rows = _make_rows()
    config = MoEXGBoostConfig(
        n_windows=2,
        test_window_hours=1,
        training_lookback_days=1,
        max_svd_components=8,
        target_max_one_hot_width=64,
        n_estimators=10,
        max_depth=3,
        min_bin_rows=10,
        power_user_percentile=0.50,
    )
    model = MoEXGBoostModel(config)
    payload = model.evaluate(rows)

    assert "bin_details" in payload["summary"]
    assert len(payload["summary"]["bin_details"]) >= 1
    for detail in payload["summary"]["bin_details"]:
        assert "bin" in detail
        assert "rows" in detail
        assert "scored" in detail
