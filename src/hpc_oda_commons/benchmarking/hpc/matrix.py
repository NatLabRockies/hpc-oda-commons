"""Plan the full model x dataset benchmark matrix for an HPC cluster.

Given the tracked dataset cards and a local :class:`SiteConfig`, this builds one Slurm
recipe + sbatch script per (dataset, model) cell, plus one GPU embedding job per dataset
(the embedded parquet is reused by ``job_runtime_embedding_knn``). Everything is written
under a local staging dir (``.hpc_oda/bench-matrix/<plan_id>/``, gitignored); the
orchestration step rsyncs it to the cluster and submits.

All resource decisions are derived from each card's 90-day-window row count, so the plan
is reproducible from tracked inputs + the (untracked) site config alone.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from hpc_oda_commons.benchmarking.hpc.config import SiteConfig

# --- Benchmark configuration (the agreed methodology; see docs/benchmarking/methodology.md) ---

# Six runtime-prediction models. ``job_power_uopc`` is power prediction — out of scope.
RUNTIME_MODELS: tuple[str, ...] = (
    "job_runtime_baseline",
    "job_runtime_tfidf_knn",
    "job_runtime_random_forest",
    "job_runtime_xgboost",
    "job_runtime_mlp",
    "job_runtime_embedding_knn",
)
# The model whose recipe reads the *embedded* parquet (requires a prior GPU embed pass).
EMBEDDING_MODEL: str = "job_runtime_embedding_knn"

# Models whose independent per-window fits are run in parallel across the cell's allocated
# cores (via ``window_n_jobs``). MLP only: Random Forest already parallelizes inside each
# fit (estimator ``n_jobs=-1``), so window-level threads would oversubscribe it.
WINDOW_PARALLEL_MODEL_TAGS: frozenset[str] = frozenset({"mlp"})

# Rolling split: 120 x 6h = 30 days test, 60 days training lookback → a 90-day slice.
SPLIT: dict[str, object] = {
    "method": "rolling",
    "n_windows": 120,
    "test_window_hours": 6,
    "training_lookback_days": 60,
}
INPUT_SCHEMA = "oda.job.v0.2.0"


@dataclass(frozen=True)
class Tier:
    """A resource tier: which partition/cores/walltime a dataset's cells get."""

    name: str
    partition_kind: str  # "cpu" or "bigmem" — resolved to a real partition via SiteConfig
    cpus: int
    mem: str  # "0" = all memory on the node
    time: str  # benchmark walltime (Slurm D-HH:MM:SS or HH:MM:SS)
    embed_time: str  # embedding-job walltime
    embed_mem: str  # embedding-job memory (GPU nodes are shared, so request explicitly)


# Tiers keyed by rows in the 90-day benchmark window. Training-set size per rolling window
# scales with this, and so does peak memory (one-hot + SVD of high-cardinality text/id
# columns), which is why the largest datasets move to the big-memory partition. embed_mem
# scales with the embedded output (rows x embedding dim), which the embed builds in memory.
TIERS: tuple[Tier, ...] = (
    Tier("light", "cpu", 16, "0", "08:00:00", "02:00:00", "64G"),
    Tier("heavy", "cpu", 52, "0", "1-00:00:00", "04:00:00", "128G"),
    Tier("extreme", "bigmem", 64, "0", "2-00:00:00", "08:00:00", "256G"),
)
_LIGHT_MAX_ROWS = 300_000
_HEAVY_MAX_ROWS = 2_000_000


def tier_for_rows(window_rows: int) -> Tier:
    """Pick the resource tier for a dataset from its 90-day-window row count."""
    if window_rows < _LIGHT_MAX_ROWS:
        return TIERS[0]
    if window_rows < _HEAVY_MAX_ROWS:
        return TIERS[1]
    return TIERS[2]


def _model_tag(model_key: str) -> str:
    """Short, filename-safe tag for a model (``job_runtime_xgboost`` → ``xgboost``)."""
    return model_key.removeprefix("job_runtime_")


@dataclass
class Card:
    """The slice of a dataset card the planner needs."""

    dataset: str  # short name (card filename stem), e.g. "nlr_kestrel"
    window_rows: int
    window_start: str
    window_end: str
    healthy: bool
    system: str
    source_table: str  # canonical prepared parquet path (relative to repo root)
    card_path: Path


def load_cards(cards_dir: Path) -> list[Card]:
    """Load and parse every ``*.card.json`` under ``cards_dir`` (sorted by dataset name)."""
    cards: list[Card] = []
    for path in sorted(cards_dir.glob("*.card.json")):
        cards.append(_parse_card(path))
    if not cards:
        raise FileNotFoundError(f"no *.card.json files found under {cards_dir}")
    return cards


