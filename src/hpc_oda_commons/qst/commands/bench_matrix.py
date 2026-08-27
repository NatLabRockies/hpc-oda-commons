"""CLI: ``hpc-oda bench-matrix`` — plan and run the full model x dataset benchmark.

``plan``/``slice`` build recipes + sbatch scripts + windowed parquets locally (from the
tracked dataset cards + a local, gitignored site config). ``stage``/``submit``/``status``/
``collect``/``aggregate`` drive the cluster. The site config supplies every
cluster/user-specific value, so nothing site-specific is generated into the tracked repo.
See docs/benchmarking/hpc-runner.md.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from hpc_oda_commons.benchmark.arm_selection import DEFAULT_BURN_IN, DEFAULT_METRIC
from hpc_oda_commons.benchmarking.hpc.config import (
    DEFAULT_SITE_CONFIG_PATH,
    SiteConfig,
    SiteConfigError,
    load_site_config,
)
from hpc_oda_commons.benchmarking.hpc.matrix import (
    RUNTIME_MODELS,
    ModelSelectionError,
    build_plan,
    load_cards,
    select_models,
    slice_extension_for,
    tier_for_rows,
    write_plan,
)
from hpc_oda_commons.benchmarking.hpc.orchestrate import (
    LoadedPlan,
    OrchestrationError,
    collect_commands,
    load_plan,
    merge_submission_manifest,
    parse_sacct,
    run_command,
    sacct_command,
    stage_commands,
    submit_plan,
)
from hpc_oda_commons.benchmarking.hpc.slice import SliceError, effective_start, slice_dataset

console = Console()

_STAGING_ROOT = Path(".hpc_oda/bench-matrix")
# Plan ids minted by `bench-matrix plan` when --plan-id is not given: `%Y%m%d-%H%M%S`.
# Lexicographic order over this shape is chronological order, which is what makes
# "newest" cheap to compute.
_TIMESTAMP_PLAN_ID = re.compile(r"^\d{8}-\d{6}$")


def _load_site(site: Path) -> SiteConfig:
    try:
        return load_site_config(site)
    except SiteConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc


def _resolve_plan_dir(plan_dir: Path | None) -> Path:
    """Return the plan dir, defaulting to the newest *timestamped* plan in the staging root.

    Only timestamp-named plans are eligible to be the default. A plan named with
    ``--plan-id`` has to be selected explicitly, because it was named deliberately and
    nothing about its name says when it was built.

    The previous version sorted every plan dir together and took the last, which is why
    this is worth spelling out: digits sort before letters, so a single named plan
    (``test-plan``, ``fleet-01``) shadowed *every* timestamped plan permanently, however
    much newer. `submit` reads this, so the failure mode was launching a stale matrix whose
    results look perfectly plausible (#147).
    """
    if plan_dir is not None:
        if not (plan_dir / "plan.json").exists():
            console.print(
                f"[red]No plan.json under {plan_dir}. Run `bench-matrix plan` first.[/red]"
            )
            raise typer.Exit(1)
        return plan_dir
    found = [p.parent for p in _STAGING_ROOT.glob("*/plan.json")]
    candidates = sorted(d for d in found if _TIMESTAMP_PLAN_ID.match(d.name))
    if not candidates:
        named = sorted(d.name for d in found)
        hint = (
            f" Named plans are not auto-selected; pass --plan-dir to use one of: {', '.join(named)}."
            if named
            else ""
        )
        console.print(
            f"[red]No timestamped plans under {_STAGING_ROOT}. "
            f"Run `bench-matrix plan` first.{hint}[/red]"
        )
        raise typer.Exit(1)
    return candidates[-1]


def _load_plan_dir(plan_dir: Path | None) -> tuple[LoadedPlan, Path]:
    """Resolve + load a plan, announcing which one. Every plan-consuming command goes
    through here, so the echo means you never act on a defaulted plan without seeing it."""
    resolved = _resolve_plan_dir(plan_dir)
    plan = load_plan(resolved / "plan.json")
    console.print(
        f"[dim]Using plan[/dim] [cyan]{plan.plan_id}[/cyan] "
        f"[dim]({len(plan.cells)} cells, {len(plan.embeds)} embeds) from {resolved}[/dim]"
    )
    return plan, resolved


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
    exclude_model: Annotated[
        list[str] | None,
        typer.Option(
            "--exclude-model",
            help=(
                "Leave a model out of the matrix (repeatable). Full key "
                "(job_runtime_mlp) or short tag (mlp)."
            ),
        ),
    ] = None,
    include_unhealthy: Annotated[
        bool,
        typer.Option(
            "--include-unhealthy", help="Include datasets whose window is flagged unhealthy."
        ),
    ] = False,
    windows_dir: Annotated[
        Path,
        typer.Option(
            "--windows-dir",
            help=(
                "Sliced windows dir, read for each slice.json so cells are sized from the "
                "rows they actually load rather than the card's narrower window."
            ),
        ),
    ] = Path(".hpc_oda/bench-matrix/data/windows"),
) -> None:
    """Generate the benchmark-matrix plan (recipes + sbatch scripts + plan.json)."""
    try:
        cfg = load_site_config(site)
    except SiteConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    try:
        models = select_models(exclude_model or [])
    except ModelSelectionError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    cards = load_cards(cards_dir, windows_dir if windows_dir.exists() else None)
    if not windows_dir.exists():
        console.print(
            f"[yellow]No slices under {windows_dir}[/yellow] — sizing cells from the cards' "
            "own windows, which under-counts the rows a cell loads. Run "
            "[cyan]bench-matrix slice[/cyan] first for accurate sizing."
        )
    pid = plan_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    plan = build_plan(cards, cfg, plan_id=pid, include_unhealthy=include_unhealthy, models=models)

    staging_dir = out / pid
    plan_path = write_plan(plan, staging_dir, cfg)

    # --- summary ---
    table = Table(title=f"Benchmark matrix — plan {pid}")
    table.add_column("dataset")
    table.add_column("rows loaded", justify="right")
    table.add_column("tier")
    table.add_column("partition")
    table.add_column("workers", justify="right")
    table.add_column("models", justify="right")
    by_dataset: dict[str, int] = {}
    for cell in plan.cells:
        by_dataset[cell.dataset] = by_dataset.get(cell.dataset, 0) + 1
    card_by_name = {c.dataset: c for c in cards}
    for dataset in sorted(by_dataset):
        card = card_by_name[dataset]
        tier = tier_for_rows(card.effective_rows)
        table.add_row(
            dataset,
            f"{card.effective_rows:,}",
            tier.name,
            _partition_for(plan, dataset),
            str(tier.window_workers),
            str(by_dataset[dataset]),
        )
    console.print(table)

    n_datasets = len(by_dataset)
    console.print(
        f"[green]Planned[/green] {len(plan.cells)} benchmark cells "
        f"({n_datasets} datasets x {len(plan.models)} models "
        f"x {len(plan.lookbacks)} lookbacks {plan.lookbacks}) "
        f"+ {len(plan.embeds)} embedding jobs."
    )
    left_out = [m for m in RUNTIME_MODELS if m not in plan.models]
    if left_out:
        console.print(f"[yellow]Excluded {len(left_out)} model(s)[/yellow]: {', '.join(left_out)}")
    if plan.skipped:
        console.print(f"[yellow]Skipped {len(plan.skipped)}[/yellow]:")
        for entry in plan.skipped:
            console.print(f"  [yellow]{entry['dataset']}[/yellow] — {entry['reason']}")
        if any("unhealthy" in e["reason"] for e in plan.skipped):
            console.print("  Re-run with [cyan]--include-unhealthy[/cyan] to include those.")
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
    extra_lookback_days: Annotated[
        int | None,
        typer.Option(
            "--extra-lookback-days",
            min=0,
            help=(
                "Extend the slice earlier by N days, leaving the test region alone. "
                "Defaults to the shortfall the benchmark split implies for each dataset "
                "(training_lookback_days - the card's train_days). Pass a value only to "
                "override that."
            ),
        ),
    ] = None,
) -> None:
    """Slice each dataset's canonical parquet to its benchmark window.

    Reads the canonical parquet named on each card and writes
    ``<out>/<dataset>/data.parquet``, plus a ``slice.json`` recording which window it
    holds. That tree rsyncs to ``<repo>/data/windows`` on the cluster, where the generated
    recipes read it. Overlapping (long-running) jobs are kept so the earliest rolling
    windows keep their training rows — see the slice module.

    By default each dataset is extended back by exactly the shortfall its card leaves against
    the benchmark split's ``training_lookback_days``, so a slice always holds the history the
    generated recipes ask for. Deriving it rather than passing it by hand is deliberate: a
    slice silently narrower than the split is invisible in the results (#143, #145).
    """
    cards = load_cards(cards_dir)
    table = Table(title="Slice to benchmark window")
    table.add_column("dataset")
    table.add_column("window")
    table.add_column("rows", justify="right")
    table.add_column("status")

    sliced = 0
    for card in cards:
        if dataset and card.dataset != dataset:
            continue
        if not card.healthy and not include_unhealthy:
            table.add_row(card.dataset, "-", "-", "[yellow]skip (unhealthy)[/yellow]")
            continue
        source = Path(card.source_table)
        if not source.exists():
            table.add_row(card.dataset, "-", "-", f"[red]missing source {source}[/red]")
            continue
        dest = out / card.dataset / "data.parquet"
        extension = (
            extra_lookback_days if extra_lookback_days is not None else slice_extension_for(card)
        )
        start = effective_start(card.window_start, extension)
        try:
            n = slice_dataset(
                source,
                dest,
                card.window_start,
                card.window_end,
                extra_lookback_days=extension,
            )
        except SliceError as exc:
            table.add_row(card.dataset, "-", "-", f"[red]{exc}[/red]")
            continue
        sliced += 1
        table.add_row(card.dataset, f"{start}..{card.window_end}", f"{n:,}", "[green]ok[/green]")

    console.print(table)
    console.print(f"[green]Sliced[/green] {sliced} datasets → [cyan]{out}[/cyan]")


# --- orchestration: stage → submit → status → collect → aggregate -------------------

_PLAN_DIR_OPT = Annotated[
    Path | None,
    typer.Option("--plan-dir", help="Plan dir (default: newest under .hpc_oda/bench-matrix)."),
]
_SITE_OPT = Annotated[Path, typer.Option("--site", help="Local (gitignored) HPC site config.")]
_DRY_RUN_OPT = Annotated[
    bool, typer.Option("--dry-run", help="Print commands without running them.")
]


def bench_matrix_stage(
    plan_dir: _PLAN_DIR_OPT = None,
    site: _SITE_OPT = DEFAULT_SITE_CONFIG_PATH,
    windows_dir: Annotated[
        Path,
        typer.Option("--windows-dir", help="Local sliced windows to stage."),
    ] = Path(".hpc_oda/bench-matrix/data/windows"),
    dry_run: _DRY_RUN_OPT = False,
) -> None:
    """rsync the windowed parquets and the plan (recipes + scripts) to the cluster."""
    cfg = _load_site(site)
    plan, resolved = _load_plan_dir(plan_dir)
    console.print(f"Staging plan [cyan]{plan.plan_id}[/cyan] → {cfg.host}:{cfg.repo_dir}")
    try:
        for cmd in stage_commands(plan, cfg, windows_dir=windows_dir, plan_dir=resolved):
            run_command(cmd, execute=not dry_run, echo=console.print)
    except OrchestrationError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print("[green]Staged.[/green]" if not dry_run else "[yellow]Dry-run only.[/yellow]")


def bench_matrix_submit(
    plan_dir: _PLAN_DIR_OPT = None,
    site: _SITE_OPT = DEFAULT_SITE_CONFIG_PATH,
    execute: Annotated[
        bool,
        typer.Option(
            "--execute", help="Actually submit (default: dry-run — charges the allocation)."
        ),
    ] = False,
    only: Annotated[str | None, typer.Option("--only", help="Submit only this dataset.")] = None,
    only_model: Annotated[
        str | None,
        typer.Option("--only-model", help="Submit only this model (short tag, e.g. baseline)."),
    ] = None,
    partition: Annotated[
        str | None,
        typer.Option("--partition", help="Override partition (e.g. debug for a smoke test)."),
    ] = None,
    time: Annotated[
        str | None, typer.Option("--time", help="Override walltime (e.g. 00:20:00).")
    ] = None,
) -> None:
    """Submit embed jobs then benchmark cells (embedding_knn cells depend on their embed).

    Dry-run by default; pass ``--execute`` to really submit. Use ``--only``/``--only-model``
    and ``--partition debug`` for a quick single-cell smoke before the full fleet.
    """
    cfg = _load_site(site)
    plan, resolved = _load_plan_dir(plan_dir)
    try:
        manifest = submit_plan(
            plan,
            cfg,
            execute=execute,
            only=only,
            only_model=only_model,
            partition=partition,
            time=time,
            echo=console.print,
        )
    except OrchestrationError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    n = len(manifest["cells"])
    if execute:
        manifest_path = resolved / "submitted.json"
        existing = None
        if manifest_path.exists():
            try:
                existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                console.print(
                    f"[yellow]Could not read {manifest_path}; writing a fresh manifest.[/yellow]"
                )
        merged = merge_submission_manifest(existing, manifest)
        manifest_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        console.print(
            f"[green]Submitted[/green] {n} cells + {len(manifest['embeds'])} embeds "
            f"→ {manifest_path}"
        )
        carried = len(merged["cells"]) - n
        if carried > 0:
            console.print(
                f"  manifest now holds {len(merged['cells'])} cells "
                f"({carried} carried over from earlier submissions)"
            )
    else:
        console.print(
            f"[yellow]Dry-run[/yellow]: would submit {n} cells + {len(manifest['embeds'])} embeds. "
            "Pass [cyan]--execute[/cyan] to submit."
        )


def bench_matrix_status(
    plan_dir: _PLAN_DIR_OPT = None,
    site: _SITE_OPT = DEFAULT_SITE_CONFIG_PATH,
) -> None:
    """Poll sacct for the submitted jobs and summarize their states."""
    cfg = _load_site(site)
    _plan, resolved = _load_plan_dir(plan_dir)
    sub_path = resolved / "submitted.json"
    if not sub_path.exists():
        console.print(
            f"[red]No submitted.json under {resolved}. Run `bench-matrix submit --execute` first.[/red]"
        )
        raise typer.Exit(1)
    manifest = json.loads(sub_path.read_text(encoding="utf-8"))
    jobids = [c["jobid"] for c in manifest["cells"]] + list(manifest["embeds"].values())
    jobids = [j for j in jobids if j and not j.startswith("<")]
    if not jobids:
        console.print("[yellow]No real jobids recorded (was this a dry-run?).[/yellow]")
        raise typer.Exit(0)

    try:
        res = run_command(sacct_command(cfg, jobids), execute=True, echo=console.print)
    except OrchestrationError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    states = parse_sacct(res.stdout)

    counts: dict[str, int] = {}
    table = Table(title=f"Job status — plan {manifest['plan_id']}")
    table.add_column("job")
    table.add_column("jobid")
    table.add_column("state")
    table.add_column("elapsed")
    for c in manifest["cells"]:
        info = states.get(c["jobid"], {})
        state = info.get("state", "UNKNOWN")
        counts[state] = counts.get(state, 0) + 1
        table.add_row(c["job_name"], c["jobid"], state, info.get("elapsed", ""))
    console.print(table)
    console.print("  ".join(f"[bold]{k}[/bold]={v}" for k, v in sorted(counts.items())))


def bench_matrix_collect(
    plan_dir: _PLAN_DIR_OPT = None,
    site: _SITE_OPT = DEFAULT_SITE_CONFIG_PATH,
    dest: Annotated[
        Path | None,
        typer.Option(
            "--dest",
            help="Local dir for pulled result bundles (default: <plan-dir>/collected-runs).",
        ),
    ] = None,
    dry_run: _DRY_RUN_OPT = False,
) -> None:
    """rsync the cluster's result bundles (runs/) back locally."""
    cfg = _load_site(site)
    plan, resolved = _load_plan_dir(plan_dir)
    target = dest or (resolved / "collected-runs")
    target.mkdir(parents=True, exist_ok=True)
    try:
        for cmd in collect_commands(plan, cfg, target):
            run_command(cmd, execute=not dry_run, echo=console.print)
    except OrchestrationError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(
        f"[green]Collected[/green] → [cyan]{target}[/cyan]"
        if not dry_run
        else "[yellow]Dry-run only.[/yellow]"
    )


def bench_matrix_aggregate(
    plan_dir: _PLAN_DIR_OPT = None,
    runs: Annotated[
        Path | None,
        typer.Option("--runs", help="Collected runs dir (default: <plan-dir>/collected-runs)."),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Leaderboard output dir (default: <plan-dir>/leaderboard)."),
    ] = None,
) -> None:
    """Build the leaderboard from collected result bundles."""
    from hpc_oda_commons.benchmark.results import build_leaderboard, write_leaderboard

    _plan, resolved = _load_plan_dir(plan_dir)
    runs_dir = runs or (resolved / "collected-runs")
    out_dir = out or (resolved / "leaderboard")
    if not runs_dir.exists():
        console.print(f"[red]No runs at {runs_dir}. Run `bench-matrix collect` first.[/red]")
        raise typer.Exit(1)
    leaderboard = build_leaderboard(runs_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = write_leaderboard(leaderboard, out_dir)
    n = len(leaderboard.get("entries", []))
    superseded = leaderboard.get("superseded", [])
    console.print(f"[green]Aggregated[/green] {n} benchmark cells → [cyan]{json_path}[/cyan]")
    if superseded:
        # Say what was narrowed rather than narrowing silently (#166).
        console.print(
            f"[yellow]Superseded {len(superseded)}[/yellow] older bundle(s) for cells that "
            "were run more than once; the newest of each was kept:"
        )
        for entry in superseded[:10]:
            console.print(f"  {entry['created_at']}  {entry['bundle_dir']}")
        if len(superseded) > 10:
            console.print(f"  ... and {len(superseded) - 10} more")


def bench_matrix_rank(
    plan_dir: _PLAN_DIR_OPT = None,
    runs: Annotated[
        Path | None,
        typer.Option("--runs", help="Collected runs dir (default: <plan-dir>/collected-runs)."),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Ranking output dir (default: <plan-dir>/leaderboard)."),
    ] = None,
    metric: Annotated[
        str, typer.Option("--metric", help="Metric to select and score on (mae, rmse).")
    ] = DEFAULT_METRIC,
    burn_in: Annotated[
        int,
        typer.Option("--burn-in", help="Windows used to build history before scoring starts."),
    ] = DEFAULT_BURN_IN,
) -> None:
    """Rank each cell by walk-forward choice among its training-lookback arms.

    Reporting the best arm by test error would select on the number it reports; this chooses
    each window's arm from earlier windows only (#190).
    """
    from hpc_oda_commons.benchmark.results import build_arm_ranking, write_arm_ranking

    _plan, resolved = _load_plan_dir(plan_dir)
    runs_dir = runs or (resolved / "collected-runs")
    out_dir = out or (resolved / "leaderboard")
    if not runs_dir.exists():
        console.print(f"[red]No runs at {runs_dir}. Run `bench-matrix collect` first.[/red]")
        raise typer.Exit(1)

    ranking = build_arm_ranking(runs_dir, metric=metric, burn_in=burn_in)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = write_arm_ranking(ranking, out_dir)

    table = Table(title=f"Walk-forward lookback selection — {metric}, burn-in {burn_in}")
    table.add_column("dataset")
    table.add_column("model")
    table.add_column("policy", justify="right")
    table.add_column("best arm (hindsight)", justify="right")
    table.add_column("cost of choosing", justify="right")
    table.add_column("arms chosen")
    for cell in ranking["cells"]:
        counts = cell["choice_counts"]
        chosen = " ".join(f"{k}:{v}" for k, v in counts.items() if v)
        oracle = f"{cell['oracle_key']} {cell['oracle_score']:,.0f}"
        pct = 100.0 * cell["regret"] / cell["oracle_score"] if cell["oracle_score"] else 0.0
        table.add_row(
            cell["dataset"].split(".")[-1],
            cell["model"].split(".")[-1],
            f"{cell['score']:,.0f}",
            oracle,
            f"+{pct:.1f}%",
            chosen,
        )
    console.print(table)
    console.print(
        f"[green]Ranked[/green] {len(ranking['cells'])} cell(s) → [cyan]{json_path}[/cyan]"
    )
    if ranking["unranked"]:
        # Named rather than silently absent, as everywhere else the tooling narrows coverage.
        console.print(f"[yellow]Unranked {len(ranking['unranked'])}[/yellow] cell(s):")
        for cell in ranking["unranked"][:10]:
            console.print(f"  {cell['dataset']} {cell['model']}: {cell['reason']}")
        if len(ranking["unranked"]) > 10:
            console.print(f"  ... and {len(ranking['unranked']) - 10} more")
