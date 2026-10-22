"""CLI: ``hpc-oda datasets`` — fetch, prepare, characterize, card, slice and bound datasets."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

import pyarrow as pa
import pyarrow.parquet as pq
import typer
from rich.console import Console
from rich.table import Table

from hpc_oda_commons.benchmark.arm_selection import DEFAULT_BURN_IN
from hpc_oda_commons.benchmarking import (
    CeilingError,
    CharacterizeError,
    build_card,
    characterize_table,
    compute_ceiling,
    select_window,
    write_card,
)
from hpc_oda_commons.benchmarking.hpc.slice import SliceError, slice_dataset
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
        console.print(
            f"[red]Checksum mismatch for {exc.filename}: "
            f"expected {exc.expected}, got {exc.actual}.[/red]"
        )
        return typer.Exit(1)
    console.print(f"[red]Fetch failed: {exc}[/red]")
    return typer.Exit(1)


def descriptor_argument(value: Path) -> Path:
    """Resolve a descriptor argument: a file, or a bundled dataset's name or id."""
    from hpc_oda_commons.datasets.descriptor import find_descriptor

    found = find_descriptor(value)
    if found is None:
        raise typer.BadParameter(
            f"{value} is neither a descriptor file nor a bundled dataset "
            "(`hpc-oda browse --type dataset` lists them)."
        )
    return found


