"""
Implements  (Find pillar via registry snapshot).
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from hpc_oda_commons.registry.index import RegistryIndex
from hpc_oda_commons.registry.snapshot import load_registry_snapshot

console = Console(width=120)


def browse(
    tag: str | None = typer.Option(None, "--tag", help="Filter by tag or problem domain."),
    entry_type: str | None = typer.Option(
        None, "--type", help="Filter by entry type (adapter, model, recipe)."
    ),
    source: str | None = typer.Option(None, "--source", help="Filter by supported source."),
    input_schema: str | None = typer.Option(
        None, "--input-schema", help="Filter by input schema version."
    ),
    output_schema: str | None = typer.Option(
        None, "--output-schema", help="Filter by output schema version."
    ),
    snapshot: Path | None = typer.Option(
        None, "--snapshot", exists=True, readable=True, help="Path to registry snapshot JSON."
    ),
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
