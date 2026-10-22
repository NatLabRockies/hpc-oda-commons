"""A recipe names its dataset one way: the short name bundles and cards use (#259)."""

from __future__ import annotations

from pathlib import Path

import yaml

from hpc_oda_commons.benchmark.recipes import load_recipe
from hpc_oda_commons.datasets.ids import dataset_name


def test_registry_and_old_ids_give_the_short_name() -> None:
    assert dataset_name("lassen") == "lassen"
    assert dataset_name("dataset.lassen") == "lassen"
    assert dataset_name("dataset.job_runtime.lassen") == "lassen"
    assert dataset_name("dataset.job_power.pm100") == "pm100"


def test_other_ids_are_left_alone() -> None:
    path = "hpc_oda_commons/datasets/synthetic/job-runtime/tiny"
    assert dataset_name(path) == path
    assert dataset_name("embedded_jobs") == "embedded_jobs"


def test_a_recipe_may_spell_its_dataset_as_a_registry_id(tmp_path: Path) -> None:
    recipe = {
        "recipe_id": "recipe.test",
        "problem_domain": ["job-runtime-prediction"],
        "schema_version": "oda.job.v0.2.0",
        "dataset": {"id": "dataset.lassen", "table_path": "data/datasets/lassen/data.parquet"},
        "model": {"id": "model.baseline", "version": "0.1.0"},
        "metrics": [
            {"name": "mae", "target": "runtime_seconds"},
            {"name": "rmse", "target": "runtime_seconds"},
        ],
    }
    path = tmp_path / "r.yml"
    path.write_text(yaml.safe_dump(recipe))
    assert load_recipe(path)["dataset"]["id"] == "lassen"


def test_every_bundled_recipe_uses_the_short_form() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "hpc_oda_commons" / "recipes"
    for path in sorted(root.rglob("*.yml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("dataset"), dict):
            dataset_id = str(raw["dataset"]["id"])
            assert dataset_name(dataset_id) == dataset_id, path.name
