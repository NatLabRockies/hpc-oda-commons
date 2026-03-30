from __future__ import annotations

from pathlib import Path

import pytest

from hpc_oda_commons.benchmark.recipes import load_recipe, validate_recipe
from hpc_oda_commons.kernel.validate import SchemaValidationError


def _valid_recipe() -> dict:
    return {
        "recipe_id": "recipe.job_runtime.baseline_tiny",
        "problem_domain": ["job-runtime-prediction"],
        "schema_version": "oda.job.v0.1.0",
        "dataset": {
            "id": "hpc_oda_commons/datasets/synthetic/job-runtime/tiny",
            "table_path": "hpc_oda_commons/datasets/synthetic/job-runtime/tiny/data.parquet",
            "manifest_path": "hpc_oda_commons/datasets/synthetic/job-runtime/tiny/manifest.json",
        },
        "model": {"id": "model.job_runtime_baseline", "version": "0.1.0"},
        "metrics": [
            {"name": "mae", "target": "runtime_seconds"},
            {"name": "rmse", "target": "runtime_seconds"},
        ],
        "split": {"method": "fixed", "train_fraction": 0.8, "seed": 42},
        "run": {"output_dir": "runs", "overwrite": False},
    }


def _valid_rolling_recipe() -> dict:
    payload = _valid_recipe()
    payload["model"] = {"id": "model.job_runtime_xgboost", "version": "0.1.0"}
    payload["split"] = {"method": "rolling", "n_windows": 24}
    return payload


def test_validate_recipe_ok() -> None:
    validate_recipe(_valid_recipe())


def test_validate_recipe_rolling_ok() -> None:
    validate_recipe(_valid_rolling_recipe())


def test_validate_recipe_rolling_with_optional_lookback_ok() -> None:
    payload = _valid_rolling_recipe()
    payload["split"]["training_lookback_days"] = 30
    validate_recipe(payload)


def test_validate_recipe_rolling_requires_n_windows() -> None:
    payload = _valid_rolling_recipe()
    payload["split"] = {"method": "rolling"}
    with pytest.raises(SchemaValidationError):
        validate_recipe(payload)


def test_validate_recipe_rolling_invalid_lookback_days() -> None:
    payload = _valid_rolling_recipe()
    payload["split"]["training_lookback_days"] = 0
    with pytest.raises(SchemaValidationError, match="training_lookback_days"):
        validate_recipe(payload)


def test_validate_recipe_missing_required_metric() -> None:
    payload = _valid_recipe()
    payload["metrics"] = [{"name": "mae", "target": "runtime_seconds"}]
    with pytest.raises(SchemaValidationError):
        validate_recipe(payload)


def test_validate_recipe_metric_targets_must_match() -> None:
    payload = _valid_recipe()
    payload["metrics"][1]["target"] = "other"
    with pytest.raises(SchemaValidationError):
        validate_recipe(payload)


def test_load_recipe_from_file(tmp_path: Path) -> None:
    recipe_path = tmp_path / "recipe.yml"
    recipe_path.write_text(
        "\n".join(
            [
                "recipe_id: recipe.job_runtime.baseline_tiny",
                "problem_domain:",
                "  - job-runtime-prediction",
                "schema_version: oda.job.v0.1.0",
                "dataset:",
                "  id: hpc_oda_commons/datasets/synthetic/job-runtime/tiny",
                "  table_path: hpc_oda_commons/datasets/synthetic/job-runtime/tiny/data.parquet",
                "model:",
                "  id: model.job_runtime_baseline",
                '  version: "0.1.0"',
                "metrics:",
                "  - name: mae",
                "    target: runtime_seconds",
                "  - name: rmse",
                "    target: runtime_seconds",
            ]
        ),
        encoding="utf-8",
    )
    load_recipe(recipe_path, validate=True)
