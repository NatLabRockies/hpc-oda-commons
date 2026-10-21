"""Model cards are generated from the code (#247); these keep them honest."""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

from hpc_oda_commons.benchmark import model_cards
from hpc_oda_commons.benchmark.runner import RUNNERS

ROOT = Path(__file__).resolve().parents[2]


def _cards() -> dict[str, str]:
    return model_cards.model_cards(ROOT / model_cards.LEADERBOARD_JSON)


def test_committed_cards_are_what_the_generator_writes() -> None:
    """Change a model, a runner, a recipe, the registry or the leaderboard without running
    `hpc-oda models cards`, and this fails."""
    expected = _cards()
    committed = {
        p.name: p.read_text(encoding="utf-8") for p in (ROOT / "docs" / "models").glob("*.md")
    }

    assert sorted(committed) == sorted(expected), "a card is missing or left over"
    stale = [name for name, text in expected.items() if committed[name] != text]
    assert not stale, f"stale model cards, regenerate with `hpc-oda models cards`: {stale}"


def test_each_runner_builds_the_config_its_entry_names() -> None:
    """RUNNERS is the one record the cards' settings come from, so it must match the code."""
    for key, spec in RUNNERS.items():
        tree = ast.parse(inspect.getsource(spec.run))
        # Every config class the runner refers to: the one it builds, or whose defaults it
        # uses (run_fixed_uopc builds the model with its default config).
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        configs = {name for name in names if name.endswith("Config")}
        assert configs == ({spec.config.__name__} if spec.config else set()), key
        assert spec.config is None or dataclasses.is_dataclass(spec.config), key


def test_split_keys_follow_helpers_and_resolve_defaults() -> None:
    xgb = RUNNERS[("model.xgboost", "rolling")]
    keys = dict(model_cards._split_keys(xgb.run, xgb.config))
    # Read through the shared rolling helper, with the config's defaults.
    assert keys["training_lookback_days"] == "`100`"
    assert keys["objective"] == "`reg:squarederror`"
    cutoff = dict(model_cards._split_keys(RUNNERS[("model.uopc", "cutoff")].run, None))
    assert cutoff["test_start"] == "required"  # split["test_start"]
    assert cutoff["max_alloc_ratio"] == "`None`"  # split.get with no default is optional
    assert cutoff["predictor"] == "`median`"  # a module constant, resolved
    fixed = RUNNERS[("model.uopc", "fixed")]
    # Read inside the model's evaluate_fixed, which the runner hands split to.
    assert dict(model_cards._split_keys(fixed.run, fixed.config)) == {"train_fraction": "`0.8`"}


def test_cards_say_where_and_how_each_model_runs() -> None:
    from hpc_oda_commons.benchmarking.hpc.matrix import RUNTIME_MODELS

    cards = _cards()
    for model in RUNTIME_MODELS:
        assert "in the runtime fleet" in cards[f"{model}.md"], model
    assert "in the runtime fleet" not in cards["uopc.md"]
    assert "It does not use the shared submit-time allowlist." in cards["baseline.md"]
    assert "shared submit-time allowlist ([" in cards["xgboost.md"]