def _parse_card(path: Path) -> Card:
    payload = json.loads(path.read_text(encoding="utf-8"))
    window = payload.get("benchmark_window") or {}
    source = payload.get("source") or {}
    return Card(
        dataset=path.name.removesuffix(".card.json"),
        window_rows=int(window.get("n_rows", 0)),
        window_start=str(window.get("window_start", "")),
        window_end=str(window.get("window_end", "")),
        healthy=bool(window.get("healthy", False)),
        system=str(source.get("system", "")),
        source_table=str(source.get("table_path", "")),
        card_path=path,
    )


@dataclass
class Cell:
    """One benchmark job: a single model on a single dataset."""

    dataset: str
    model: str  # short tag, e.g. "xgboost"
    model_id: str  # "model.job_runtime_xgboost"
    tier: str
    partition: str
    cpus: int
    time: str
    table_path: str  # parquet the recipe reads, relative to repo_dir on the cluster
    recipe_path: str  # relative to the staging dir
    script_path: str  # relative to the staging dir
    needs_embed: bool
    job_name: str


@dataclass
class EmbedJob:
    """One GPU embedding job: embed a dataset's window for ``embedding_knn``."""

    dataset: str
    input_path: str  # windowed parquet, relative to repo_dir
    output_path: str  # embedded parquet, relative to repo_dir
    partition: str
    time: str
    mem: str
    script_path: str  # relative to the staging dir
    job_name: str


@dataclass
class Plan:
    """The full plan: every cell and embed job, plus the site/plan metadata."""

    plan_id: str
    host: str
    remote_base: str
    repo_dir: str
    models: list[str]
    cells: list[Cell] = field(default_factory=list)
    embeds: list[EmbedJob] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)


def _window_parquet(dataset: str) -> str:
    return f"data/windows/{dataset}/data.parquet"


def _embedded_parquet(dataset: str) -> str:
    return f"data/embeddings/{dataset}/data.parquet"


def build_recipe(
    dataset: str,
    model_key: str,
    table_path: str,
    output_dir: str,
    *,
    window_n_jobs: int | None = None,
) -> dict:
    """Build a benchmark recipe payload (``oda.recipe.v0.1.0``) for one cell.

    ``window_n_jobs`` (when set) is added to the split so the model runs its independent
    per-window fits across that many threads — used to spread MLP over the cell's cores.
    """
    split = dict(SPLIT)
    if window_n_jobs is not None:
        split["window_n_jobs"] = window_n_jobs
    return {
        "recipe_id": f"recipe.job_runtime.{dataset}_{_model_tag(model_key)}",
        "problem_domain": ["job-runtime-prediction"],
        "schema_version": INPUT_SCHEMA,
        "dataset": {"id": dataset, "table_path": table_path},
        "model": {"id": f"model.{model_key}", "version": "0.1.0"},
        "metrics": [
            {"name": "mae", "target": "runtime_seconds"},
            {"name": "rmse", "target": "runtime_seconds"},
        ],
        "split": split,
        "run": {"output_dir": output_dir, "overwrite": True},
    }


def build_plan(
    cards: list[Card],
    site: SiteConfig,
    *,
    plan_id: str,
    models: tuple[str, ...] = RUNTIME_MODELS,
    include_unhealthy: bool = False,
) -> Plan:
    """Build the in-memory plan (no files written)."""
    plan = Plan(
        plan_id=plan_id,
        host=site.host,
        remote_base=site.remote_base,
        repo_dir=site.repo_dir,
        models=list(models),
    )
    embed_wanted = EMBEDDING_MODEL in models
    for card in cards:
        if not card.healthy and not include_unhealthy:
            plan.skipped.append({"dataset": card.dataset, "reason": "window flagged unhealthy"})
            continue
        tier = tier_for_rows(card.window_rows)
        partition = site.partition(tier.partition_kind)
        window_pq = _window_parquet(card.dataset)

        for model_key in models:
            tag = _model_tag(model_key)
            needs_embed = model_key == EMBEDDING_MODEL
            table_path = _embedded_parquet(card.dataset) if needs_embed else window_pq
            plan.cells.append(
                Cell(
                    dataset=card.dataset,
                    model=tag,
                    model_id=f"model.{model_key}",
                    tier=tier.name,
                    partition=partition,
                    cpus=tier.cpus,
                    time=tier.time,
                    table_path=table_path,
                    recipe_path=f"recipes/{card.dataset}__{tag}.yml",
                    script_path=f"scripts/bench__{card.dataset}__{tag}.sbatch",
                    needs_embed=needs_embed,
                    job_name=f"b.{card.dataset}.{tag}",
                )
            )

        if embed_wanted:
            plan.embeds.append(
                EmbedJob(
                    dataset=card.dataset,
                    input_path=window_pq,
                    output_path=_embedded_parquet(card.dataset),
                    partition=site.partition("gpu"),
                    time=tier.embed_time,
                    mem=tier.embed_mem,
                    script_path=f"scripts/embed__{card.dataset}.sbatch",
                    job_name=f"e.{card.dataset}",
                )
            )
    return plan


