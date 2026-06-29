"""Rich console rendering for leaderboard summaries."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table

from hpc_oda_commons.benchmark.leaderboard_display import (
    metric_column_label,
    prepare_leaderboard_rows,
)


def render_leaderboard_console(
    leaderboard: dict[str, Any],
    *,
    console: Console | None = None,
) -> None:
    console = console or Console()
    entries = leaderboard.get("entries", [])
    rows, metric_names, _bests = prepare_leaderboard_rows(entries)

    if not rows:
        console.print("[yellow]No benchmark runs found in the runs directory.[/yellow]")
        return

    table = Table(
        title="hpc-oda leaderboard",
        header_style="bold",
        show_lines=False,
        pad_edge=False,
    )
    table.add_column("Run", style="dim", no_wrap=True, max_width=11)
    table.add_column("Recipe", style="cyan", no_wrap=True)
    table.add_column("Model", style="magenta", no_wrap=True)
    table.add_column("Target", style="green", no_wrap=True)
    table.add_column("Dataset", style="blue", overflow="ellipsis", max_width=24)

    for name in metric_names:
        table.add_column(metric_column_label(name, target=None), justify="right", no_wrap=True)

    table.add_column("Train", justify="right", no_wrap=True)

    for row in rows:
        metric_cells = []
        for name in metric_names:
            metric = row["metrics"].get(name)
            if metric is None:
                metric_cells.append("-")
                continue
            text = str(metric["display"])
            if metric.get("is_best"):
                text = f"[bold green]{text}[/bold green]"
            metric_cells.append(text)

        table.add_row(
            row["created_at"],
            row["recipe_short"],
            f"{row['model_short']} v{row['model_version']}",
            row["target_label"],
            row["dataset_label"],
            *metric_cells,
            row["training_time"],
        )

    console.print(table)
