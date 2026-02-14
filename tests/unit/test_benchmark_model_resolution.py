from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import typer

from hpc_oda_commons.qst import cli


def _write_dataset(path: Path) -> None:
    rows = [
        {
            "job_id": 1,
            "submit_time": "2026-01-01T00:05:00Z",
            "start_time": "2026-01-01T00:06:00Z",
            "end_time": "2026-01-01T00:20:00Z",
            "runtime_seconds": 840.0,
            "partition": "debug",
            "allocated_cpus": 2,
        },
        {
            "job_id": 2,
            "submit_time": "2026-01-01T01:10:00Z",
            "start_time": "2026-01-01T01:12:00Z",
            "end_time": "2026-01-01T01:30:00Z",
            "runtime_seconds": 1080.0,
            "partition": "compute",
            "allocated_cpus": 4,
        },
        {
            "job_id": 3,
            "submit_time": "2026-01-01T02:15:00Z",
            "start_time": "2026-01-01T02:16:00Z",
            "end_time": "2026-01-01T02:33:00Z",
            "runtime_seconds": 1020.0,
            "partition": "debug",
            "allocated_cpus": 2,
        },
    ]
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)


def _write_recipe(path: Path, *, model_id: str, split_block: str, table_path: Path) -> None:
    text = "\n".join(
        [
            "recipe_id: recipe.test.benchmark_path",
            "problem_domain:",
            "  - job-runtime-prediction",
            "schema_version: oda.job.v0.1.0",
            "dataset:",
            "  id: test_dataset",
            f"  table_path: {table_path.as_posix()}",
            "model:",
            f"  id: {model_id}",
            '  version: "0.1.0"',
            "metrics:",
            "  - name: mae",
            "    target: runtime_seconds",
            "  - name: rmse",
            "    target: runtime_seconds",
            "split:",
            split_block,
            "run:",
            "  output_dir: runs",
            "  overwrite: false",
        ]
    )
    path.write_text(text + "\n", encoding="utf-8")


def _first_result_bundle(runs_dir: Path) -> Path:
    matches = sorted(runs_dir.rglob("result.json"))
    assert matches
    return matches[0].parent


def test_benchmark_rolling_hourly_uses_xgboost_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeXGBModel:
        seen_n_recent_hours: int | None = None
        seen_training_lookback_days: int | None = None

        def __init__(self, config: object) -> None:
            FakeXGBModel.seen_n_recent_hours = int(config.n_recent_hours)
            FakeXGBModel.seen_training_lookback_days = int(config.training_lookback_days)

        def evaluate_hourly(
            self,
            rows: list[dict[str, object]],
            *,
            verbose: bool = False,
        ) -> dict[str, object]:
            assert rows
            _ = verbose
            return {
                "mae": 1.25,
                "rmse": 2.5,
                "hourly": [{"status": "ok", "metrics": {"mae": 1.25, "rmse": 2.5}}],
                "summary": {
                    "hours_total": 4,
                    "hours_scored": 1,
                    "hours_skipped": 3,
                    "preprocessing_refits": 1,
                    "rows_scored": 3,
                    "days_with_cached_preprocessing": ["2026-01-01"],
                    "n_recent_hours": 4,
                    "training_lookback_days": 7,
                },
            }

    monkeypatch.setattr(cli, "JobRuntimeXGBoostModel", FakeXGBModel)
    monkeypatch.chdir(tmp_path)

    table_path = tmp_path / "jobs.parquet"
    recipe_path = tmp_path / "rolling.yml"
    _write_dataset(table_path)
    _write_recipe(
        recipe_path,
        model_id="model.job_runtime_xgboost",
        split_block="\n".join(
            [
                "  method: rolling_hourly",
                "  n_recent_hours: 4",
                "  training_lookback_days: 7",
            ]
        ),
        table_path=table_path,
    )

    cli.benchmark(recipe_path)

    bundle = _first_result_bundle(tmp_path / "runs")
    result = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
    metrics_payload = json.loads((bundle / "metrics.json").read_text(encoding="utf-8"))

    assert FakeXGBModel.seen_n_recent_hours == 4
    assert FakeXGBModel.seen_training_lookback_days == 7
    assert result["model"]["id"] == "model.job_runtime_xgboost"
    assert result["metrics"]["mae"] == 1.25
    assert result["metrics"]["rmse"] == 2.5
    assert "hourly" in metrics_payload
    assert metrics_payload["summary"]["hours_total"] == 4


