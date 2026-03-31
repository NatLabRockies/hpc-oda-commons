from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from hpc_oda_commons.models.job_runtime_tfidf_knn.model import (
    JobRuntimeTfidfKnnConfig,
    JobRuntimeTfidfKnnModel,
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
            user = f"user{hour % 3:04d}"
            partition = "compute" if (hour + j) % 2 == 0 else "debug"
            name = f"job_name_{j % 5}"
            runtime_seconds = float(
                900 + 30 * hour + 20 * j + (60 if partition == "compute" else 0)
            )

            rows.append(
                {
                    "job_id": hour * 4 + j,
                    "submit_time": _iso(submit_time),
                    "end_time": _iso(end_time),
                    "user": user,
                    "partition": partition,
                    "name": name,
                    "runtime_seconds": runtime_seconds,
                }
            )
    return rows


def test_evaluate_returns_metrics_and_window_details() -> None:
    config = JobRuntimeTfidfKnnConfig(
        n_windows=10,
        test_window_hours=1,
        k=3,
        n_hash_features=256,
    )
    model = JobRuntimeTfidfKnnModel(config)
    payload = model.evaluate(_sample_rows())

    assert payload["mae"] >= 0.0
    assert payload["rmse"] >= 0.0
    assert payload["summary"]["windows_total"] == 10
    assert payload["summary"]["windows_scored"] > 0
    assert payload["summary"]["windows_skipped"] >= 0
    assert payload["summary"]["rows_scored"] > 0

    windows = payload["windows"]
    assert len(windows) == 10
    assert any(entry["status"] == "ok" for entry in windows)
    assert (
        sum(1 for entry in windows if entry["status"] == "ok")
        == payload["summary"]["windows_scored"]
    )


def test_evaluate_raises_when_no_scored_predictions() -> None:
    rows = [
        {
            "job_id": 1,
            "submit_time": "2026-01-01T00:00:00Z",
            "end_time": "2026-01-01T00:10:00Z",
            "partition": "debug",
            "runtime_seconds": None,
        },
        {
            "job_id": 2,
            "submit_time": "2026-01-01T01:00:00Z",
            "end_time": "2026-01-01T01:10:00Z",
            "partition": "compute",
            "runtime_seconds": None,
        },
    ]
    config = JobRuntimeTfidfKnnConfig(n_windows=2, test_window_hours=1, n_hash_features=64)
    model = JobRuntimeTfidfKnnModel(config)

    with pytest.raises(ValueError, match="No rolling splits produced scored predictions"):
        model.evaluate(rows)


def test_evaluate_verbose_uses_tqdm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = JobRuntimeTfidfKnnConfig(n_windows=4, test_window_hours=1, n_hash_features=256)
    model = JobRuntimeTfidfKnnModel(config)

    seen: dict[str, object] = {}

    def fake_tqdm(iterable: list[object], **kwargs: object) -> list[object]:
        seen["kwargs"] = kwargs
        return iterable

    monkeypatch.setattr(
        "hpc_oda_commons.models.job_runtime_tfidf_knn.model.tqdm",
        fake_tqdm,
    )
    payload = model.evaluate(_sample_rows(), verbose=True)
    assert payload["summary"]["windows_total"] == 4
    kwargs = seen["kwargs"]
    assert kwargs["desc"] == "rolling/tfidf_knn"
    assert kwargs["unit"] == "window"
    assert kwargs["disable"] is False
