from __future__ import annotations

import importlib.resources as ir
from pathlib import Path

import pyarrow.parquet as pq

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


def test_packaged_recipes_match_canonical_recipe_tree() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    canonical_root = repo_root / "recipes"
    packaged_root = repo_root / "src/hpc_oda_commons" / "recipes"
    suffixes = {".yml", ".yaml", ".toml"}

    canonical = {
        path.relative_to(canonical_root).as_posix(): path.read_bytes()
        for path in sorted(canonical_root.rglob("*"))
        if path.is_file() and path.suffix.lower() in suffixes
    }
    packaged = {
        path.relative_to(packaged_root).as_posix(): path.read_bytes()
        for path in sorted(packaged_root.rglob("*"))
        if path.is_file() and path.suffix.lower() in suffixes
    }

    assert packaged == canonical
