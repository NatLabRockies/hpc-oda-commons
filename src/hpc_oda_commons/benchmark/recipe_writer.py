"""Write every model's benchmark recipes for one dataset (#255).

A dataset you bring is benchmarked the way the published ones are, so its results sit on
the same leaderboard tables. The recipes come from the code and files the benchmark already
uses, never a hand-kept copy:

- **runtime:** the HPC matrix's recipe builder (``bench-matrix``), on the leaderboard's
  runtime protocol (``tracks.RUNTIME_PROTOCOL``) and each lookback arm the dataset's card
  can express. The recipe declares the card's window, history included, so the run reads
  the rows a sliced table would hold.
- **power:** the bundled F-DATA power recipes, one per model and target, with this
  dataset's table and window put in. Every model's split is the same on every bundled
  dataset, and the leaderboard checks a power run against its recipe's split.

Models that read a job embedding (``EMBEDDING_MODELS``) read an embedded table, unless the
prepared table already has an ``embedding`` column.
"""

from __future__ import annotations

import copy
import importlib.resources as ir
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from hpc_oda_commons.benchmark.recipes import load_recipe, validate_recipe
from hpc_oda_commons.benchmark.tracks import RUNTIME_LOOKBACKS, RUNTIME_PROTOCOL
from hpc_oda_commons.benchmarking.hpc.matrix import (
    RUNTIME_MODELS,
    build_recipe,
    lookback_arms_for,
    slice_extension_for,
)
from hpc_oda_commons.benchmarking.hpc.slice import effective_start
from hpc_oda_commons.datasets.descriptor import Descriptor

# The models whose recipes read a job ``embedding`` column: on the bundled datasets, these
# are the ones that read the embedded table (a test keeps the two in step).
EMBEDDING_MODELS: frozenset[str] = frozenset({"model.embedding_knn", "model.uopc"})
# The power targets the leaderboard ranks, and the bundled recipe suffix for each.
POWER_TARGETS: dict[str, str] = {"avgpcon_per_node": "avg", "maxpcon_per_node": "peak"}
# The embedding model and format the benchmark embeds with (see the bundled recipes).
EMBED_MODEL = "microsoft/harrier-oss-v1-0.6b"


@dataclass
class Written:
    """What :func:`write_recipes` wrote, and the commands that go with it: ``steps`` build
    the embedded tables, ``ceilings`` compute the error ceilings headroom is measured on."""

    recipes: list[Path] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    ceilings: list[str] = field(default_factory=list)


def _power_templates() -> dict[tuple[str, str], dict[str, Any]]:
    """The bundled F-DATA power recipes, by (model id, target)."""
    root = Path(str(ir.files("hpc_oda_commons") / "recipes" / "job-power"))
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for suffix in POWER_TARGETS.values():
        for path in sorted(root.glob(f"*_rolling_{suffix}.yml")):
            recipe = load_recipe(path)
            out[(recipe["model"]["id"], recipe["metrics"][0]["target"])] = recipe
    return out


