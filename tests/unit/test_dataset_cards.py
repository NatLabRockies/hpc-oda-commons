"""Dataset cards are generated from the repo (#249); these keep them honest."""

from __future__ import annotations

from pathlib import Path

from hpc_oda_commons.benchmark import dataset_cards
from hpc_oda_commons.datasets.descriptor import bundled_descriptor_paths

ROOT = Path(__file__).resolve().parents[2]


def _cards() -> dict[str, str]:
    return dataset_cards.dataset_cards(ROOT / dataset_cards.LEADERBOARD_JSON)


def test_committed_cards_are_what_the_generator_writes() -> None:
    """Change a descriptor, a runtime card, a ceiling, a recipe or the leaderboard without
    running `hpc-oda datasets cards`, and this fails."""
    expected = _cards()
    committed = {
        p.name: p.read_text(encoding="utf-8") for p in (ROOT / dataset_cards.CARDS_DIR).glob("*.md")
    }

    assert sorted(committed) == sorted(expected), "a card is missing or left over"
    stale = [name for name, text in expected.items() if committed[name] != text]
    assert not stale, f"stale dataset cards, regenerate with `hpc-oda datasets cards`: {stale}"


def test_every_bundled_dataset_has_a_card() -> None:
    assert {f"{name}.md" for name in bundled_descriptor_paths()} | {"README.md"} == set(_cards())


def test_a_card_names_its_source_its_windows_and_its_siblings() -> None:
    cards = _cards()
    fdata = cards["fdata_fugaku.md"]
    assert "[10.5281/zenodo.11467483](https://doi.org/10.5281/zenodo.11467483)" in fdata
    # One dataset serves both benchmarks, each reading the window its recipes declare.
    assert "### Job runtime" in fdata and "### Average power per node" in fdata
    assert "2023-11-30 → 2024-04-30" in fdata
    assert "[FRESCO Conte Job Accounting](fresco_conte.md)" in cards["fresco_anvil.md"]
    # A dataset with no runtime card is still carded, and says so.
    assert "Not characterized" in cards["adastra_mi250.md"]


def test_a_dataset_too_large_for_a_node_says_why_it_is_off_the_leaderboard() -> None:
    card = _cards()["ccin2p3_2024.md"]
    assert "isn't on the runtime leaderboard" in card
    assert "more than one node takes" in card
