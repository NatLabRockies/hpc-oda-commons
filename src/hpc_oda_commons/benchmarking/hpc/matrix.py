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
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from hpc_oda_commons.benchmarking.characterize import DEFAULT_TEST_DAYS
from hpc_oda_commons.benchmarking.hpc.config import SiteConfig

# --- Benchmark configuration (the agreed methodology; see docs/benchmarking/methodology.md) ---

# Six runtime-prediction models. ``job_power_uopc`` is power prediction — out of scope.
RUNTIME_MODELS: tuple[str, ...] = (
    "job_runtime_baseline",
    # Trivial but strong: memorises the median runtime of same-signature past jobs. It beat
    # all six fitted models on 9 of 20 datasets in the 2026-08-25 fleet run (#171), which the
    # global-mean baseline alone could never have revealed. Measured cost: ~51s on lassen
    # (302k rows), scaling roughly linearly -- a fraction of a fitted cell on the heavy
    # datasets, comparable on the light ones where every cell is cheap anyway.
    "job_runtime_signature_memorizer",
    "job_runtime_tfidf_knn",
    "job_runtime_random_forest",
    "job_runtime_xgboost",
    "job_runtime_moe_xgboost",
    "job_runtime_mlp",
    "job_runtime_embedding_knn",
)
# The model whose recipe reads the *embedded* parquet (requires a prior GPU embed pass).
EMBEDDING_MODEL: str = "job_runtime_embedding_knn"

# Models that run their independent per-window fits concurrently (via ``window_n_jobs``).
# MLP and TF-IDF kNN both do serial single-threaded per-window work that dominates on large
# corpora. MoE XGBoost joins them on measurement: window-parallel beat estimator-parallel
# 7:52 vs 11:36 on a 532k-row slice at equal cores, with the two arms' MAE agreeing to 0.02%
# (float summation order under threading -- see docs/known-issues.md #2). Random Forest
# already parallelizes inside each fit (``n_jobs=-1``), so window threads would oversubscribe
# it.
WINDOW_PARALLEL_MODEL_TAGS: frozenset[str] = frozenset({"mlp", "tfidf_knn", "moe_xgboost"})

# Rolling split: 120 x 6h = 30 days test, 120 days training lookback.
#
# The lookback exceeds the cards' ``train_days`` (60), so the earliest rolling windows would
# train on truncated history unless the slice reaches further back than the card window. That
# shortfall is derived per dataset by ``bench-matrix slice`` rather than passed by hand -- see
# ``Card.train_days`` -- so the slice and this split cannot drift apart (#143, #145).
# The span of history a slice carries before its window's test region -- equivalently, the
# longest lookback a slice can express. Kept separate from ``training_lookback_days`` (#170):
# this is how much we CUT, that is how much a model USES. While they were the same number, a
# per-dataset lookback meant re-slicing that dataset.
#
# Set equal to the default lookback, so existing slices remain exactly as they are. Raising it
# is how you enable lookbacks longer than 120 days; that requires a re-slice, but does not
# invalidate results already measured -- a 120-day lookback selects the same training rows no
# matter how much extra history sits in the file.
SLICE_HISTORY_DAYS: int = 120

# The benchmark sweeps the training lookback rather than fixing it. Measured, the fixed 120
# days was best for only 6 of 20 datasets, and the cost of the wrong value is not marginal:
# on lassen, XGBoost scores 3,346 at 10 days against 4,233 at 120 -- and at 10 days it beats
# every model the fleet ran at 120, which is to say the parameter, not the model, decided
# that dataset (#170).
#
# So every model competes at every lookback and the comparison is about the model. Cost is
# ~1.6x, not 3x: a short lookback trains on proportionally less history, so a 10d arm costs
# roughly a fifth of a 120d one.
#
# Choosing a winner per cell is left to analysis, deliberately. Picking each model's best arm
# by test MAE would be selecting on the test set -- a noisier model gets three draws at the
# same target -- so the honest selection (tune on early windows, score on late ones) is done
# downstream from the per-window metrics these runs already emit.
LOOKBACK_ARMS: tuple[int, ...] = (10, 30, 120)

