from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import typer

from hpc_oda_commons.benchmark import runner
from hpc_oda_commons.qst import cli


def _dt(_s: str):
    """Parse an ISO-8601 Z timestamp to a tz-aware UTC datetime (v0.2 fixtures)."""
    from datetime import datetime

    return datetime.fromisoformat(_s.replace("Z", "+00:00"))


def _write_dataset(path: Path) -> None:
    rows = [
        {
            "job_id": 1,
            "submit_time": _dt("2026-01-01T00:05:00Z"),
            "start_time": _dt("2026-01-01T00:06:00Z"),
            "end_time": _dt("2026-01-01T00:20:00Z"),
            "runtime_seconds": 840.0,
            "partition": "debug",
            "allocated_cpus": 2,
        },
        {
            "job_id": 2,
            "submit_time": _dt("2026-01-01T01:10:00Z"),
            "start_time": _dt("2026-01-01T01:12:00Z"),
            "end_time": _dt("2026-01-01T01:30:00Z"),
            "runtime_seconds": 1080.0,
            "partition": "compute",
            "allocated_cpus": 4,
        },
        {
            "job_id": 3,
            "submit_time": _dt("2026-01-01T02:15:00Z"),
            "start_time": _dt("2026-01-01T02:16:00Z"),
            "end_time": _dt("2026-01-01T02:33:00Z"),
            "runtime_seconds": 1020.0,
            "partition": "debug",
            "allocated_cpus": 2,
        },
    ]
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)


def _write_recipe(
    path: Path,
    *,
    model_id: str,
    split_block: str,
    table_path: Path,
    output_dir: str = "runs",
    overwrite: bool = False,
) -> None:
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
            f"  output_dir: {output_dir}",
            f"  overwrite: {'true' if overwrite else 'false'}",
        ]
    )
    path.write_text(text + "\n", encoding="utf-8")


def _first_result_bundle(runs_dir: Path) -> Path:
    matches = sorted(runs_dir.rglob("result.json"))
    assert matches
    return matches[0].parent


def test_benchmark_rolling_uses_xgboost_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeXGBModel:
        seen_n_windows: int | None = None
        seen_training_lookback_days: int | None = None

        def __init__(self, config: object) -> None:
            FakeXGBModel.seen_n_windows = int(config.n_windows)
            FakeXGBModel.seen_training_lookback_days = int(config.training_lookback_days)

        def evaluate(
            self,
            rows: list[dict[str, object]],
            *,
            verbose: bool = False,
            metric_defs: list[dict[str, object]] | None = None,
            capture_artifacts: bool = False,
        ) -> dict[str, object]:
            assert rows
            _ = verbose
            _ = metric_defs
            _ = capture_artifacts
            return {
                "mae": 1.25,
                "rmse": 2.5,
                "windows": [{"status": "ok", "metrics": {"mae": 1.25, "rmse": 2.5}}],
                "summary": {
                    "windows_total": 4,
                    "windows_scored": 1,
                    "windows_skipped": 3,
                    "preprocessing_refits": 1,
                    "rows_scored": 3,
                    "days_with_cached_preprocessing": ["2026-01-01"],
                    "n_windows": 4,
                    "training_lookback_days": 7,
                },
            }

    monkeypatch.setattr(runner, "JobRuntimeXGBoostModel", FakeXGBModel)
    monkeypatch.chdir(tmp_path)

    table_path = tmp_path / "jobs.parquet"
    recipe_path = tmp_path / "rolling.yml"
    _write_dataset(table_path)
    _write_recipe(
        recipe_path,
        model_id="model.job_runtime_xgboost",
        split_block="\n".join(
            [
                "  method: rolling",
                "  n_windows: 4",
                "  training_lookback_days: 7",
            ]
        ),
        table_path=table_path,
    )

    cli.benchmark(recipe_path)

    bundle = _first_result_bundle(tmp_path / "runs")
    result = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
    metrics_payload = json.loads((bundle / "metrics.json").read_text(encoding="utf-8"))

    assert FakeXGBModel.seen_n_windows == 4
    assert FakeXGBModel.seen_training_lookback_days == 7
    assert result["model"]["id"] == "model.job_runtime_xgboost"
    assert result["metrics"]["mae"] == 1.25
    assert result["metrics"]["rmse"] == 2.5
    assert result["timing"]["total_train_eval_seconds"] >= 0.0
    assert "windows" in metrics_payload
    assert metrics_payload["summary"]["windows_total"] == 4