def datasets_fetch(
    descriptor: Annotated[
        Path,
        typer.Argument(
            callback=descriptor_argument,
            help="A dataset descriptor YAML, or a bundled dataset's name (pm100, dataset.pm100).",
        ),
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
        typer.Argument(
            callback=descriptor_argument,
            help="A dataset descriptor YAML, or a bundled dataset's name (pm100, dataset.pm100).",
        ),
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
        typer.Option("--out", help="Output directory for the runtime card (*.card.json)."),
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
    pin_end: Annotated[
        str | None,
        typer.Option(
            "--pin-end",
            help="Keep the window ending on this day (YYYY-MM-DD) instead of choosing one: "
            "the window a benchmark already ran on.",
        ),
    ] = None,
    anchor: Annotated[
        float,
        typer.Option("--anchor", help="Place the window END at this fraction of the healthy span."),
    ] = 0.80,
    train_days: Annotated[int, typer.Option("--train-days", help="Training lookback (days).")] = 60,
    test_days: Annotated[int, typer.Option("--test-days", help="Test coverage (days).")] = 90,
    history_days: Annotated[
        int,
        typer.Option(
            "--history-days",
            help="History the earliest scored window must see (the lookback budget).",
        ),
    ] = 120,
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
    """Check a prepared table's health, choose its benchmark window, write its runtime card.

    Writes `<stem>.card.json` under --out. `recipes write`, `bench-matrix`, `datasets ceiling
    --card` and the leaderboard read it; people read it on the dataset's card, so run
    `hpc-oda datasets cards` after. See docs/benchmarking/runtime/methodology.md.
    """
    stem = dataset_id.split(".")[-1] if dataset_id else table_path.parent.name
    did = dataset_id or f"dataset.{stem}"
    # List columns (F-DATA's embedding) are never characterized; leaving them unread keeps a
    # large table within memory (#249).
    schema = pq.read_schema(table_path)
    table = pq.read_table(
        table_path,
        columns=[f.name for f in schema if not pa.types.is_list(f.type)],
    )
    try:
        char = characterize_table(table, gap_min_days=gap_min_days, gap_floor_frac=gap_floor)
        window = select_window(
            char,
            anchor=anchor,
            pinned_end=pin_end,
            train_days=train_days,
            test_days=test_days,
            history_days=history_days,
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
    json_path = write_card(card, out, stem=stem)

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
    console.print(f"  card: {json_path} (regenerate the dataset cards: hpc-oda datasets cards)")


def datasets_slice(
    table_path: Annotated[
        Path,
        typer.Argument(exists=True, readable=True, help="Canonical oda.job parquet to slice."),
    ],
    start: Annotated[
        str, typer.Option("--start", help="First day kept, YYYY-MM-DD (UTC, inclusive).")
    ],
    end: Annotated[str, typer.Option("--end", help="Last day kept, YYYY-MM-DD (UTC, inclusive).")],
    out: Annotated[Path, typer.Option("--out", help="Output parquet path.")],
) -> None:
    """Cut a prepared table to a window you name, keeping every job that overlaps it.

    The rolling split tests the days before a table's last submit, so cutting the end
    picks the test period, and the start must leave the training lookback. A job is kept
    if it was submitted by the end of --end and ended on or after --start, as in
    `bench-matrix slice`. Writes slice.json beside --out.
    """
    try:
        n = slice_dataset(table_path, out, start, end, window_key="window")
    except (SliceError, ValueError) as exc:
        console.print(f"[red]Cannot slice {table_path}: {exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"{n:,} rows overlapping {start}..{end} → {out}")


def datasets_ceiling(
    table_path: Annotated[
        Path,
        typer.Argument(exists=True, readable=True, help="Windowed oda.job parquet to analyse."),
    ],
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Write the analysis JSON here (default: beside the table)."),
    ] = None,
    card: Annotated[
        Path | None,
        typer.Option(
            "--card",
            exists=True,
            readable=True,
            help="The dataset's runtime card (*.card.json): sets --n-windows to cover its test "
            "days. The runtime leaderboard scores 120 windows today, so pass --n-windows 120 to "
            "match it.",
        ),
    ] = None,
    n_windows: Annotated[
        int | None,
        typer.Option("--n-windows", help="Rolling windows (power: 89). Overrides --card."),
    ] = None,
    test_window_hours: Annotated[
        int, typer.Option("--test-window-hours", help="Hours in each rolling test window.")
    ] = 6,
    skip_windows: Annotated[
        int,
        typer.Option(
            "--skip-windows",
            help="Leading windows with jobs to leave unscored: the walk-forward burn-in, so "
            "the floor covers the rows a runtime leaderboard score does. Power has one "
            "arm and no burn-in: pass 0.",
        ),
    ] = DEFAULT_BURN_IN,
    dataset_id: Annotated[
        str | None, typer.Option("--dataset-id", help="Label recorded on the analysis.")
    ] = None,
    target: Annotated[
        str, typer.Option("--target", help="Column the floor bounds, e.g. avgpcon_per_node.")
    ] = "runtime_seconds",
    extra_feature: Annotated[
        list[str] | None,
        typer.Option(
            "--extra-feature",
            help="A column some benchmarked model reads beyond the shared allowlist (repeatable), "
            "e.g. embedding. The floor bounds a model only if its signature holds every input.",
        ),
    ] = None,
    start: Annotated[
        str | None,
        typer.Option("--start", help="Read only the recipe's window: its first day."),
    ] = None,
    end: Annotated[
        str | None,
        typer.Option("--end", help="Read only the recipe's window: its last day."),
    ] = None,
    require_nonnull: Annotated[
        list[str] | None,
        typer.Option(
            "--require-nonnull",
            help="Read only rows that have this column, as the recipe does (repeatable).",
        ),
    ] = None,
    window_by: Annotated[
        str,
        typer.Option(
            "--by",
            help="overlap: keep jobs that overlap the window; submit: keep jobs submitted in it.",
        ),
    ] = "overlap",
) -> None:
    """Compute the minimum error any submit-time predictor could achieve on this table.

    Jobs with identical submit-time features cannot be told apart, so the best possible
    prediction per signature is its group median (for MAE) or mean (for RMSE). That bound
    calibrates every model score: an MAE means little without knowing how much accuracy was
    available. Also measures causal memorization -- predicting from same-signature jobs that
    finished earlier -- across a range of lookbacks, which is a deployable strategy rather
    than a bound. See docs/benchmarking/runtime/ceilings.md.
    """
    from datetime import datetime, timezone

    from hpc_oda_commons.benchmarking.hpc.matrix import load_card, n_windows_for
    from hpc_oda_commons.kernel.validate import validate_json
    from hpc_oda_commons.models.feature_policy import feature_allowlist

    stem = dataset_id.split(".")[-1] if dataset_id else table_path.parent.name
    if start or end or require_nonnull:
        from hpc_oda_commons.benchmarking.hpc.slice import SliceError, read_window

        try:
            table = read_window(
                table_path, start, end, require_nonnull=require_nonnull or [], by=window_by
            )
        except SliceError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1) from exc
    else:
        table = pq.read_table(table_path)
    try:
        fields = sorted(feature_allowlist(extra_feature or (), target=target))
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    if n_windows is None:
        if card is None:
            console.print("[red]Pass --card (runtime) or --n-windows (power).[/red]")
            raise typer.Exit(1)
        n_windows = n_windows_for(load_card(card), test_window_hours)
    try:
        result = compute_ceiling(
            table,
            feature_fields=fields,
            n_windows=n_windows,
            test_window_hours=test_window_hours,
            skip_windows=skip_windows,
            target_field=target,
        )
    except CeilingError as exc:
        console.print(f"[red]Cannot analyse {table_path}: {exc}[/red]")
        raise typer.Exit(1) from exc

    result["dataset_id"] = dataset_id or stem
    result["generated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    validate_json(result, "oda.ceiling.v0.1.0")

    out_path = out or table_path.with_name("ceiling.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    fl, sizes = result["floor"], result["floor"]["group_sizes"]
    # Runtime floors are thousands of seconds; power floors are a few watts per node.
    places = 0 if fl["mae"] >= 100 else 2
    split = result["split"]
    console.print(
        f"[bold]{result['dataset_id']}[/bold]: {result['scored_rows']:,} scored rows in "
        f"{split['scored_windows']} windows (skipped the first {split['skip_windows']} of "
        f"{split['windows_with_jobs']} with jobs)"
    )
    console.print(
        f"  floor  MAE [green]{fl['mae']:,.{places}f}[/green]  "
        f"RMSE [green]{fl['rmse']:,.{places}f}[/green]  "
        f"over {fl['signatures']:,} signatures"
    )
    console.print(
        f"  groups min {sizes['min']} / median {sizes['median']:,.0f} / max {sizes['max']:,}"
        f" · {sizes['singleton_row_share'] * 100:.1f}% of rows are alone in their group"
    )
    if sizes["singleton_row_share"] > 0.10:
        console.print(
            "  [yellow]note:[/yellow] many rows are alone in their signature, so the floor is "
            "loose here - it cannot constrain rows it has no peers for."
        )
    cm = result.get("causal_memorization", {})
    if cm:
        best = cm["best_lookback"]
        s = cm["sweep"][best]
        console.print(
            f"  causal memorization best at [cyan]{best}[/cyan]: MAE {s['mae']:,.{places}f} "
            f"(coverage {s['coverage'] * 100:.0f}%)"
        )
    console.print(f"  → {out_path}")


def datasets_cards(
    out: Annotated[
        Path, typer.Option("--out", help="Directory to write the dataset cards into.")
    ] = Path("docs/datasets/cards"),
    leaderboard: Annotated[
        Path,
        typer.Option(
            "--leaderboard",
            exists=True,
            readable=True,
            help="The leaderboard JSON the cards' results come from.",
        ),
    ] = Path("site/leaderboard/leaderboard.json"),
    descriptors: Annotated[
        Path | None,
        typer.Option(
            "--descriptors",
            exists=True,
            file_okay=False,
            help="Card the descriptors in this folder, your own among them, instead "
            "of the bundled ones.",
        ),
    ] = None,
    benchmark_dir: Annotated[
        Path,
        typer.Option(
            "--benchmark-dir",
            help="Folder of runtime cards (*.card.json) and error ceilings (*.ceiling.json).",
        ),
    ] = Path("docs/benchmarking/datasets"),
    recipes: Annotated[
        list[Path] | None,
        typer.Option("--recipes", help="A folder of the datasets' recipes (repeatable)."),
    ] = None,
) -> None:
    """Write a card for every dataset, generated from its files.

    Each card comes from the dataset's descriptor, its runtime card, the error ceilings, the
    recipes and the leaderboard, so regenerate the cards whenever one of those changes; for
    the bundled datasets a unit test fails when the committed cards differ from what this
    writes. With --descriptors, it cards a dataset of your own the same way.
    """
    from hpc_oda_commons.benchmark.dataset_cards import write_dataset_cards

    for path in write_dataset_cards(
        out.resolve(),
        leaderboard.resolve(),
        benchmark_dir.resolve(),
        descriptors_dir=descriptors,
        recipe_dirs=[r.resolve() for r in recipes or ()],
    ):
        console.print(f"[green]wrote[/green] {path}")