def test_benchmark_rejects_unsupported_model_split_combo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    table_path = tmp_path / "jobs.parquet"
    recipe_path = tmp_path / "bad_combo.yml"
    _write_dataset(table_path)
    _write_recipe(
        recipe_path,
        model_id="model.job_runtime_xgboost",
        split_block="\n".join(
            [
                "  method: fixed",
                "  train_fraction: 0.8",
                "  seed: 42",
            ]
        ),
        table_path=table_path,
    )

    with pytest.raises(typer.BadParameter, match="Unsupported model/split combination"):
        cli.benchmark(recipe_path)


def test_benchmark_rolling_hourly_uses_default_training_lookback_days(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeXGBModel:
        seen_training_lookback_days: int | None = None

        def __init__(self, config: object) -> None:
            FakeXGBModel.seen_training_lookback_days = int(config.training_lookback_days)

        def evaluate_hourly(
            self,
            rows: list[dict[str, object]],
            *,
            verbose: bool = False,
        ) -> dict[str, object]:
            assert rows
            _ = verbose
            return {
                "mae": 1.0,
                "rmse": 1.5,
                "hourly": [{"status": "ok", "metrics": {"mae": 1.0, "rmse": 1.5}}],
                "summary": {
                    "hours_total": 3,
                    "hours_scored": 1,
                    "hours_skipped": 2,
                    "preprocessing_refits": 1,
                    "rows_scored": 2,
                    "days_with_cached_preprocessing": ["2026-01-01"],
                    "n_recent_hours": 3,
                    "training_lookback_days": 100,
                },
            }

    monkeypatch.setattr(cli, "JobRuntimeXGBoostModel", FakeXGBModel)
    monkeypatch.chdir(tmp_path)

    table_path = tmp_path / "jobs.parquet"
    recipe_path = tmp_path / "rolling_default_lookback.yml"
    _write_dataset(table_path)
    _write_recipe(
        recipe_path,
        model_id="model.job_runtime_xgboost",
        split_block="\n".join(["  method: rolling_hourly", "  n_recent_hours: 3"]),
        table_path=table_path,
    )

    cli.benchmark(recipe_path)
    assert FakeXGBModel.seen_training_lookback_days == 100


def test_benchmark_verbose_prints_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeXGBModel:
        seen_verbose: bool | None = None

        def __init__(self, config: object) -> None:
            _ = config

        def evaluate_hourly(
            self,
            rows: list[dict[str, object]],
            *,
            verbose: bool = False,
        ) -> dict[str, object]:
            assert rows
            FakeXGBModel.seen_verbose = verbose
            return {
                "mae": 1.25,
                "rmse": 2.5,
                "hourly": [{"status": "ok", "metrics": {"mae": 1.25, "rmse": 2.5}}],
                "summary": {
                    "hours_total": 4,
                    "hours_scored": 1,
                    "hours_skipped": 3,
                    "preprocessing_refits": 1,
                    "rows_scored": 3,
                    "days_with_cached_preprocessing": ["2026-01-01"],
                    "n_recent_hours": 4,
                    "training_lookback_days": 7,
                },
            }

    monkeypatch.setattr(cli, "JobRuntimeXGBoostModel", FakeXGBModel)
    monkeypatch.chdir(tmp_path)

    table_path = tmp_path / "jobs.parquet"
    recipe_path = tmp_path / "rolling_verbose.yml"
    _write_dataset(table_path)
    _write_recipe(
        recipe_path,
        model_id="model.job_runtime_xgboost",
        split_block="\n".join(
            [
                "  method: rolling_hourly",
                "  n_recent_hours: 4",
                "  training_lookback_days: 7",
            ]
        ),
        table_path=table_path,
    )

    cli.benchmark(recipe_path, verbose=True)
    assert FakeXGBModel.seen_verbose is True