def test_benchmark_baseline_rolling_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """baseline + rolling dispatches to run_rolling_baseline."""
    monkeypatch.chdir(tmp_path)

    table_path = tmp_path / "jobs.parquet"
    recipe_path = tmp_path / "baseline_rolling.yml"
    _write_dataset(table_path)
    _write_recipe(
        recipe_path,
        model_id="model.job_runtime_baseline",
        split_block="\n".join(
            [
                "  method: rolling",
                "  n_windows: 2",
                "  test_window_hours: 1",
            ]
        ),
        table_path=table_path,
    )

    cli.benchmark(recipe_path)

    bundle = _first_result_bundle(tmp_path / "runs")
    result = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
    metrics_payload = json.loads((bundle / "metrics.json").read_text(encoding="utf-8"))

    assert result["model"]["id"] == "model.job_runtime_baseline"
    assert result["metrics"]["mae"] >= 0.0
    assert result["metrics"]["rmse"] >= 0.0
    assert "windows" in metrics_payload
    assert metrics_payload["summary"]["windows_total"] == 2


def test_benchmark_tfidf_knn_rolling_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """tfidf_knn + rolling dispatches to run_rolling_tfidf_knn."""

    class FakeTfidfKnnModel:
        def __init__(self, config: object) -> None:
            pass

        def evaluate(
            self,
            rows: list[dict[str, object]],
            *,
            verbose: bool = False,
            metric_defs: list[dict[str, object]] | None = None,
            capture_artifacts: bool = False,
        ) -> dict[str, object]:
            assert rows
            _ = verbose
            _ = metric_defs
            _ = capture_artifacts
            return {
                "mae": 2.0,
                "rmse": 3.0,
                "windows": [{"status": "ok", "metrics": {"mae": 2.0, "rmse": 3.0}}],
                "summary": {
                    "windows_total": 2,
                    "windows_scored": 1,
                    "windows_skipped": 1,
                    "rows_scored": 3,
                    "n_windows": 2,
                    "test_window_hours": 1,
                    "training_lookback_days": 100,
                },
            }

    monkeypatch.setattr(runner, "JobRuntimeTfidfKnnModel", FakeTfidfKnnModel)
    monkeypatch.chdir(tmp_path)

    table_path = tmp_path / "jobs.parquet"
    recipe_path = tmp_path / "tfidf_knn_rolling.yml"
    _write_dataset(table_path)
    _write_recipe(
        recipe_path,
        model_id="model.job_runtime_tfidf_knn",
        split_block="\n".join(
            [
                "  method: rolling",
                "  n_windows: 2",
                "  test_window_hours: 1",
            ]
        ),
        table_path=table_path,
    )

    cli.benchmark(recipe_path)

    bundle = _first_result_bundle(tmp_path / "runs")
    result = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
    metrics_payload = json.loads((bundle / "metrics.json").read_text(encoding="utf-8"))

    assert result["model"]["id"] == "model.job_runtime_tfidf_knn"
    assert result["metrics"]["mae"] == 2.0
    assert result["metrics"]["rmse"] == 3.0
    assert "windows" in metrics_payload
    assert metrics_payload["summary"]["windows_total"] == 2


def test_benchmark_mlp_rolling_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """mlp + rolling dispatches to run_rolling_mlp."""

    class FakeMlpModel:
        def __init__(self, config: object) -> None:
            pass

        def evaluate(
            self,
            rows: list[dict[str, object]],
            *,
            verbose: bool = False,
            metric_defs: list[dict[str, object]] | None = None,
            capture_artifacts: bool = False,
        ) -> dict[str, object]:
            assert rows
            _ = verbose
            _ = metric_defs
            _ = capture_artifacts
            return {
                "mae": 3.0,
                "rmse": 4.0,
                "windows": [{"status": "ok", "metrics": {"mae": 3.0, "rmse": 4.0}}],
                "summary": {
                    "windows_total": 2,
                    "windows_scored": 1,
                    "windows_skipped": 1,
                    "rows_scored": 3,
                    "n_windows": 2,
                    "test_window_hours": 1,
                    "training_lookback_days": 100,
                },
            }

    monkeypatch.setattr(runner, "JobRuntimeMlpModel", FakeMlpModel)
    monkeypatch.chdir(tmp_path)

    table_path = tmp_path / "jobs.parquet"
    recipe_path = tmp_path / "mlp_rolling.yml"
    _write_dataset(table_path)
    _write_recipe(
        recipe_path,
        model_id="model.job_runtime_mlp",
        split_block="\n".join(
            [
                "  method: rolling",
                "  n_windows: 2",
                "  test_window_hours: 1",
            ]
        ),
        table_path=table_path,
    )

    cli.benchmark(recipe_path)

    bundle = _first_result_bundle(tmp_path / "runs")
    result = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
    metrics_payload = json.loads((bundle / "metrics.json").read_text(encoding="utf-8"))

    assert result["model"]["id"] == "model.job_runtime_mlp"
    assert result["metrics"]["mae"] == 3.0
    assert result["metrics"]["rmse"] == 4.0
    assert "windows" in metrics_payload
    assert metrics_payload["summary"]["windows_total"] == 2


