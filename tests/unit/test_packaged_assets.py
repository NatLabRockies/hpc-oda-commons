from __future__ import annotations

import importlib.resources as ir

import pyarrow.parquet as pq

from hpc_oda_commons.kernel.schemas import load_schema


def test_packaged_schemas_load() -> None:
    for schema_id in (
        "oda.job.v0.1.0",
        "oda.job.v0.2.0",
        "oda.result.v0.1.0",
        "oda.registry.v0.1.0",
        "oda.recipe.v0.1.0",
        "oda.mdl.v0.1.0",
        "oda.mapping.v0.1.0",
    ):
        assert load_schema(schema_id)


def test_packaged_registry_sources_exist() -> None:
    """The registry is built from these at run time (#249), so they must ship."""
    base = ir.files("hpc_oda_commons")
    assert (base / "models" / "baseline" / "model.yml").is_file()
    assert (base / "adapters" / "slurmctld" / "adapter.yml").is_file()


def test_packaged_recipe_and_dataset_assets_exist() -> None:
    base = ir.files("hpc_oda_commons")
    baseline_recipe = base / "recipes" / "job-runtime" / "baseline_tiny.yml"
    xgb_recipe = base / "recipes" / "job-runtime" / "xgb_hourly_recent.yml"
    manifest = base / "datasets" / "synthetic" / "job-runtime" / "tiny" / "manifest.json"
    parquet = base / "datasets" / "synthetic" / "job-runtime" / "tiny" / "data.parquet"

    assert baseline_recipe.is_file()
    assert xgb_recipe.is_file()
    assert manifest.is_file()
    assert parquet.is_file()


def test_packaged_tiny_dataset_is_rolling_compatible() -> None:
    base = ir.files("hpc_oda_commons")
    parquet = base / "datasets" / "synthetic" / "job-runtime" / "tiny" / "data.parquet"
    table = pq.read_table(parquet)

    assert "submit_time" in table.column_names

    submit_values = [v for v in table.column("submit_time").to_pylist() if v not in (None, "")]
    assert submit_values

    hour_bins = {str(v)[:13] for v in submit_values}
    assert len(hour_bins) >= 3