# ``n_windows`` is the default for a card that states no evaluation length; the planner
# derives it per dataset from the card's ``test_days`` (#191). 360 x 6h = the 90-day
# evaluation the cards now target.
SPLIT: dict[str, object] = {
    "method": "rolling",
    "n_windows": 360,
    "test_window_hours": 6,
    "training_lookback_days": 120,
}

# Per-model split keys layered onto SPLIT by ``build_recipe``. Any model not named here runs
# the shared defaults. This is a table rather than branching inside ``build_recipe`` so that
# "which configuration did cell X run?" stays answerable by reading one place.
MODEL_SPLIT_OVERRIDES: dict[str, dict[str, object]] = {
    # Fit the metric the leaderboard ranks on. Runtimes are heavy-tailed (Kestrel p99/p50
    # ~1,200x), so under squared error a handful of week-long jobs own the gradient (#138).
    # Applied to BOTH XGBoost variants deliberately: if only the MoE fitted absolute error,
    # its margin over plain XGBoost would bundle a -2.6% effect that has nothing to do with
    # the mixture.
    "job_runtime_xgboost": {"objective": "reg:absoluteerror"},
    "job_runtime_moe_xgboost": {
        "objective": "reg:absoluteerror",
        # Route by requested wallclock alone. Per-user experts measured net harmful: on the
        # rows they claimed, pooling was 3.0% better (#134). Expressible since #141.
        "enable_power_users": False,
        # Recency weighting, ~2-week half-life (#136).
        "time_decay_rate": 0.05,
    },
}
INPUT_SCHEMA = "oda.job.v0.2.0"


# --- MEMORY NOTE ---------------------------------------------------------------------
# Window workers are a memory knob, not a speed knob: each concurrent fit holds its own
# preprocessed training set, so peak memory is roughly (rows held) + workers x (per-window
# cost). Cores are free here (exclusive nodes); memory is the fixed resource.
#
# Two measurements on a 250 GB / 104-core node bound the range:
#   * 532k-row slice, 52 workers  -> 14.5 GB peak. Small data is cheap at any worker count.
#   * 13.9M-row slice, 1 worker   -> 110 GB peak (20.6 GB of it just holding the rows as
#     Python objects). Per-window cost ~90 GB, so 3 concurrent windows would exhaust the
#     node.
#
# Those two points come from different datasets with different column cardinalities, so
# they bound the behaviour rather than fitting a curve -- the values below are chosen
# conservatively within those bounds, not interpolated. An OOM costs the whole cell; an
# unused worker slot costs nothing.
_LIGHT_WORKERS = 32
_HEAVY_WORKERS = 16
_EXTREME_WORKERS = 4

# Slices larger than this are not attempted. At 13.9M rows the per-window cost alone is
# ~90 GB, which leaves no room for concurrency, and the cell needs >24h serially -- a cell
# that can only run one window at a time for a day is not a benchmark we can schedule at
# scale. Such datasets are skipped and reported rather than moved to a bigger node.
MAX_NODE_ROWS = 8_000_000


@dataclass(frozen=True)
class Tier:
    """A resource tier: the walltime and window-worker count a dataset's cells get.

    Deliberately no core count. Benchmark partitions are allocated whole
    (``OverSubscribe=EXCLUSIVE``), so a cell holds every core on its node no matter what
    ``--cpus-per-task`` says; asking for fewer only left cores idle. The scarce resource is
    **memory**, and what consumes it is concurrent per-window fits — hence ``window_workers``
    rather than cores.
    """

    name: str
    partition_kind: str  # resolved to a real partition via SiteConfig
    window_workers: int  # ``window_n_jobs`` for window-parallel models; memory-bounded
    mem: str  # "0" = all memory on the node
    time: str  # benchmark walltime (Slurm D-HH:MM:SS or HH:MM:SS)
    embed_time: str  # embedding-job walltime
    embed_mem: str  # embedding-job memory (GPU nodes are shared, so request explicitly)


