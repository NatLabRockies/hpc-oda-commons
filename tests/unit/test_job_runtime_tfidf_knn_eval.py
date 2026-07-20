from __future__ import annotations

import warnings
from datetime import datetime, timedelta, timezone

import pytest

from hpc_oda_commons.models.job_runtime_tfidf_knn.model import (
    JobRuntimeTfidfKnnConfig,
    JobRuntimeTfidfKnnModel,
)


def _dt(_s: str):
    """Parse an ISO-8601 Z timestamp to a tz-aware UTC datetime (v0.2 fixtures)."""
    from datetime import datetime

    return datetime.fromisoformat(_s.replace("Z", "+00:00"))


def _iso(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc)


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
            "submit_time": _dt("2026-01-01T00:00:00Z"),
            "end_time": _dt("2026-01-01T00:10:00Z"),
            "partition": "debug",
            "runtime_seconds": None,
        },
        {
            "job_id": 2,
            "submit_time": _dt("2026-01-01T01:00:00Z"),
            "end_time": _dt("2026-01-01T01:10:00Z"),
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


def test_window_n_jobs_is_order_invariant() -> None:
    """The independent per-window fits are exact: running them across a thread pool
    (window_n_jobs>1) yields identical metrics and window entries to the sequential path,
    so parallelism is a pure speedup and never changes results."""
    rows = _sample_rows()
    base = {"n_windows": 10, "test_window_hours": 1, "k": 3, "n_hash_features": 256}
    seq = JobRuntimeTfidfKnnModel(JobRuntimeTfidfKnnConfig(**base, window_n_jobs=1)).evaluate(rows)
    par = JobRuntimeTfidfKnnModel(JobRuntimeTfidfKnnConfig(**base, window_n_jobs=4)).evaluate(rows)

    assert seq["mae"] == par["mae"]
    assert seq["rmse"] == par["rmse"]
    assert seq["summary"] == par["summary"]
    assert seq["windows"] == par["windows"]


def test_precompute_slice_structure_matches_reference() -> None:
    """Precompute-and-slice preserves the evaluation *structure* of the original
    incremental-cache path: same windows scored vs skipped, same supervised row counts.
    The exact mae/rmse *values* are not reproducible across CPU/BLAS environments (a neighbor
    tie can flip — see docs/known-issues.md), so they are pinned by the xfail
    ``test_tfidf_knn_rolling_regression`` rather than asserted with a hardcoded float here."""
    payload = JobRuntimeTfidfKnnModel(
        JobRuntimeTfidfKnnConfig(n_windows=10, test_window_hours=1, k=3, n_hash_features=256)
    ).evaluate(_sample_rows())

    assert [entry["status"] for entry in payload["windows"]] == ["skipped"] + ["ok"] * 9
    assert payload["summary"]["windows_total"] == 10
    assert payload["summary"]["windows_scored"] == 9
    assert payload["summary"]["windows_skipped"] == 1
    assert payload["summary"]["rows_scored"] == 36
    # Every scored window drew on a non-empty supervised train/test slice.
    for entry in payload["windows"]:
        if entry["status"] == "ok":
            assert entry["train_rows_supervised"] >= 2
            assert entry["test_rows_supervised"] >= 1
    # Metrics are well-formed (the values themselves are env-sensitive; see docstring).
    assert payload["mae"] >= 0.0
    assert payload["rmse"] >= payload["mae"]


def test_no_joblib_parallel_warning_emitted() -> None:
    """The per-window kNN query runs single-threaded (the window pool supplies parallelism),
    so no sklearn joblib ``delayed``/``Parallel`` warning is emitted — the spam that previously
    ballooned large-cell logs to multiple GB."""
    model = JobRuntimeTfidfKnnModel(
        JobRuntimeTfidfKnnConfig(n_windows=6, test_window_hours=1, k=3, n_hash_features=256)
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model.evaluate(_sample_rows())

    joblib_warnings = [w for w in caught if "sklearn.utils.parallel" in str(w.message)]
    assert joblib_warnings == []
