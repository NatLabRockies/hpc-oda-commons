from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from hpc_oda_commons.models.job_runtime_xgboost.model import (
    JobRuntimeXGBoostConfig,
    JobRuntimeXGBoostModel,
)


def test_config_defaults() -> None:
    config = JobRuntimeXGBoostConfig()
    assert config.n_windows == 1000
    assert config.test_window_hours == 6
    assert config.training_lookback_days == 100
    assert config.submit_time_field == "submit_time"
    assert config.end_time_field == "end_time"
    assert config.explained_variance_target == 0.95
    assert config.infrequent_category_fraction == 0.001
    assert config.min_frequency_floor == 2
    assert config.target_max_one_hot_width == 2048
    assert config.max_svd_components == 256
    assert config.random_state == 42
    assert config.n_estimators == 100


def test_dependency_check_reports_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    model = JobRuntimeXGBoostModel()

    def fake_find_spec(name: str) -> object | None:
        if name in {"xgboost", "sklearn"}:
            return None
        return SimpleNamespace()

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    with pytest.raises(RuntimeError, match="xgboost, sklearn"):
        model._check_dependencies()


def test_analyze_preprocessing_writes_diagnostics(tmp_path: Path) -> None:
    rows = [
        {"user": "alice", "partition": "debug", "state": "COMPLETED"},
        {"user": "bob", "partition": "debug", "state": "FAILED"},
        {"user": "charlie", "partition": "compute", "state": "COMPLETED"},
        {"user": None, "partition": "compute", "state": "TIMEOUT"},
    ]
    model = JobRuntimeXGBoostModel()
    out_path = tmp_path / "preprocessing.json"

    payload = model.analyze_preprocessing(rows, diagnostics_path=out_path)

    assert out_path.exists()
    assert payload["analysis_version"] == "rolling_tabular.preprocessing.v0.1.0"
    assert payload["row_count"] == 4
    assert payload["one_hot_analysis"]["encoded_feature_count"] > 0


def test_build_split_plan() -> None:
    rows = [
        {
            "submit_time": "2026-01-01T22:05:00Z",
            "end_time": "2026-01-01T22:55:00Z",
        },
        {
            "submit_time": "2026-01-01T23:15:00Z",
            "end_time": "2026-01-01T23:50:00Z",
        },
    ]
    model = JobRuntimeXGBoostModel()
    plan = model.build_split_plan(rows, n_windows=2, test_window_hours=1)

    assert len(plan) == 2
    assert plan[0]["split_time"] == "2026-01-01T22:00:00Z"
    assert plan[0]["refresh_preprocessing"] is True
    assert plan[0]["train_row_count"] == 0
    assert plan[1]["split_time"] == "2026-01-01T23:00:00Z"
    assert plan[1]["refresh_preprocessing"] is False
    assert plan[1]["train_row_count"] == 1


def test_build_split_plan_respects_training_lookback_override() -> None:
    rows = [
        {
            "submit_time": "2025-10-15T10:00:00Z",
            "end_time": "2025-10-15T11:00:00Z",
        },
        {
            "submit_time": "2025-12-31T22:05:00Z",
            "end_time": "2025-12-31T22:30:00Z",
        },
        {
            "submit_time": "2026-01-01T00:05:00Z",
            "end_time": "2026-01-01T00:10:00Z",
        },
    ]
    model = JobRuntimeXGBoostModel()

    wide = model.build_split_plan(rows, n_windows=1, test_window_hours=1)
    narrow = model.build_split_plan(
        rows, n_windows=1, test_window_hours=1, training_lookback_days=1
    )

    assert wide[0]["train_row_count"] == 2
    assert narrow[0]["train_row_count"] == 1