# Tiers keyed by rows in the slice a cell actually loads. Training-set size per rolling
# window scales with that, and so does peak memory (one-hot + SVD of high-cardinality
# text/id columns, times the number of windows fitted concurrently). embed_mem scales with
# the embedded output (rows x embedding dim), which the embed builds in memory.
#
# Everything runs on the ordinary CPU partition. The big-memory partition is deliberately
# unused: it is a small pool, and a benchmark cell that only fits there is a cell whose
# memory profile we do not understand well enough to run at scale. Datasets that cannot fit
# an ordinary node are skipped and reported, not quietly moved somewhere bigger.
#
# ``window_workers`` is set from measurement, not from the core count -- see MEMORY NOTE.
TIERS: tuple[Tier, ...] = (
    Tier("light", "cpu", _LIGHT_WORKERS, "0", "08:00:00", "02:00:00", "64G"),
    Tier("heavy", "cpu", _HEAVY_WORKERS, "0", "1-00:00:00", "04:00:00", "128G"),
    Tier("extreme", "cpu", _EXTREME_WORKERS, "0", "2-00:00:00", "08:00:00", "256G"),
)
_LIGHT_MAX_ROWS = 300_000
_HEAVY_MAX_ROWS = 2_000_000


def tier_for_rows(window_rows: int) -> Tier:
    """Pick the resource tier for a dataset from the row count of the slice it loads."""
    if window_rows < _LIGHT_MAX_ROWS:
        return TIERS[0]
    if window_rows < _HEAVY_MAX_ROWS:
        return TIERS[1]
    return TIERS[2]


def fits_a_node(window_rows: int) -> bool:
    """Whether a dataset's slice is small enough to benchmark on one ordinary node."""
    return window_rows <= MAX_NODE_ROWS


def slice_extension_for(card: Card) -> int:
    """Days a card's slice reaches back beyond its window. Fixed, not derived (#170).

    This used to be ``training_lookback_days - train_days``, which tied *how much history we
    cut* to *how much a model uses*. That coupling made the lookback impossible to vary per
    dataset without re-slicing, and the lookback is worth varying: on ``lassen``, XGBoost
    scores 3,304 at a 10-day lookback against 4,434 at 120 -- a 25% swing that changed which
    model won the dataset.

    So the two are separated. The slice cuts a generous fixed span; a model's lookback
    selects within it and may be anything up to the slice. A short lookback simply leaves
    history unused, which costs disk rather than correctness.

    ``train_days`` still shortens the extension when the card window already covers part of
    the span, so nothing is cut twice.

    The budget is the card's since #191. ``SLICE_HISTORY_DAYS`` remains the default for cards
    that predate the field, so an unregenerated card slices exactly as it did.
    """
    return max(0, card.history_days - card.train_days)


def lookback_arms_for(card: Card, arms: Sequence[int] = LOOKBACK_ARMS) -> tuple[int, ...]:
    """The arms a card can actually express, each capped at its history budget.

    An arm longer than the history behind the window is not the arm it claims to be. On
    ``atlas_opentrinity`` -- 80 days of source in total -- the "120d" arm trained on the ~80
    that existed and still reported itself as 120d, which is a wrong number rather than a
    weak one (#191).

    Capping renames the arm instead of dropping it: the measurement is still wanted, under a
    label that matches what it did. Arms that collapse onto each other are de-duplicated, so
    a card with a 30-day budget runs two arms rather than the same arm twice.
    """
    return tuple(sorted({min(int(arm), card.history_days) for arm in arms}))


