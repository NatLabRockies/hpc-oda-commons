"""
Implements  for adapters/models/recipes metadata display.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from hpc_oda_commons.registry.index import RegistryIndex
from hpc_oda_commons.registry.snapshot import load_registry_snapshot

console = Console()


def info(
    entry_id: str = typer.Argument(
        ..., help="Registry entry ID (e.g., model.job_runtime_baseline)."
    ),
    snapshot: Annotated[
        Path | None,
        typer.Option(
            "--snapshot", exists=True, readable=True, help="Path to registry snapshot JSON."
        ),
    ] = None,
) -> None:
    snapshot_obj = load_registry_snapshot(snapshot)
    index = RegistryIndex.from_entries(snapshot_obj.entries)
    entry = index.get(entry_id)
    if entry is None:
        raise typer.BadParameter(f"Registry entry not found: {entry_id}")

    table = Table(title=f"Registry Info: {entry.id}", show_header=False)
    table.add_column("Field", style="bold cyan")
    table.add_column("Value", style="white", overflow="fold")

    table.add_row("Name", entry.name)
    table.add_row("Type", entry.entry_type)
    table.add_row("Version", entry.version)
    table.add_row("Description", entry.description)
    table.add_row("Problem Domain", ", ".join(entry.problem_domain))
    table.add_row("Supported Sources", ", ".join(entry.supported_sources) or "-")
    table.add_row("Input Schema", entry.input_schema_version or "-")
    table.add_row("Output Schema", entry.output_schema_version or "-")
    table.add_row("License", entry.license or "-")
    table.add_row("Tags", ", ".join(entry.tags) or "-")

    if entry.reference:
        if entry.reference.kind == "python":
            ref_value = f"{entry.reference.module}:{entry.reference.object}"
        else:
            ref_value = entry.reference.path or "-"
        table.add_row("Reference", ref_value)
    else:
        table.add_row("Reference", "-")

    console.print(table)
