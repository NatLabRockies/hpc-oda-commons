"""
Implements  (Find pillar via registry snapshot).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from hpc_oda_commons.registry.index import RegistryIndex
from hpc_oda_commons.registry.snapshot import load_registry_snapshot

console = Console(width=120)


def browse(
    tag: Annotated[
        str | None, typer.Option("--tag", help="Filter by tag or problem domain.")
    ] = None,
    entry_type: Annotated[
        str | None, typer.Option("--type", help="Filter by entry type (adapter, model, recipe).")
    ] = None,
    source: Annotated[
        str | None, typer.Option("--source", help="Filter by supported source.")
    ] = None,
    input_schema: Annotated[
        str | None, typer.Option("--input-schema", help="Filter by input schema version.")
    ] = None,
    output_schema: Annotated[
        str | None, typer.Option("--output-schema", help="Filter by output schema version.")
    ] = None,
    snapshot: Annotated[
        Path | None,
        typer.Option(
            "--snapshot", exists=True, readable=True, help="Path to registry snapshot JSON."
        ),
    ] = None,
) -> None:
    if entry_type and entry_type not in {"adapter", "model", "recipe"}:
        raise typer.BadParameter("type must be one of: adapter, model, recipe")

    snapshot_obj = load_registry_snapshot(snapshot)
    index = RegistryIndex.from_entries(snapshot_obj.entries)
    entries = index.filter(
        tag=tag,
        entry_type=entry_type,
        source=source,
        input_schema=input_schema,
        output_schema=output_schema,
    )

    if not entries:
        console.print("[yellow]No registry entries matched your filters.[/yellow]")
        return

    table = Table(title="hpc-oda registry", header_style="bold")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Type", style="magenta")
    table.add_column("Name", style="white")
    table.add_column("Schemas", style="green")
    table.add_column("Sources", style="blue")

    for entry in sorted(entries, key=lambda e: e.id):
        schemas = []
        if entry.input_schema_version:
            schemas.append(f"in:{entry.input_schema_version}")
        if entry.output_schema_version:
            schemas.append(f"out:{entry.output_schema_version}")
        schema_text = ", ".join(schemas) if schemas else "-"
        sources = ", ".join(entry.supported_sources) if entry.supported_sources else "-"
        table.add_row(entry.id, entry.entry_type, entry.name, schema_text, sources)

    console.print(table)
