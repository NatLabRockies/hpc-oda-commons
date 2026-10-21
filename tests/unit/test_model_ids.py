"""Model ids name the model, not a task (#249); ids from before then still resolve."""

from __future__ import annotations

from pathlib import Path

from hpc_oda_commons.benchmark.recipes import load_recipe
from hpc_oda_commons.benchmark.runner import RUNNERS
from hpc_oda_commons.models.ids import LEGACY_MODEL_IDS, canonical_model_id
from hpc_oda_commons.registry.snapshot import load_registry_index


def _registered_models() -> set[str]:
    return {e.id for e in load_registry_index().entries if e.entry_type == "model"}


def test_every_old_id_maps_to_a_model_that_runs() -> None:
    runnable = {model_id for model_id, _method in RUNNERS}
    for new in LEGACY_MODEL_IDS.values():
        assert new in runnable
        assert new in _registered_models()


def test_no_model_id_names_a_task() -> None:
    for model_id in _registered_models() | {model_id for model_id, _method in RUNNERS}:
        assert "job_runtime" not in model_id and "job_power" not in model_id, model_id


def test_a_current_or_unknown_id_is_kept() -> None:
    assert canonical_model_id("model.xgboost") == "model.xgboost"
    assert canonical_model_id("model.someone_elses") == "model.someone_elses"


def test_a_recipe_with_an_old_id_loads_with_the_new_one(tmp_path: Path) -> None:
    bundled = Path("src/hpc_oda_commons/recipes/job-power/xgboost_rolling_avg_pm100.yml")
    text = bundled.read_text(encoding="utf-8")
    assert "id: model.xgboost" in text
    recipe = tmp_path / "recipe.yml"
    recipe.write_text(text.replace("id: model.xgboost", "id: model.job_runtime_xgboost"))

    assert load_recipe(recipe)["model"]["id"] == "model.xgboost"