def test_benchmark_uopc_fixed_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeUopcModel:
        def evaluate_fixed(
            self,
            rows: list[dict[str, object]],
            *,
            split: dict[str, object],
            metric_defs: list[dict[str, object]] | None = None,
            verbose: bool = False,
            capture_artifacts: bool = False,
        ) -> dict[str, object]:
            assert rows
            _ = split
            _ = metric_defs
            _ = verbose
            _ = capture_artifacts
            return {
                "mae": 12.5,
                "rmse": 20.0,
                "summary": {"rows_scored": 10, "rows_skipped": 2},
            }

    monkeypatch.setattr(runner, "JobPowerUopcModel", FakeUopcModel)
    monkeypatch.chdir(tmp_path)

    rows = [
        {
            "usr": "alice",
            "jnam": "job_a",
            "cnumr": 64,
            "nnumr": 2,
            "edt": "2024-04-01T00:00:00+09:00",
            "maxpcon": 1500.0,
        },
        {
            "usr": "alice",
            "jnam": "job_b",
            "cnumr": 128,
            "nnumr": 4,
            "edt": "2024-04-01T01:00:00+09:00",
            "maxpcon": 1600.0,
        },
    ]
    table_path = tmp_path / "power.parquet"
    pq.write_table(pa.Table.from_pylist(rows), table_path)

    recipe_path = tmp_path / "uopc_fixed.yml"
    text = "\n".join(
        [
            "recipe_id: recipe.test.uopc_fixed",
            "problem_domain:",
            "  - job-power-prediction",
            "schema_version: oda.job.v0.1.0",
            "dataset:",
            "  id: test_power",
            f"  table_path: {table_path.as_posix()}",
            "model:",
            "  id: model.job_power_uopc",
            '  version: "0.1.0"',
            "metrics:",
            "  - name: mae",
            "    target: maxpcon",
            "  - name: rmse",
            "    target: maxpcon",
            "split:",
            "  method: fixed",
            "  train_fraction: 0.5",
            "  seed: 42",
            "run:",
            "  output_dir: runs",
            "  overwrite: false",
        ]
    )
    recipe_path.write_text(text + "\n", encoding="utf-8")

    cli.benchmark(recipe_path)

    bundle = _first_result_bundle(tmp_path / "runs")
    result = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
    metrics_payload = json.loads((bundle / "metrics.json").read_text(encoding="utf-8"))

    assert result["model"]["id"] == "model.job_power_uopc"
    assert result["metrics"]["mae"] == 12.5
    assert result["metrics"]["rmse"] == 20.0
    assert metrics_payload["summary"]["rows_scored"] == 10


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