def n_windows_for(card: Card, test_window_hours: int | None = None) -> int:
    """How many rolling windows cover the card's evaluation region."""
    hours = int(test_window_hours or SPLIT["test_window_hours"])  # type: ignore[arg-type]
    return max(1, (card.test_days * 24) // hours)


def _model_tag(model_key: str) -> str:
    """Short, filename-safe tag for a model (``job_runtime_xgboost`` → ``xgboost``)."""
    return model_key.removeprefix("job_runtime_")


class ModelSelectionError(ValueError):
    """Raised when a requested exclusion names no model in the matrix."""


def select_models(exclude: Sequence[str] = ()) -> tuple[str, ...]:
    """``RUNTIME_MODELS`` minus ``exclude``, preserving the roster's order.

    Names may be full model keys (``job_runtime_mlp``) or the short tags that appear in
    plan output and ``submit --only-model`` (``mlp``). Whether a model belongs to the
    benchmark and whether it earns its wall-clock in a *given run* are different
    questions; this answers the second without editing ``RUNTIME_MODELS``, which answers
    the first.

    An unknown name is an error rather than a no-op: a typo'd exclusion that quietly
    planned the full matrix is exactly the surprise this exists to prevent (#156).
    """
    by_name = {m: m for m in RUNTIME_MODELS}
    by_name.update({_model_tag(m): m for m in RUNTIME_MODELS})

    unknown = sorted({name for name in exclude if name not in by_name})
    if unknown:
        raise ModelSelectionError(
            f"unknown model(s) to exclude: {', '.join(unknown)}. "
            f"Known models: {', '.join(sorted(by_name))}."
        )

    dropped = {by_name[name] for name in exclude}
    kept = tuple(m for m in RUNTIME_MODELS if m not in dropped)
    if not kept:
        raise ModelSelectionError("every model was excluded — nothing left to plan.")
    return kept


@dataclass
class Card:
    """The slice of a dataset card the planner needs."""

    dataset: str  # short name (card filename stem), e.g. "nlr_kestrel"
    window_rows: int  # rows in the card's own window (submit-based)
    window_start: str
    window_end: str
    train_days: int  # the card rule's training span; 0 when the card does not state one
    healthy: bool
    system: str
    source_table: str  # canonical prepared parquet path (relative to repo root)
    card_path: Path
    # The history budget and evaluation length the card declares. Both were module constants
    # until #191; one value did not suit every source, and a card whose source could not
    # afford the constant received less without saying so.
    history_days: int = SLICE_HISTORY_DAYS
    test_days: int = DEFAULT_TEST_DAYS
    sliced_rows: int | None = None  # rows in the slice on disk, from its slice.json

    @property
    def effective_rows(self) -> int:
        """Rows a cell will actually load: the slice on disk if we have it, else the card's.

        These diverge whenever the split needs more history than the card window holds --
        which, since #145, is always. Sizing from the card would under-provision every cell
        by the width of the lookback extension.
        """
        return self.sliced_rows if self.sliced_rows is not None else self.window_rows


def load_cards(cards_dir: Path, windows_dir: Path | None = None) -> list[Card]:
    """Load every ``*.card.json`` under ``cards_dir`` (sorted by dataset name).

    When ``windows_dir`` is given, each card is annotated with the row count from the
    matching ``<dataset>/slice.json``, so resource sizing follows the data a cell loads
    rather than the card's own (narrower) window. Missing sidecars are not an error --
    the card's count is then the best available estimate.
    """
    cards: list[Card] = []
    for path in sorted(cards_dir.glob("*.card.json")):
        card = _parse_card(path)
        if windows_dir is not None:
            card = replace(card, sliced_rows=_sliced_rows(windows_dir, card.dataset))
        cards.append(card)
    if not cards:
        raise FileNotFoundError(f"no *.card.json files found under {cards_dir}")
    return cards


def _sliced_rows(windows_dir: Path, dataset: str) -> int | None:
    sidecar = windows_dir / dataset / "slice.json"
    if not sidecar.exists():
        return None
    try:
        return int(json.loads(sidecar.read_text(encoding="utf-8"))["rows"])
    except (ValueError, KeyError, OSError):
        return None


def _parse_card(path: Path) -> Card:
    payload = json.loads(path.read_text(encoding="utf-8"))
    window = payload.get("benchmark_window") or {}
    source = payload.get("source") or {}
    return Card(
        dataset=path.name.removesuffix(".card.json"),
        window_rows=int(window.get("n_rows", 0)),
        window_start=str(window.get("window_start", "")),
        window_end=str(window.get("window_end", "")),
        # A card with no stated rule reports 0, which makes the derived slice extension the
        # full lookback -- wider than needed, never narrower.
        train_days=int((window.get("rule") or {}).get("train_days", 0)),
        # Cards written before #191 state ``test_days`` (30) but not ``history_days``, so the
        # old constant is the default for the latter and such a card plans exactly as it used
        # to: 30 days of evaluation against a 120-day budget.
        history_days=int((window.get("rule") or {}).get("history_days", SLICE_HISTORY_DAYS)),
        test_days=int((window.get("rule") or {}).get("test_days", DEFAULT_TEST_DAYS)),
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
    window_workers: int  # window_n_jobs for window-parallel models (memory-bounded)
    time: str
    table_path: str  # parquet the recipe reads, relative to repo_dir on the cluster
    recipe_path: str  # relative to the staging dir
    script_path: str  # relative to the staging dir
    needs_embed: bool
    job_name: str
    training_lookback_days: int = int(SPLIT["training_lookback_days"])  # type: ignore[arg-type]
    n_windows: int = int(SPLIT["n_windows"])  # type: ignore[arg-type]


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
    lookbacks: list[int]
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
    training_lookback_days: int | None = None,
    n_windows: int | None = None,
) -> dict:
    """Build a benchmark recipe payload (``oda.recipe.v0.1.0``) for one cell.

    ``window_n_jobs`` (when set) is added to the split so the model runs its independent
    per-window fits across that many threads — used to spread MLP over the cell's cores.

    Any ``MODEL_SPLIT_OVERRIDES`` entry for ``model_key`` is layered on top of the shared
    ``SPLIT``, so a model can carry the configuration it was actually measured in.
    """
    split = dict(SPLIT)
    if training_lookback_days is not None:
        split["training_lookback_days"] = int(training_lookback_days)
    if n_windows is not None:
        split["n_windows"] = int(n_windows)
    split.update(MODEL_SPLIT_OVERRIDES.get(model_key, {}))
    if window_n_jobs is not None:
        split["window_n_jobs"] = window_n_jobs
    return {
        # The arm is part of the identity: three lookbacks of one model are three cells, and
        # anything keyed on the recipe id downstream would otherwise merge them (#170).
        "recipe_id": (
            f"recipe.job_runtime.{dataset}_{_model_tag(model_key)}"
            f"_lb{int(split['training_lookback_days'])}d"
        ),
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
    lookbacks: tuple[int, ...] = LOOKBACK_ARMS,
    include_unhealthy: bool = False,
) -> Plan:
    """Build the in-memory plan (no files written)."""
    plan = Plan(
        plan_id=plan_id,
        host=site.host,
        remote_base=site.remote_base,
        repo_dir=site.repo_dir,
        models=list(models),
        lookbacks=list(lookbacks),
    )
    embed_wanted = EMBEDDING_MODEL in models
    for card in cards:
        if not card.healthy and not include_unhealthy:
            plan.skipped.append({"dataset": card.dataset, "reason": "window flagged unhealthy"})
            continue
        if not fits_a_node(card.effective_rows):
            plan.skipped.append(
                {
                    "dataset": card.dataset,
                    "reason": (
                        f"slice of {card.effective_rows:,} rows exceeds what one node can "
                        f"hold ({MAX_NODE_ROWS:,}); big-memory nodes are not used"
                    ),
                }
            )
            continue
        tier = tier_for_rows(card.effective_rows)
        partition = site.partition(tier.partition_kind)
        window_pq = _window_parquet(card.dataset)

        for model_key in models:
            tag = _model_tag(model_key)
            needs_embed = model_key == EMBEDDING_MODEL
            table_path = _embedded_parquet(card.dataset) if needs_embed else window_pq
            for lookback in lookback_arms_for(card, lookbacks):
                stem = f"{card.dataset}__{tag}__lb{lookback}d"
                plan.cells.append(
                    Cell(
                        dataset=card.dataset,
                        model=tag,
                        model_id=f"model.{model_key}",
                        tier=tier.name,
                        partition=partition,
                        window_workers=tier.window_workers,
                        time=tier.time,
                        table_path=table_path,
                        recipe_path=f"recipes/{stem}.yml",
                        script_path=f"scripts/bench__{stem}.sbatch",
                        needs_embed=needs_embed,
                        job_name=f"b.{card.dataset}.{tag}.lb{lookback}d",
                        training_lookback_days=lookback,
                        n_windows=n_windows_for(card),
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
            output_dir=f"runs/{cell.dataset}/{cell.model}/lb{cell.training_lookback_days}d",
            window_n_jobs=(
                cell.window_workers if cell.model in WINDOW_PARALLEL_MODEL_TAGS else None
            ),
            training_lookback_days=cell.training_lookback_days,
            n_windows=cell.n_windows,
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
        "lookbacks": plan.lookbacks,
        "n_cells": len(plan.cells),
        "n_embeds": len(plan.embeds),
        "cells": [asdict(c) for c in plan.cells],
        "embeds": [asdict(e) for e in plan.embeds],
        "skipped": plan.skipped,
    }
    plan_path = staging_dir / "plan.json"
    plan_path.write_text(json.dumps(plan_json, indent=2) + "\n", encoding="utf-8")
    return plan_path
