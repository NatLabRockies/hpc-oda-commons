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


def test_validate_recipe_rolling_accepts_moe_routing_knobs() -> None:
    """A bundled recipe must be able to set the knobs its model documents.

    `split` is `additionalProperties: false`, so every model option a recipe may
    carry has to be declared in the schema — otherwise the recipe fails to load
    with "Additional properties are not allowed" and the option is unreachable.
    """
    payload = _valid_rolling_recipe()
    payload["model"] = {"id": "model.job_runtime_moe_xgboost", "version": "0.1.0"}
    payload["split"] = {
        "method": "rolling",
        "n_windows": 24,
        "time_decay_rate": 0.05,
        "enable_power_users": False,
        "power_user_percentile": 0.99,
        "min_expert_rows": 100,
        "n_wallclock_bins": 5,
        "wallclock_bin_edges_hours": [2, 4, 24, 48],
        "estimator_n_jobs": 1,
    }
    validate_recipe(payload)


def test_validate_recipe_rolling_accepts_log_target() -> None:
    """`split.log_target` has to be declared, or the recipe fails to load.

    `split` is `additionalProperties: false`, so a model option the runners read
    is unreachable from a recipe until the schema names it.
    """
    payload = _valid_rolling_recipe()
    payload["split"] = {"method": "rolling", "n_windows": 24, "log_target": True}
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


def test_validate_recipe_rolling_accepts_objective() -> None:
    """`split.objective` has to be declared, or the recipe fails to load.

    `split` is `additionalProperties: false`; an undeclared model option is
    unreachable from a recipe no matter what the runner does with it (#135).
    """
    payload = _valid_rolling_recipe()
    payload["split"] = {
        "method": "rolling",
        "n_windows": 24,
        "objective": "reg:absoluteerror",
    }
    validate_recipe(payload)


# --- recipe knobs must be reachable, as a class (#134, #172) --------------------------


def test_every_rolling_tabular_split_knob_is_declared_in_the_schema() -> None:
    """`split` is `additionalProperties: false`, so an undeclared knob is unreachable.

    This has bitten twice by enumeration: the MoE knobs in #134 were rejected at recipe load,
    and the target encoding in #172 shipped with the runner silently ignoring it -- an A/B
    measured a 0.0% difference, to the decimal, before anyone noticed.

    So this derives the list from the runner instead of restating it. A new knob that the
    runner reads but the schema does not name fails here, without anyone remembering to add
    a case.
    """
    import json
    from pathlib import Path

    from hpc_oda_commons.benchmark.runner import _rolling_tabular_split_kwargs
    from hpc_oda_commons.models.job_runtime_xgboost.model import JobRuntimeXGBoostConfig

    knobs = set(_rolling_tabular_split_kwargs({}, JobRuntimeXGBoostConfig()))
    schema = json.loads(
        (Path("src/hpc_oda_commons/schemas/oda/recipe/v0.1.0.json")).read_text(encoding="utf-8")
    )
    declared = set(schema["properties"]["split"]["properties"])

    assert knobs <= declared, f"undeclared in the recipe schema: {sorted(knobs - declared)}"


def test_a_recipe_can_actually_set_the_target_encoding_knobs() -> None:
    """Declared in the schema AND read by the runner -- both halves, or it does nothing."""
    from hpc_oda_commons.benchmark.runner import _rolling_tabular_split_kwargs
    from hpc_oda_commons.models.job_runtime_xgboost.model import JobRuntimeXGBoostConfig

    payload = _valid_rolling_recipe()
    payload["split"] = {
        "method": "rolling",
        "n_windows": 24,
        "target_encode_min_cardinality": 64,
        "target_encode_smoothing": 5.0,
    }
    validate_recipe(payload)  # half one: the schema accepts it

    kwargs = _rolling_tabular_split_kwargs(payload["split"], JobRuntimeXGBoostConfig())

    # half two: the runner carries it into the model's config
    assert kwargs["target_encode_min_cardinality"] == 64
    assert kwargs["target_encode_smoothing"] == 5.0
