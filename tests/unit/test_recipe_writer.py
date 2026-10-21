"""`hpc-oda recipes write` writes a dataset's recipes on the benchmark's protocol (#255)."""

from __future__ import annotations

import importlib.resources as ir
import json
import shutil
from pathlib import Path

import yaml

from hpc_oda_commons.benchmark.dataset_cards import dataset_cards
from hpc_oda_commons.benchmark.recipe_writer import EMBEDDING_MODELS, write_recipes
from hpc_oda_commons.benchmark.results import build_leaderboard
from hpc_oda_commons.benchmark.tracks import RUNTIME_LOOKBACKS, RUNTIME_PROTOCOL
from hpc_oda_commons.benchmarking.hpc.matrix import (
    RUNTIME_MODELS,
    load_card,
    slice_extension_for,
)
from hpc_oda_commons.benchmarking.hpc.slice import effective_start
from hpc_oda_commons.datasets.descriptor import load_descriptor
from tests.unit.test_leaderboard_tracks import _bundle, _ceiling

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = Path(str(ir.files("hpc_oda_commons")))
EXAMPLE = ROOT / "docs" / "how-to" / "benchmark-your-data" / "example_cluster.yml"
PM100 = PACKAGE / "datasets" / "descriptors" / "pm100.yml"
PM100_CARD = ROOT / "docs" / "benchmarking" / "datasets" / "pm100.card.json"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_the_embedding_models_are_those_the_bundled_recipes_embed_for() -> None:
    root = PACKAGE / "recipes" / "job-power"
    embedded = {
        _load(p)["model"]["id"]
        for p in root.glob("*_rolling_avg_eagle.yml")
        if "_embedded/" in _load(p)["dataset"]["table_path"]
    }
    assert embedded == EMBEDDING_MODELS


def test_power_recipes_are_the_bundled_protocol(tmp_path: Path) -> None:
    """Written for PM100, they match its bundled recipes in all but where they read and
    write: the split the leaderboard checks a run against is the same."""
    written = write_recipes(load_descriptor(PM100), tmp_path)
    power = sorted((tmp_path / "power").glob("*.yml"))
    assert len(power) == 16
    bundled = PACKAGE / "recipes" / "job-power"
    for path in power:
        mine = _load(path)
        theirs = _load(bundled / (mine["recipe_id"].removeprefix("recipe.job_power.") + ".yml"))
        for key in ("recipe_id", "problem_domain", "schema_version", "model", "metrics", "split"):
            assert mine[key] == theirs[key], (path.name, key)
        embedded = mine["model"]["id"] in EMBEDDING_MODELS
        assert ("embeddings" in mine["dataset"]["table_path"]) == embedded
    assert written.skipped == ["runtime: no runtime card (run `hpc-oda datasets characterize`)"]


def test_runtime_recipes_follow_the_leaderboard_protocol(tmp_path: Path) -> None:
    card = load_card(PM100_CARD)
    write_recipes(load_descriptor(PM100), tmp_path, card=card, models=())
    recipes = [_load(p) for p in sorted((tmp_path / "runtime").glob("*.yml"))]
    assert {r["model"]["id"] for r in recipes} == {f"model.{m}" for m in RUNTIME_MODELS}
    assert len(recipes) == len(RUNTIME_MODELS) * len(RUNTIME_LOOKBACKS)
    window = {
        "start": effective_start(card.window_start, slice_extension_for(card)),
        "end": card.window_end,
    }
    for recipe in recipes:
        split = recipe["split"]
        assert split["n_windows"] == RUNTIME_PROTOCOL["n_windows"]
        assert split["test_window_hours"] == RUNTIME_PROTOCOL["test_window_hours"]
        assert split["training_lookback_days"] in RUNTIME_LOOKBACKS
        assert recipe["dataset"]["window"] == window


def test_models_can_be_limited_and_ceilings_are_given(tmp_path: Path) -> None:
    written = write_recipes(
        load_descriptor(PM100),
        tmp_path,
        card=load_card(PM100_CARD),
        models=["baseline", "model.uopc"],
    )
    names = sorted(p.name for p in written.recipes)
    assert names == [
        "baseline_avg.yml",
        "baseline_lb10d.yml",
        "baseline_lb120d.yml",
        "baseline_lb30d.yml",
        "baseline_peak.yml",
        "uopc_avg.yml",
        "uopc_peak.yml",
    ]
    assert [c.split()[3] for c in written.ceilings][:1] == ["data/datasets/pm100/data.parquet"]
    assert any("--target maxpcon_per_node" in c for c in written.ceilings)


def test_a_run_from_written_recipes_counts_on_the_leaderboard(tmp_path: Path) -> None:
    """A power recipe that isn't bundled counts once its folder is passed (--recipes)."""
    recipes = tmp_path / "recipes"
    write_recipes(load_descriptor(EXAMPLE), recipes, models=["baseline", "xgboost"])
    runs, ceilings = tmp_path / "runs", tmp_path / "ceilings"
    _ceiling(ceilings, "dataset.example_cluster", "avgpcon_per_node", 10.0)
    for model, mae in (("baseline", 50.0), ("xgboost", 30.0)):
        recipe = _load(recipes / "power" / f"{model}_avg.yml")
        _bundle(runs, recipe_id=recipe["recipe_id"], model=f"model.{model}", mae=mae)

    without = build_leaderboard(runs, ceilings_dir=ceilings, cards_dir=ceilings)
    assert all("not a bundled benchmark recipe" in e["reason"] for e in without["excluded"])

    board = build_leaderboard(
        runs, ceilings_dir=ceilings, cards_dir=ceilings, recipe_dirs=[recipes]
    )
    (table,) = [t for t in board["tables"] if t["target"] == "avgpcon_per_node"]
    assert table["datasets"] == ["example_cluster"]
    xgb = next(r for r in table["rows"] if r["model"] == "model.xgboost")
    assert xgb["cells"]["example_cluster"]["headroom"] == 0.5  # (50 - 30) / (50 - 10)


def test_your_own_dataset_gets_a_card(tmp_path: Path) -> None:
    descriptors = tmp_path / "descriptors"
    descriptors.mkdir()
    shutil.copy(EXAMPLE, descriptors / EXAMPLE.name)
    recipes = tmp_path / "recipes"
    write_recipes(load_descriptor(EXAMPLE), recipes, models=["baseline"])
    board = tmp_path / "leaderboard" / "leaderboard.json"
    board.parent.mkdir()
    board.write_text(json.dumps({"generated_at": "2026-10-21T00:00:00Z", "tables": []}))

    cards = dataset_cards(
        board,
        tmp_path / "benchmark",
        descriptors_dir=descriptors,
        recipe_dirs=[recipes],
        out_dir=tmp_path / "cards",
    )

    assert sorted(cards) == ["README.md", "example_cluster.md"]
    card = cards["example_cluster.md"]
    assert "## Recipes" in card and "Not characterized" in card
    assert "[`example_cluster.yml`](../descriptors/example_cluster.yml)" in card
    assert "(../recipes/power/baseline_avg.yml)" in card
    assert "[leaderboard](../leaderboard/index.html)" in card