def test_benchmark_rolling_uses_default_training_lookback_days(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeXGBModel:
        seen_training_lookback_days: int | None = None

        def __init__(self, config: object) -> None:
            FakeXGBModel.seen_training_lookback_days = int(config.training_lookback_days)

        def evaluate(
            self,
            rows: list[dict[str, object]],
            *,
            verbose: bool = False,
            metric_defs: list[dict[str, object]] | None = None,
            capture_artifacts: bool = False,
        ) -> dict[str, object]:
            assert rows
            _ = verbose
            _ = metric_defs
            _ = capture_artifacts
            return {
                "mae": 1.0,
                "rmse": 1.5,
                "windows": [{"status": "ok", "metrics": {"mae": 1.0, "rmse": 1.5}}],
                "summary": {
                    "windows_total": 3,
                    "windows_scored": 1,
                    "windows_skipped": 2,
                    "preprocessing_refits": 1,
                    "rows_scored": 2,
                    "days_with_cached_preprocessing": ["2026-01-01"],
                    "n_windows": 3,
                    "training_lookback_days": 100,
                },
            }

    monkeypatch.setattr(runner, "JobRuntimeXGBoostModel", FakeXGBModel)
    monkeypatch.chdir(tmp_path)

    table_path = tmp_path / "jobs.parquet"
    recipe_path = tmp_path / "rolling_default_lookback.yml"
    _write_dataset(table_path)
    _write_recipe(
        recipe_path,
        model_id="model.job_runtime_xgboost",
        split_block="\n".join(["  method: rolling", "  n_windows: 3"]),
        table_path=table_path,
    )

    cli.benchmark(recipe_path)
    assert FakeXGBModel.seen_training_lookback_days == 100


def test_benchmark_verbose_prints_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeXGBModel:
        seen_verbose: bool | None = None

        def __init__(self, config: object) -> None:
            _ = config

        def evaluate(
            self,
            rows: list[dict[str, object]],
            *,
            verbose: bool = False,
            metric_defs: list[dict[str, object]] | None = None,
            capture_artifacts: bool = False,
        ) -> dict[str, object]:
            assert rows
            FakeXGBModel.seen_verbose = verbose
            _ = metric_defs
            _ = capture_artifacts
            return {
                "mae": 1.25,
                "rmse": 2.5,
                "windows": [{"status": "ok", "metrics": {"mae": 1.25, "rmse": 2.5}}],
                "summary": {
                    "windows_total": 4,
                    "windows_scored": 1,
                    "windows_skipped": 3,
                    "preprocessing_refits": 1,
                    "rows_scored": 3,
                    "days_with_cached_preprocessing": ["2026-01-01"],
                    "n_windows": 4,
                    "training_lookback_days": 7,
                },
            }

    monkeypatch.setattr(runner, "JobRuntimeXGBoostModel", FakeXGBModel)
    monkeypatch.chdir(tmp_path)

    table_path = tmp_path / "jobs.parquet"
    recipe_path = tmp_path / "rolling_verbose.yml"
    _write_dataset(table_path)
    _write_recipe(
        recipe_path,
        model_id="model.job_runtime_xgboost",
        split_block="\n".join(
            [
                "  method: rolling",
                "  n_windows: 4",
                "  training_lookback_days: 7",
            ]
        ),
        table_path=table_path,
    )

    cli.benchmark(recipe_path, verbose=True)
    assert FakeXGBModel.seen_verbose is True
    captured = capsys.readouterr()
    assert "benchmark resolved:" in captured.out
    assert "benchmark metrics:" in captured.out


_FIXED_SPLIT = "\n".join(["  method: fixed", "  train_fraction: 0.8", "  seed: 42"])


def test_benchmark_honors_output_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """recipe.run.output_dir places the result bundle under that directory."""
    monkeypatch.chdir(tmp_path)
    table_path = tmp_path / "jobs.parquet"
    recipe_path = tmp_path / "recipe.yml"
    _write_dataset(table_path)
    _write_recipe(
        recipe_path,
        model_id="model.job_runtime_baseline",
        split_block=_FIXED_SPLIT,
        table_path=table_path,
        output_dir="custom_runs",
    )

    cli.benchmark(recipe_path)

    bundle = _first_result_bundle(tmp_path / "custom_runs")
    assert (bundle / "result.json").exists()
    # nothing was written to the default runs/ directory
    assert not list((tmp_path / "runs").glob("benchmark-*"))


def test_benchmark_overwrite_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An existing bundle is rejected unless run.overwrite is true."""
    from datetime import datetime as _dt

    fixed = _dt(2026, 1, 1, 12, 0, 0)

    class _Frozen(_dt):
        @classmethod
        def now(cls, tz: object = None) -> _dt:
            return fixed if tz is None else fixed.replace(tzinfo=tz)  # type: ignore[arg-type]

    monkeypatch.setattr(cli, "datetime", _Frozen)
    monkeypatch.chdir(tmp_path)

    table_path = tmp_path / "jobs.parquet"
    recipe_path = tmp_path / "recipe.yml"
    _write_dataset(table_path)
    _write_recipe(
        recipe_path,
        model_id="model.job_runtime_baseline",
        split_block=_FIXED_SPLIT,
        table_path=table_path,
        overwrite=False,
    )

    cli.benchmark(recipe_path)  # first run creates the (now deterministic) bundle

    with pytest.raises(typer.BadParameter, match="already exists"):
        cli.benchmark(recipe_path)  # same run_id, overwrite false -> rejected

    _write_recipe(
        recipe_path,
        model_id="model.job_runtime_baseline",
        split_block=_FIXED_SPLIT,
        table_path=table_path,
        overwrite=True,
    )
    cli.benchmark(recipe_path)  # overwrite true -> proceeds without raising


def test_benchmark_missing_dataset_no_synthetic_fallback_for_non_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-runtime recipe with a missing dataset must error, not silently fall
    back to the synthetic job-runtime dataset (which lacks the recipe's target)."""
    monkeypatch.chdir(tmp_path)

    recipe_path = tmp_path / "power.yml"
    recipe_path.write_text(
        "\n".join(
            [
                "recipe_id: recipe.test.power_missing",
                "problem_domain:",
                "  - job-power-prediction",
                "schema_version: oda.job.v0.1.0",
                "dataset:",
                "  id: test_dataset",
                "  table_path: data/does_not_exist.parquet",
                "model:",
                "  id: model.job_power_uopc",
                '  version: "0.1.0"',
                "metrics:",
                "  - name: mae",
                "    target: maxpcon",
                "  - name: rmse",
                "    target: maxpcon",
                "split:",
                "  method: fixed",
                "  train_fraction: 0.8",
                "  seed: 42",
                "run:",
                "  output_dir: runs",
                "  overwrite: false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(typer.BadParameter, match="synthetic fallback"):
        cli.benchmark(recipe_path)
