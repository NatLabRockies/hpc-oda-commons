"""CLI: ``hpc-oda bench-matrix`` — plan the full model x dataset benchmark for a cluster.

``plan`` reads the tracked dataset cards plus a *local, gitignored* site config and writes
per-cell Slurm recipes + sbatch scripts under ``.hpc_oda/bench-matrix/<plan_id>/``. The
site config supplies every cluster/user-specific value, so nothing site-specific is
generated into the tracked repo. Staging (rsync), submission, and result aggregation are
separate steps (see docs/benchmarking/hpc-runner.md).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from hpc_oda_commons.benchmarking.hpc.config import (
    DEFAULT_SITE_CONFIG_PATH,
    SiteConfigError,
    load_site_config,
)
from hpc_oda_commons.benchmarking.hpc.matrix import (
    RUNTIME_MODELS,
    build_plan,
    load_cards,
    tier_for_rows,
    write_plan,
)
from hpc_oda_commons.benchmarking.hpc.slice import SliceError, slice_dataset

console = Console()


def bench_matrix_plan(
    cards_dir: Annotated[
        Path,
        typer.Option("--cards-dir", exists=True, help="Directory of *.card.json dataset cards."),
    ] = Path("docs/benchmarking/datasets"),
    site: Annotated[
        Path,
        typer.Option("--site", help="Local (gitignored) HPC site config."),
    ] = DEFAULT_SITE_CONFIG_PATH,
    out: Annotated[
        Path,
        typer.Option("--out", help="Staging root for generated recipes/scripts."),
    ] = Path(".hpc_oda/bench-matrix"),
    plan_id: Annotated[
        str | None,
        typer.Option("--plan-id", help="Plan id (default: timestamp). Names the staging subdir."),
    ] = None,
    include_unhealthy: Annotated[
        bool,
        typer.Option(
            "--include-unhealthy", help="Include datasets whose window is flagged unhealthy."
        ),
    ] = False,
) -> None:
    """Generate the benchmark-matrix plan (recipes + sbatch scripts + plan.json)."""
    try:
        cfg = load_site_config(site)
    except SiteConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    cards = load_cards(cards_dir)
    pid = plan_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    plan = build_plan(cards, cfg, plan_id=pid, include_unhealthy=include_unhealthy)

    staging_dir = out / pid
    plan_path = write_plan(plan, staging_dir, cfg)

    # --- summary ---
    table = Table(title=f"Benchmark matrix — plan {pid}")
    table.add_column("dataset")
    table.add_column("window rows", justify="right")
    table.add_column("tier")
    table.add_column("partition")
    table.add_column("models", justify="right")
    by_dataset: dict[str, int] = {}
    for cell in plan.cells:
        by_dataset[cell.dataset] = by_dataset.get(cell.dataset, 0) + 1
    card_by_name = {c.dataset: c for c in cards}
    for dataset in sorted(by_dataset):
        card = card_by_name[dataset]
        tier = tier_for_rows(card.window_rows)
        table.add_row(
            dataset,
            f"{card.window_rows:,}",
            tier.name,
            _partition_for(plan, dataset),
            str(by_dataset[dataset]),
        )
    console.print(table)

    n_datasets = len(by_dataset)
    console.print(
        f"[green]Planned[/green] {len(plan.cells)} benchmark cells "
        f"({n_datasets} datasets x {len(RUNTIME_MODELS)} models) "
        f"+ {len(plan.embeds)} embedding jobs."
    )
    if plan.skipped:
        names = ", ".join(s["dataset"] for s in plan.skipped)
        console.print(f"[yellow]Skipped {len(plan.skipped)}[/yellow] (unhealthy window): {names}")
        console.print("  Re-run with [cyan]--include-unhealthy[/cyan] to include them.")
    console.print(f"Staging dir: [cyan]{staging_dir}[/cyan]")
    console.print(f"Plan manifest: [cyan]{plan_path}[/cyan]")


def _partition_for(plan, dataset: str) -> str:
    for cell in plan.cells:
        if cell.dataset == dataset:
            return cell.partition
    return "?"


def bench_matrix_slice(
    cards_dir: Annotated[
        Path,
        typer.Option("--cards-dir", exists=True, help="Directory of *.card.json dataset cards."),
    ] = Path("docs/benchmarking/datasets"),
    out: Annotated[
        Path,
        typer.Option(
            "--out", help="Local staging dir for windowed parquets (rsync to repo/data/windows)."
        ),
    ] = Path(".hpc_oda/bench-matrix/data/windows"),
    dataset: Annotated[
        str | None,
        typer.Option("--dataset", help="Slice only this dataset (default: all healthy datasets)."),
    ] = None,
    include_unhealthy: Annotated[
        bool,
        typer.Option("--include-unhealthy", help="Also slice datasets whose window is unhealthy."),
    ] = False,
) -> None:
    """Slice each dataset's canonical parquet to its 90-day benchmark window.

    Reads the canonical parquet named on each card and writes
    ``<out>/<dataset>/data.parquet``. That tree rsyncs to ``<repo>/data/windows`` on the
    cluster, where the generated recipes read it. Overlapping (long-running) jobs are kept
    so the earliest rolling windows keep their training rows — see the slice module.
    """
    cards = load_cards(cards_dir)
    table = Table(title="Slice to benchmark window")
    table.add_column("dataset")
    table.add_column("rows", justify="right")
    table.add_column("status")

    sliced = 0
    for card in cards:
        if dataset and card.dataset != dataset:
            continue
        if not card.healthy and not include_unhealthy:
            table.add_row(card.dataset, "-", "[yellow]skip (unhealthy)[/yellow]")
            continue
        source = Path(card.source_table)
        if not source.exists():
            table.add_row(card.dataset, "-", f"[red]missing source {source}[/red]")
            continue
        dest = out / card.dataset / "data.parquet"
        try:
            n = slice_dataset(source, dest, card.window_start, card.window_end)
        except SliceError as exc:
            table.add_row(card.dataset, "-", f"[red]{exc}[/red]")
            continue
        sliced += 1
        table.add_row(card.dataset, f"{n:,}", "[green]ok[/green]")

    console.print(table)
    console.print(f"[green]Sliced[/green] {sliced} datasets → [cyan]{out}[/cyan]")
