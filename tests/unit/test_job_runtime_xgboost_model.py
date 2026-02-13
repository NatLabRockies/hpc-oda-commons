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
    assert config.n_recent_hours == 1000
    assert config.submit_time_field == "submit_time"
    assert config.end_time_field == "end_time"
    assert config.explained_variance_target == 0.95
    assert config.infrequent_category_fraction == 0.01
    assert config.min_frequency_floor == 2
    assert config.target_max_one_hot_width == 2048
    assert config.max_svd_components == 256
    assert config.random_state == 42


def test_dependency_check_reports_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    model = JobRuntimeXGBoostModel()

    def fake_find_spec(name: str) -> object | None:
        if name in {"xgboost", "sklearn"}:
            return None
        return SimpleNamespace()

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    with pytest.raises(RuntimeError, match="xgboost, sklearn"):
        model._check_dependencies()


def test_fit_predict_and_hourly_are_scaffolded(monkeypatch: pytest.MonkeyPatch) -> None:
    model = JobRuntimeXGBoostModel()
    monkeypatch.setattr(model, "_check_dependencies", lambda: None)

    with pytest.raises(NotImplementedError, match="scaffolded in Increment 1"):
        model.fit([])
    with pytest.raises(NotImplementedError, match="scaffolded in Increment 1"):
        model.predict([])


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
    assert payload["analysis_version"] == "job_runtime_xgboost.preprocessing.v0.1.0"
    assert payload["row_count"] == 4
    assert payload["one_hot_analysis"]["encoded_feature_count"] > 0


def test_build_hourly_split_plan() -> None:
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
    plan = model.build_hourly_split_plan(rows, n_recent_hours=2)

    assert len(plan) == 2
    assert plan[0]["split_time"] == "2026-01-01T22:00:00Z"
    assert plan[0]["refresh_preprocessing"] is True
    assert plan[1]["split_time"] == "2026-01-01T23:00:00Z"
    assert plan[1]["refresh_preprocessing"] is False
