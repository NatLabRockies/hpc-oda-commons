"""Rich console rendering for leaderboard summaries."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table

from hpc_oda_commons.benchmark.leaderboard_display import (
    format_headroom,
    format_metric_value,
    short_registry_id,
)


def _cell_text(table: dict[str, Any], cell: dict[str, Any] | None) -> str:
    if cell is None:
        return "-"
    mae = format_metric_value("mae", float(cell["mae"]), target=table["target"])
    if cell.get("headroom") is None:
        return mae
    return f"{format_headroom(cell['headroom'])} ({mae})"


def render_leaderboard_console(
    leaderboard: dict[str, Any],
    *,
    console: Console | None = None,
) -> None:
    """One table per target: a row per model, the average, a column per dataset (#237)."""
    console = console or Console()
    tables = [t for t in leaderboard.get("tables", []) if t["rows"]]
    if not tables:
        console.print("[yellow]No benchmark cells found in the runs directory.[/yellow]")
    for data in tables:
        table = Table(title=data["title"], header_style="bold", pad_edge=False)
        table.add_column("#", style="dim", justify="right")
        table.add_column("Model", style="magenta", no_wrap=True)
        if data["headroom"]:
            table.add_column("Average", justify="right")
        for dataset in data["datasets"]:
            table.add_column(dataset, justify="right")
        rank = 0
        for row in data["rows"]:
            cells = [_cell_text(data, row["cells"].get(d)) for d in data["datasets"]]
            label = short_registry_id(str(row["model"]), prefix="model.")
            if row["average"] is not None:
                rank += 1
                head = [str(rank), label, f"[bold]{format_headroom(row['average'])}[/bold]"]
            elif data["headroom"]:
                head = ["", label, f"{row['datasets_run']}/{len(data['roster'])}"]
            else:
                head = ["", label]
            table.add_row(*head, *cells)
        console.print(table)
        if data.get("note"):
            console.print(f"[dim]{data['note']}[/dim]")
    excluded = leaderboard.get("excluded", [])
    if excluded:
        console.print(f"[dim]{len(excluded)} run(s) not counted; see runs.html for why.[/dim]")
