from __future__ import annotations

import importlib.resources as ir

from hpc_oda_commons.kernel.schemas import load_schema
from hpc_oda_commons.registry.snapshot import snapshot_resource_path


def test_packaged_schemas_load() -> None:
    for schema_id in (
        "oda.job.v0.1.0",
        "oda.result.v0.1.0",
        "oda.registry.v0.1.0",
        "oda.recipe.v0.1.0",
        "oda.mdl.v0.1.0",
        "oda.mapping.v0.1.0",
    ):
        assert load_schema(schema_id)


def test_packaged_registry_snapshot_exists() -> None:
    path = snapshot_resource_path()
    assert path.exists()


def test_packaged_recipe_and_dataset_assets_exist() -> None:
    base = ir.files("hpc_oda_commons")
    recipe = base / "recipes" / "job-runtime" / "baseline_tiny.yml"
    manifest = base / "datasets" / "synthetic" / "job-runtime" / "tiny" / "manifest.json"
    parquet = base / "datasets" / "synthetic" / "job-runtime" / "tiny" / "data.parquet"

    assert recipe.is_file()
    assert manifest.is_file()
    assert parquet.is_file()
