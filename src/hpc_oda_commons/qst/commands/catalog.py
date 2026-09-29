"""CLI: ``hpc-oda catalog export``."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from hpc_oda_commons.catalog.export import CatalogExportError, export_catalog

console = Console()


def catalog_export(
    out: Annotated[Path, typer.Option("--out", "-o", help="Output directory.")] = Path("catalog"),
    dataset: Annotated[
        list[str] | None,
        typer.Option("--dataset", "-d", help="Only this dataset id (repeatable)."),
    ] = None,
) -> None:
    """Export registered datasets as Croissant 1.0 catalog records (no network)."""
    try:
        written = export_catalog(out, dataset_ids=dataset)
    except CatalogExportError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(f"Exported {len(written)} Croissant record(s) to {out.as_posix()}/")