def _dump(recipe: dict[str, Any], path: Path, header: str) -> Path:
    validate_recipe(recipe, path=path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(recipe, sort_keys=False)
    path.write_text(f"# {header}\n# Written by `hpc-oda recipes write` (#255).\n\n{body}")
    return path


def _wanted(model_id: str, models: Sequence[str]) -> bool:
    return not models or model_id in models or model_id.removeprefix("model.") in models


def write_recipes(
    descriptor: Descriptor,
    out_dir: Path,
    *,
    card: Any | None = None,
    window: dict[str, str] | None = None,
    require_nonnull: Sequence[str] = (),
    runs_dir: str = "runs",
    models: Sequence[str] = (),
    benchmark_dir: str = "benchmark/datasets",
) -> Written:
    """Write the runtime and power recipes for ``descriptor``'s dataset into ``out_dir``.

    ``card`` is the dataset's runtime card (``matrix.load_card``); without it no runtime
    recipes are written. ``window`` and ``require_nonnull`` are what the power recipes
    read, as a recipe declares them; left out, they read the whole prepared table.
    ``models`` limits the models written, by id or short name. The ceiling commands write
    into ``benchmark_dir``, beside the runtime card.
    """
    name = descriptor.dataset_id.removeprefix("dataset.")
    (target,) = descriptor.targets[:1]
    table = target.output_path
    has_embedding = "embedding" in target.mapping
    written = Written()

    if card is None:
        written.skipped.append("runtime: no runtime card (run `hpc-oda datasets characterize`)")
    elif "runtime_seconds" not in descriptor.target_columns:
        written.skipped.append("runtime: the descriptor maps no runtime_seconds")
    else:
        start = effective_start(card.window_start, slice_extension_for(card))
        runtime_window = {"start": start, "end": card.window_end}
        embedded = table if has_embedding else f"data/embeddings/{name}/data.parquet"
        for model in RUNTIME_MODELS:
            model_id = f"model.{model}"
            if not _wanted(model_id, models):
                continue
            for lookback in lookback_arms_for(card, RUNTIME_LOOKBACKS):
                reads = embedded if model_id in EMBEDDING_MODELS else table
                recipe = build_recipe(
                    name,
                    model,
                    reads,
                    f"{runs_dir}/{name}/{model}/lb{lookback}d",
                    training_lookback_days=lookback,
                    n_windows=RUNTIME_PROTOCOL["n_windows"],
                )
                recipe["dataset"]["window"] = dict(runtime_window)
                written.recipes.append(
                    _dump(
                        recipe,
                        out_dir / "runtime" / f"{model}_lb{lookback}d.yml",
                        f"{model_id} predicting job runtime on {name}, {lookback}-day lookback.",
                    )
                )
        written.ceilings.append(
            f"hpc-oda datasets ceiling {table} --start {start} --end {card.window_end} "
            f"--dataset-id {descriptor.dataset_id} --n-windows {RUNTIME_PROTOCOL['n_windows']} "
            f"--skip-windows 20 --out {benchmark_dir}/{name}.ceiling.json"
        )
        if not has_embedding and _wanted("model.embedding_knn", models):
            written.steps += [
                f"hpc-oda datasets slice {table} --start {start} --end {card.window_end} "
                f"--out data/windows/{name}/data.parquet",
                f"hpc-oda embed data/windows/{name}/data.parquet --out {embedded} "
                f"--model {EMBED_MODEL} --format prose",
            ]

    targets = [t for t in POWER_TARGETS if t in descriptor.target_columns]
    if not targets:
        written.skipped.append("power: the descriptor maps no per-node power target")
    power_embedded = table if has_embedding else f"data/embeddings/{name}_power/data.parquet"
    templates = _power_templates()
    for power_target in targets:
        suffix = POWER_TARGETS[power_target]
        for (model_id, template_target), template in sorted(templates.items()):
            if template_target != power_target or not _wanted(model_id, models):
                continue
            model = model_id.removeprefix("model.")
            recipe = copy.deepcopy(template)
            recipe["recipe_id"] = f"recipe.job_power.{model}_rolling_{suffix}_{name}"
            dataset: dict[str, Any] = {
                "id": name,
                "table_path": power_embedded if model_id in EMBEDDING_MODELS else table,
            }
            if window:
                dataset["window"] = dict(window)
            if require_nonnull:
                dataset["require_nonnull"] = list(require_nonnull)
            recipe["dataset"] = dataset
            recipe["run"] = {
                "output_dir": f"{runs_dir}/{name}/{model}/{suffix}",
                "overwrite": False,
            }
            written.recipes.append(
                _dump(
                    recipe,
                    out_dir / "power" / f"{model}_{suffix}.yml",
                    f"{model_id} predicting {power_target} on {name}, on the power protocol.",
                )
            )
    if targets and not has_embedding and any(_wanted(m, models) for m in EMBEDDING_MODELS):
        source = table
        if window:
            # A slice keeps every job overlapping the days, a superset of a window by submit
            # time; the recipes' own window then reads exactly theirs.
            source = f"data/windows/{name}_power/data.parquet"
            written.steps.append(
                f"hpc-oda datasets slice {table} --start {window['start']} "
                f"--end {window['end']} --out {source}"
            )
        written.steps.append(
            f"hpc-oda embed {source} --out {power_embedded} --model {EMBED_MODEL} --format prose"
        )
    reads = ""
    if window:
        reads = f" --start {window['start']} --end {window['end']}"
        if window.get("by"):
            reads += f" --by {window['by']}"
    reads += "".join(f" --require-nonnull {c}" for c in require_nonnull)
    for power_target in targets:
        # On the table the embedding models read: its signature holds every input any model
        # reads (docs/benchmarking/power/methodology.md); a field it lacks is left out.
        written.ceilings.append(
            f"hpc-oda datasets ceiling {power_embedded}{reads} --target {power_target} "
            f"--dataset-id {descriptor.dataset_id} --n-windows 89 --test-window-hours 24 "
            "--skip-windows 0 --extra-feature embedding --extra-feature freq_req "
            f"--out {benchmark_dir}/{name}.{power_target}.ceiling.json"
        )
    return written
