from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from hpc_oda_commons.models.job_runtime_xgboost.model import (
    JobRuntimeXGBoostConfig,
    JobRuntimeXGBoostModel,
)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sample_rows() -> list[dict[str, object]]:
    base = datetime(2026, 1, 1, 20, 0, 0, tzinfo=timezone.utc)
    rows: list[dict[str, object]] = []
    for hour in range(10):
        hour_start = base + timedelta(hours=hour)
        for j in range(4):
            submit_time = hour_start + timedelta(minutes=10 * j)
            end_time = submit_time + timedelta(minutes=20 + j)
            partition = "compute" if (hour + j) % 2 == 0 else "debug"
            account = f"acct_{hour % 3}"
            qos = "high" if j == 0 else "normal"
            requested_cpus = float((j % 4) + 1)
            memory_requested = float(2048 + 128 * j + 32 * hour)
            runtime_seconds = float(
                900 + 30 * hour + 20 * j + (60 if partition == "compute" else 0)
            )

            rows.append(
                {
                    "submit_time": _iso(submit_time),
                    "end_time": _iso(end_time),
                    "partition": partition,
                    "account": account,
                    "qos": qos,
                    "requested_cpus": requested_cpus,
                    "memory_requested": memory_requested,
                    "runtime_seconds": runtime_seconds,
                }
            )
    return rows


class _FakeRegressor:
    def __init__(self) -> None:
        self._mean: float = 0.0

    def fit(self, x: np.ndarray, y: np.ndarray) -> _FakeRegressor:
        _ = x
        self._mean = float(np.mean(y)) if len(y) else 0.0
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        return np.full((x.shape[0],), self._mean, dtype=float)


def test_evaluate_returns_metrics_and_window_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = JobRuntimeXGBoostConfig(
        n_windows=10,
        test_window_hours=1,
        n_estimators=16,
        max_depth=4,
        learning_rate=0.1,
        subsample=1.0,
        colsample_bytree=1.0,
        max_svd_components=8,
        target_max_one_hot_width=64,
        random_state=7,
    )
    model = JobRuntimeXGBoostModel(config)
    monkeypatch.setattr(model, "_new_xgb_regressor", lambda: _FakeRegressor())
    payload = model.evaluate(_sample_rows())

    assert payload["mae"] >= 0.0
    assert payload["rmse"] >= 0.0
    assert payload["summary"]["windows_total"] == 10
    assert payload["summary"]["windows_scored"] > 0
    assert payload["summary"]["windows_skipped"] >= 0
    assert payload["summary"]["preprocessing_refits"] == 2
    assert payload["summary"]["rows_scored"] > 0
    assert payload["summary"]["training_lookback_days"] == 100

    windows = payload["windows"]
    assert len(windows) == 10
    assert any(entry["status"] == "ok" for entry in windows)
    assert (
        sum(1 for entry in windows if entry["status"] == "ok")
        == payload["summary"]["windows_scored"]
    )
    assert (
        sum(1 for entry in windows if entry["preprocessing_refit"])
        == payload["summary"]["preprocessing_refits"]
    )


def test_evaluate_raises_when_no_scored_predictions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "submit_time": "2026-01-01T00:00:00Z",
            "end_time": "2026-01-01T00:10:00Z",
            "partition": "debug",
            "runtime_seconds": None,
        },
        {
            "submit_time": "2026-01-01T01:00:00Z",
            "end_time": "2026-01-01T01:10:00Z",
            "partition": "compute",
            "runtime_seconds": None,
        },
    ]
    config = JobRuntimeXGBoostConfig(n_windows=2, test_window_hours=1, n_estimators=8, max_depth=3)
    model = JobRuntimeXGBoostModel(config)
    monkeypatch.setattr(model, "_new_xgb_regressor", lambda: _FakeRegressor())

    with pytest.raises(ValueError, match="No rolling splits produced scored predictions"):
        model.evaluate(rows)


def test_evaluate_verbose_uses_tqdm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = JobRuntimeXGBoostConfig(
        n_windows=4, test_window_hours=1, max_svd_components=8, target_max_one_hot_width=64
    )
    model = JobRuntimeXGBoostModel(config)
    monkeypatch.setattr(model, "_new_xgb_regressor", lambda: _FakeRegressor())

    seen: dict[str, object] = {}

    def fake_tqdm(iterable: list[object], **kwargs: object) -> list[object]:
        seen["kwargs"] = kwargs
        return iterable

    monkeypatch.setattr(
        "hpc_oda_commons.models.job_runtime_xgboost.model.tqdm",
        fake_tqdm,
    )
    payload = model.evaluate(_sample_rows(), verbose=True)
    assert payload["summary"]["windows_total"] == 4
    kwargs = seen["kwargs"]
    assert kwargs["desc"] == "rolling/xgboost"
    assert kwargs["unit"] == "window"
    assert kwargs["disable"] is False


def test_evaluate_passes_verbose_to_split_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = JobRuntimeXGBoostConfig(n_windows=2, test_window_hours=1)
    model = JobRuntimeXGBoostModel(config)
    monkeypatch.setattr(model, "_check_dependencies", lambda: None)

    seen_verbose: dict[str, bool | None] = {"value": None}

    def fake_build_rolling_splits(
        rows: list[dict[str, object]],
        *,
        n_windows: int = 1000,
        test_window_hours: int = 6,
        training_lookback_days: int = 100,
        submit_time_field: str = "submit_time",
        end_time_field: str = "end_time",
        verbose: bool = False,
    ) -> list[object]:
        _ = (
            rows,
            n_windows,
            test_window_hours,
            training_lookback_days,
            submit_time_field,
            end_time_field,
        )
        seen_verbose["value"] = verbose
        return []

    monkeypatch.setattr(
        "hpc_oda_commons.models.job_runtime_xgboost.model.build_rolling_splits",
        fake_build_rolling_splits,
    )

    with pytest.raises(ValueError, match="No rolling splits produced scored predictions"):
        model.evaluate(_sample_rows(), verbose=True)

    assert seen_verbose["value"] is True


def test_evaluate_verbose_prints_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = JobRuntimeXGBoostConfig(
        n_windows=4,
        test_window_hours=1,
        max_svd_components=8,
        target_max_one_hot_width=64,
    )
    model = JobRuntimeXGBoostModel(config)
    monkeypatch.setattr(model, "_new_xgb_regressor", lambda: _FakeRegressor())

    _ = model.evaluate(_sample_rows(), verbose=True)
    captured = capsys.readouterr()
    assert "[xgboost][verbose] starting rolling evaluation" in captured.out
    assert "[xgboost][verbose] summary" in captured.out