# --- template rendering -------------------------------------------------------------

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def render_template(text: str, mapping: dict[str, object]) -> str:
    """Fill ``{{key}}`` placeholders; raise if any remain unfilled."""
    rendered = _PLACEHOLDER.sub(lambda m: str(mapping[m.group(1)]), _known_only(text, mapping))
    leftover = sorted(set(_PLACEHOLDER.findall(rendered)))
    if leftover:
        raise KeyError(f"unfilled template placeholders: {leftover}")
    return rendered


def _known_only(text: str, mapping: dict[str, object]) -> str:
    # Surface unknown placeholders as a clear error rather than a KeyError deep in re.sub.
    unknown = sorted({k for k in _PLACEHOLDER.findall(text) if k not in mapping})
    if unknown:
        raise KeyError(f"template references unknown keys not in mapping: {unknown}")
    return text


def _load_template(name: str) -> str:
    return (_TEMPLATES_DIR / name).read_text(encoding="utf-8")


def _bench_script(cell: Cell, site: SiteConfig, staging_remote: str) -> str:
    return render_template(
        _load_template("benchmark.sbatch.template"),
        {
            "account": site.account,
            "partition": cell.partition,
            "time": cell.time,
            "cpus": cell.cpus,
            "mem": _mem_for(cell),
            "job_name": cell.job_name,
            "log": f"{site.repo_dir}/logs/{cell.job_name}.%j.out",
            "model_id": cell.model_id,
            "dataset_id": cell.dataset,
            "window": "90d",
            "tier": cell.tier,
            "workdir": site.repo_dir,
            "hpc_oda": site.hpc_oda,
            "recipe": f"{staging_remote}/{cell.recipe_path}",
        },
    )


def _mem_for(cell: Cell) -> str:
    for tier in TIERS:
        if tier.name == cell.tier:
            return tier.mem
    return "0"


def _embed_script(job: EmbedJob, site: SiteConfig) -> str:
    return render_template(
        _load_template("embed.sbatch.template"),
        {
            "account": site.account,
            "partition": job.partition,
            "time": job.time,
            "mem": job.mem,
            "cpus": 16,
            "gres": site.gpu_gres,
            "job_name": job.job_name,
            "log": f"{site.repo_dir}/logs/{job.job_name}.%j.out",
            "dataset_id": job.dataset,
            "window": "90d",
            "model": site.embedding_model,
            "workdir": site.repo_dir,
            "hpc_oda": site.hpc_oda,
            "input": job.input_path,
            "output": job.output_path,
            "cache_dir": site.cache_dir,
            "hf_home": site.hf_home,
        },
    )


def write_plan(plan: Plan, staging_dir: Path, site: SiteConfig) -> Path:
    """Write recipes, sbatch scripts, and ``plan.json`` under ``staging_dir``.

    ``staging_dir`` is the local staging root (``.hpc_oda/bench-matrix/<plan_id>/``). The
    generated sbatch scripts reference the *remote* staging path (the same relative layout
    under ``{repo_dir}/.hpc_oda/bench-matrix/<plan_id>``) since they run on the cluster.
    """
    import yaml

    staging_remote = f"{site.repo_dir}/.hpc_oda/bench-matrix/{plan.plan_id}"
    recipes_dir = staging_dir / "recipes"
    scripts_dir = staging_dir / "scripts"
    recipes_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)

    for cell in plan.cells:
        recipe = build_recipe(
            cell.dataset,
            f"job_runtime_{cell.model}",
            cell.table_path,
            output_dir=f"runs/{cell.dataset}/{cell.model}",
            window_n_jobs=(cell.cpus if cell.model in WINDOW_PARALLEL_MODEL_TAGS else None),
        )
        (staging_dir / cell.recipe_path).write_text(
            yaml.safe_dump(recipe, sort_keys=False), encoding="utf-8"
        )
        (staging_dir / cell.script_path).write_text(
            _bench_script(cell, site, staging_remote), encoding="utf-8"
        )

    for job in plan.embeds:
        (staging_dir / job.script_path).write_text(_embed_script(job, site), encoding="utf-8")

    plan_json = {
        "plan_id": plan.plan_id,
        "host": plan.host,
        "remote_base": plan.remote_base,
        "repo_dir": plan.repo_dir,
        "staging_remote": staging_remote,
        "models": plan.models,
        "n_cells": len(plan.cells),
        "n_embeds": len(plan.embeds),
        "cells": [asdict(c) for c in plan.cells],
        "embeds": [asdict(e) for e in plan.embeds],
        "skipped": plan.skipped,
    }
    plan_path = staging_dir / "plan.json"
    plan_path.write_text(json.dumps(plan_json, indent=2) + "\n", encoding="utf-8")
    return plan_path
