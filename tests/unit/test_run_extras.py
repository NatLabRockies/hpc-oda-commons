from __future__ import annotations

import pickle
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from hpc_oda_commons.benchmark.run_extras import (
    BenchmarkArtifacts,
    RunExtras,
    parse_run_extras,
    write_run_extras,
)
from hpc_oda_commons.benchmark.runner import run_fixed_baseline


def test_parse_run_extras_defaults() -> None:
    extras = parse_run_extras({"run": {"output_dir": "runs"}})
    assert extras == RunExtras()


def test_parse_run_extras_enabled() -> None:
    extras = parse_run_extras(
        {
            "run": {
                "extras": {
                    "save_predictions": True,
                    "save_plot": True,
                    "save_model": False,
                }
            }
        }
    )
    assert extras.save_predictions is True
    assert extras.save_plot is True
    assert extras.save_model is False


def test_write_predictions_parquet(tmp_path: Path) -> None:
    artifacts = BenchmarkArtifacts(
        y_true=[100.0, 200.0],
        y_pred=[110.0, 180.0],
    )
    written = write_run_extras(
        tmp_path,
        RunExtras(save_predictions=True),
        artifacts,
    )
    assert written == ["predictions.parquet"]
    table = pq.read_table(tmp_path / "predictions.parquet")
    assert table.column_names == ["y_true", "y_pred"]
    assert table.num_rows == 2


def test_write_plot_requires_matplotlib(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    artifacts = BenchmarkArtifacts(y_true=[1.0, 2.0], y_pred=[1.1, 1.9])
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "matplotlib" or name.startswith("matplotlib."):
            raise ImportError("no matplotlib")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match="matplotlib"):
        write_run_extras(tmp_path, RunExtras(save_plot=True), artifacts)


def test_write_model_pickle(tmp_path: Path) -> None:
    artifacts = BenchmarkArtifacts(
        y_true=[1.0],
        y_pred=[1.0],
        last_model={"kind": "test", "value": 42},
    )
    written = write_run_extras(tmp_path, RunExtras(save_model=True), artifacts)
    assert written == ["model/last_model.pkl"]
    with (tmp_path / "model" / "last_model.pkl").open("rb") as handle:
        loaded = pickle.load(handle)
    assert loaded == {"kind": "test", "value": 42}


def test_run_fixed_baseline_capture_artifacts() -> None:
    rows = [
        {"runtime_seconds": 100.0},
        {"runtime_seconds": 200.0},
        {"runtime_seconds": 300.0},
        {"runtime_seconds": 400.0},
        {"runtime_seconds": 500.0},
    ]
    metric_defs = [
        {"name": "mae", "target": "runtime_seconds"},
        {"name": "rmse", "target": "runtime_seconds"},
    ]
    _metrics, _payload, artifacts = run_fixed_baseline(
        rows,
        split={"method": "fixed", "train_fraction": 0.8, "seed": 42},
        metric_defs=metric_defs,
        capture_artifacts=True,
    )
    assert artifacts.y_true is not None
    assert artifacts.y_pred is not None
    assert len(artifacts.y_true) == len(artifacts.y_pred) == 1
    assert artifacts.last_model is not None
