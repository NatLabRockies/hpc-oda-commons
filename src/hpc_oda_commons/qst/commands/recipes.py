"""``hpc-oda recipes``: write the benchmark's recipes for a dataset of your own (#255)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

console = Console()
recipes_app = typer.Typer(
    help="Write the benchmark's recipes for a dataset of your own.", no_args_is_help=True
)


@recipes_app.command("write")
def recipes_write(
    descriptor: Annotated[
        Path,
        typer.Argument(exists=True, readable=True, help="The dataset's descriptor (.yml)."),
    ],
    out: Annotated[Path, typer.Option("--out", help="Folder to write the recipes into.")],
    card: Annotated[
        Path | None,
        typer.Option(
            "--card",
            exists=True,
            readable=True,
            help="The dataset's runtime card (from `datasets characterize`). Without it, no "
            "runtime recipes are written.",
        ),
    ] = None,
    start: Annotated[
        str | None, typer.Option("--start", help="Power window: its first day, YYYY-MM-DD.")
    ] = None,
    end: Annotated[
        str | None, typer.Option("--end", help="Power window: its last day, YYYY-MM-DD.")
    ] = None,
    by: Annotated[
        str,
        typer.Option("--by", help="Power window: keep overlapping jobs, or those submitted in it."),
    ] = "overlap",
    require_nonnull: Annotated[
        list[str] | None,
        typer.Option(
            "--require-nonnull", help="Power: read only rows with this column (repeatable)."
        ),
    ] = None,
    runs_dir: Annotated[
        str, typer.Option("--runs-dir", help="Where the runs write their result bundles.")
    ] = "runs",
    model: Annotated[
        list[str] | None,
        typer.Option("--model", help="Write only this model's recipes (repeatable)."),
    ] = None,
) -> None:
    """Write every model's recipes for a dataset, on the benchmark's own protocol.

    Runtime recipes need the dataset's runtime card, which sets their window; power recipes
    are written for each per-node power target the descriptor maps, over the whole table or
    the window you give. Runs from these recipes count on `hpc-oda leaderboard --recipes`.
    """
    from hpc_oda_commons.benchmark.recipe_writer import write_recipes
    from hpc_oda_commons.benchmarking.hpc.matrix import load_card
    from hpc_oda_commons.datasets.descriptor import load_descriptor

    if (start is None) != (end is None):
        raise typer.BadParameter("give both --start and --end, or neither")
    window = None
    if start is not None:
        window = {"start": start, "end": str(end)}
        if by != "overlap":
            window["by"] = by
    written = write_recipes(
        load_descriptor(descriptor),
        out,
        card=load_card(card) if card else None,
        window=window,
        require_nonnull=require_nonnull or (),
        runs_dir=runs_dir,
        models=model or (),
        benchmark_dir=(card.parent.as_posix() if card else "benchmark/datasets"),
    )
    console.print(f"[green]wrote[/green] {len(written.recipes)} recipes under {out}")
    for note in written.skipped:
        console.print(f"[yellow]skipped[/yellow] {note}")
    if written.steps:
        console.print("Before running the embedding models, build their embedded tables:")
        for step in written.steps:
            console.print(f"  {step}", soft_wrap=True)
    if written.ceilings:
        console.print("The error ceilings headroom is measured against:")
        for step in written.ceilings:
            console.print(f"  {step}", soft_wrap=True)
