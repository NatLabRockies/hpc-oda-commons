"""``hpc-oda models``: commands about the registered models."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from hpc_oda_commons.benchmark.model_cards import CARDS_DIR, LEADERBOARD_JSON, write_model_cards

console = Console()
models_app = typer.Typer(help="Commands about the registered models.", no_args_is_help=True)


@models_app.command("cards")
def models_cards(
    out: Annotated[
        Path, typer.Option("--out", help="Directory to write the model cards into.")
    ] = CARDS_DIR,
    leaderboard: Annotated[
        Path,
        typer.Option(
            "--leaderboard",
            exists=True,
            readable=True,
            help="The leaderboard JSON the cards' results come from.",
        ),
    ] = LEADERBOARD_JSON,
) -> None:
    """Write a card for every registered model, generated from the code (#247).

    Each card comes from the registry, the benchmark runners, the bundled recipes and the
    leaderboard, so regenerate the cards whenever one of those changes; a unit test fails
    when the committed cards differ from what this writes.
    """
    for path in write_model_cards(out, leaderboard):
        console.print(f"[green]wrote[/green] {path}")
