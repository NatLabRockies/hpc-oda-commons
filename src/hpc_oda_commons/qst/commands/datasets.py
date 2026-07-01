"""CLI: ``hpc-oda datasets`` — fetch public operational datasets into the cache."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from hpc_oda_commons.datasets.descriptor import load_descriptor
from hpc_oda_commons.datasets.fetch import (
    ChecksumMismatch,
    ManualFetchRequired,
    OfflineError,
    SizeLimitExceeded,
    UnknownSizeError,
    fetch_descriptor,
    parse_size,
    sha256_bytes,
)

console = Console()


def _human(num: int) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1000.0:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000.0
    return f"{value:.1f} PB"


def _resolve_cache_dir(cache: Path | None) -> Path:
    if cache is not None:
        return cache
    env = os.environ.get("HPC_ODA_CACHE_DIR")
    if env:
        return Path(env)
    return Path.cwd() / ".hpc_oda" / "cache" / "datasets"


def datasets_fetch(
    descriptor: Annotated[
        Path,
        typer.Argument(exists=True, readable=True, help="Path to a dataset descriptor YAML."),
    ],
    slice_: Annotated[
        str | None,
        typer.Option("--slice", help="Named slice to fetch (default: the descriptor's default)."),
    ] = None,
    fetch_all: Annotated[
        bool,
        typer.Option("--all", help="Fetch every resource, ignoring slices (may be large)."),
    ] = False,
    max_size: Annotated[
        str,
        typer.Option("--max-size", help="Refuse downloads at/above this size (e.g. 5GB, 500MB)."),
    ] = "5GB",
    cache: Annotated[
        Path | None,
        typer.Option(
            "--cache", help="Cache root (default: .hpc_oda/cache/datasets or HPC_ODA_CACHE_DIR)."
        ),
    ] = None,
    from_dir: Annotated[
        Path | None,
        typer.Option("--from", help="For gated/manual datasets: a local dir holding the file(s)."),
    ] = None,
    offline: Annotated[
        bool | None,
        typer.Option(
            "--offline/--no-offline", help="Refuse network (default: on if HPC_ODA_OFFLINE=1)."
        ),
    ] = None,
    assume_yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Proceed even when the download size is unknown."),
    ] = False,
) -> None:
    """Fetch a dataset's files (checksum-verified) into the local cache."""
    desc = load_descriptor(descriptor)
    descriptor_sha = sha256_bytes(descriptor.read_bytes())
    cache_dir = _resolve_cache_dir(cache)
    is_offline = offline if offline is not None else os.environ.get("HPC_ODA_OFFLINE") == "1"

    try:
        result = fetch_descriptor(
            desc,
            cache_dir=cache_dir,
            slice_name=slice_,
            select_all=fetch_all,
            max_bytes=parse_size(max_size),
            offline=is_offline,
            assume_yes=assume_yes,
            source_dir=from_dir,
            descriptor_sha256=descriptor_sha,
        )
    except SizeLimitExceeded as exc:
        console.print(
            f"[red]Refusing to download {_human(exc.selected_bytes)} "
            f"(limit {_human(exc.limit)}).[/red]"
        )
        console.print("Use a smaller --slice, raise --max-size, or pass --all to force.")
        raise typer.Exit(2) from exc
    except UnknownSizeError as exc:
        console.print(
            "[yellow]Download size is unknown for this slice; re-run with --yes to proceed.[/yellow]"
        )
        raise typer.Exit(2) from exc
    except OfflineError as exc:
        console.print(f"[red]Offline: {exc.filename} is not cached; cannot fetch.[/red]")
        raise typer.Exit(2) from exc
    except ManualFetchRequired as exc:
        console.print(f"[yellow]Manual download required for {exc.filename}:[/yellow]")
        console.print(exc.instructions)
        raise typer.Exit(2) from exc
    except ChecksumMismatch as exc:
        console.print(f"[red]Checksum mismatch for {exc.filename} (expected {exc.expected}).[/red]")
        raise typer.Exit(1) from exc

    title = f"Fetched {result.dataset_id}"
    if result.slice:
        title += f" [{result.slice}]"
    table = Table(title=title)
    table.add_column("file")
    table.add_column("size", justify="right")
    table.add_column("status")
    for resource in result.resources:
        size = _human(resource.bytes) if resource.bytes is not None else "?"
        table.add_row(resource.filename, size, "cached" if resource.reused else "downloaded")
    console.print(table)
    console.print(f"Lockfile: {result.lockfile_path}")
