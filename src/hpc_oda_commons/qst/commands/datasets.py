"""CLI: ``hpc-oda datasets`` — fetch and prepare public operational datasets."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import pyarrow.parquet as pq
import typer
from rich.console import Console
from rich.table import Table

from hpc_oda_commons.benchmarking import (
    CharacterizeError,
    build_card,
    characterize_table,
    select_window,
    write_card,
)
from hpc_oda_commons.datasets.decode import DecodeError
from hpc_oda_commons.datasets.descriptor import load_descriptor
from hpc_oda_commons.datasets.fetch import (
    ChecksumMismatch,
    FetchError,
    ManualFetchRequired,
    OfflineError,
    SizeLimitExceeded,
    UnknownSizeError,
    fetch_descriptor,
    parse_size,
    sha256_bytes,
)
from hpc_oda_commons.datasets.normalize import NormalizeError
from hpc_oda_commons.datasets.prepare import prepare_descriptor

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


def _resolve_offline(offline: bool | None) -> bool:
    if offline is not None:
        return offline
    return os.environ.get("HPC_ODA_OFFLINE") == "1"


def _fetch_error_exit(exc: FetchError) -> typer.Exit:
    """Map a fetch failure to a user message + exit code (shared by fetch/prepare)."""
    if isinstance(exc, SizeLimitExceeded):
        console.print(
            f"[red]Refusing to download {_human(exc.selected_bytes)} "
            f"(limit {_human(exc.limit)}).[/red]"
        )
        console.print("Use a smaller --slice, raise --max-size, or pass --all to force.")
        return typer.Exit(2)
    if isinstance(exc, UnknownSizeError):
        console.print(
            "[yellow]Download size is unknown for this slice; re-run with --yes to proceed.[/yellow]"
        )
        return typer.Exit(2)
    if isinstance(exc, OfflineError):
        console.print(f"[red]Offline: {exc.filename} is not cached; cannot fetch.[/red]")
        return typer.Exit(2)
    if isinstance(exc, ManualFetchRequired):
        console.print(f"[yellow]Manual download required for {exc.filename}:[/yellow]")
        console.print(exc.instructions)
        return typer.Exit(2)
    if isinstance(exc, ChecksumMismatch):
        console.print(f"[red]Checksum mismatch for {exc.filename} (expected {exc.expected}).[/red]")
        return typer.Exit(1)
    console.print(f"[red]Fetch failed: {exc}[/red]")
    return typer.Exit(1)


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
    try:
        result = fetch_descriptor(
            desc,
            cache_dir=_resolve_cache_dir(cache),
            slice_name=slice_,
            select_all=fetch_all,
            max_bytes=parse_size(max_size),
            offline=_resolve_offline(offline),
            assume_yes=assume_yes,
            source_dir=from_dir,
            descriptor_sha256=descriptor_sha,
        )
    except FetchError as exc:
        raise _fetch_error_exit(exc) from exc

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


def datasets_prepare(
    descriptor: Annotated[
        Path,
        typer.Argument(exists=True, readable=True, help="Path to a dataset descriptor YAML."),
    ],
    slice_: Annotated[
        str | None,
        typer.Option("--slice", help="Named slice (default: the descriptor's default)."),
    ] = None,
    fetch_all: Annotated[
        bool,
        typer.Option("--all", help="Use every resource, ignoring slices (may be large)."),
    ] = False,
    target: Annotated[
        str | None,
        typer.Option("--target", help="Only prepare the target with this output schema."),
    ] = None,
    max_size: Annotated[
        str,
        typer.Option("--max-size", help="Refuse downloads at/above this size."),
    ] = "5GB",
    cache: Annotated[
        Path | None,
        typer.Option(
            "--cache", help="Cache root (default: .hpc_oda/cache/datasets or HPC_ODA_CACHE_DIR)."
        ),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option(
            "--out", help="Output root for canonical tables (default: current directory)."
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
    """Fetch, decode, and normalize a dataset into canonical ODA table(s)."""
    desc = load_descriptor(descriptor)
    descriptor_sha = sha256_bytes(descriptor.read_bytes())
    out_root = out if out is not None else Path.cwd()
    try:
        results = prepare_descriptor(
            desc,
            cache_dir=_resolve_cache_dir(cache),
            out_root=out_root,
            slice_name=slice_,
            select_all=fetch_all,
            target_schema=target,
            max_bytes=parse_size(max_size),
            offline=_resolve_offline(offline),
            assume_yes=assume_yes,
            source_dir=from_dir,
            descriptor_sha256=descriptor_sha,
        )
    except FetchError as exc:
        raise _fetch_error_exit(exc) from exc
    except (DecodeError, NormalizeError) as exc:
        console.print(f"[red]Prepare failed: {exc}[/red]")
        raise typer.Exit(1) from exc

    table = Table(title=f"Prepared {desc.dataset_id}")
    table.add_column("schema")
    table.add_column("rows", justify="right")
    table.add_column("table")
    for result in results:
        rows = str(result.summary.get("rows_final", "?"))
        table.add_row(result.target_schema, rows, str(result.table_path))
    console.print(table)


def datasets_characterize(
    table_path: Annotated[
        Path,
        typer.Argument(
            exists=True, readable=True, help="Canonical oda.job parquet to characterize."
        ),
    ],
    out: Annotated[
        Path,
        typer.Option("--out", help="Output directory for the dataset card."),
    ] = Path("docs/benchmarking/datasets"),
    dataset_id: Annotated[
        str | None,
        typer.Option("--dataset-id", help="Dataset id label (default: derived from the path)."),
    ] = None,
    system: Annotated[
        str | None, typer.Option("--system", help="System name recorded on the card.")
    ] = None,
    descriptor: Annotated[
        str | None, typer.Option("--descriptor", help="Descriptor id/path recorded on the card.")
    ] = None,
    anchor: Annotated[
        float,
        typer.Option("--anchor", help="Place the window END at this fraction of the healthy span."),
    ] = 0.80,
    train_days: Annotated[int, typer.Option("--train-days", help="Training lookback (days).")] = 60,
    test_days: Annotated[int, typer.Option("--test-days", help="Test coverage (days).")] = 30,
    gap_min_days: Annotated[
        int,
        typer.Option(
            "--gap-min-days", help="Consecutive low-volume days that count as a missing block."
        ),
    ] = 3,
    gap_floor: Annotated[
        float,
        typer.Option(
            "--gap-floor", help="Missing-block threshold, as a fraction of median daily volume."
        ),
    ] = 0.05,
) -> None:
    """Characterize a prepared dataset's health, pick its 3-month benchmark window, write a card.

    Emits ``<stem>.card.json`` (machine-readable, consumed by the benchmark runner) and
    ``<stem>.md`` (human-readable) under ``--out``. See docs/benchmarking/methodology.md.
    """
    stem = dataset_id.split(".")[-1] if dataset_id else table_path.parent.name
    did = dataset_id or f"dataset.job_runtime.{stem}"
    table = pq.read_table(table_path)
    try:
        char = characterize_table(table, gap_min_days=gap_min_days, gap_floor_frac=gap_floor)
        window = select_window(
            char,
            anchor=anchor,
            train_days=train_days,
            test_days=test_days,
            gap_min_days=gap_min_days,
        )
    except CharacterizeError as exc:
        console.print(f"[red]Cannot characterize {table_path}: {exc}[/red]")
        raise typer.Exit(1) from exc

    source = {}
    if system:
        source["system"] = system
    if descriptor:
        source["descriptor"] = descriptor
    card = build_card(did, table_path, char, window, source=source or None)
    json_path, md_path = write_card(card, out, stem=stem)

    hs = char["healthy_span"]
    verdict = "[green]healthy[/green]" if window["healthy"] else "[red]UNHEALTHY[/red]"
    console.print(
        f"[bold]{did}[/bold]: {char['n_rows']:,} rows · healthy span {hs['start']}..{hs['end']} "
        f"· {char['rate_per_day']:,.0f} jobs/day"
    )
    if char["gaps"]:
        console.print(f"  [yellow]missing blocks in full span: {len(char['gaps'])}[/yellow]")
    console.print(
        f"  window {window['window_start']}..{window['window_end']} "
        f"({window['n_rows']:,} rows) → {verdict}"
    )
    console.print(f"  card: {json_path}")
    console.print(f"        {md_path}")
