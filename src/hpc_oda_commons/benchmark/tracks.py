"""One leaderboard per prediction target: a row per model, a column per dataset (#237).

Raw MAE is not comparable across datasets -- a Fugaku node draws ~90 W and a Kestrel node
~590 W, and runtime errors differ as much between machines -- so a cell reports **headroom
captured**: (baseline MAE - model MAE) / (baseline MAE - floor MAE). The baseline is the
window-mean model on the same dataset and windows, the floor the dataset's error ceiling
(``docs/benchmarking/datasets/*.ceiling.json``). Within a dataset it orders models exactly as
MAE does; across datasets it is on one scale, so it can be averaged.

Only bundles from a track's own benchmark protocol count. Everything else -- the UoPC paper
reproduction, smoke runs, ad hoc variants, a bundle whose recipe has since changed -- is
listed with the reason it was left out, never silently dropped.

Runtime shows MAE without headroom for now: its ceilings were computed on an older protocol
than the one its cells run, so the two would be measured on different rows (#238).
"""

from __future__ import annotations

import importlib.resources as ir
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hpc_oda_commons.benchmark.arm_selection import (
    DEFAULT_BURN_IN,
    Arm,
    ArmSelectionError,
    common_scored_indices,
    derive_arm_keys,
    pooled_metric,
    walk_forward,
)

BASELINE_MODEL = "model.job_runtime_baseline"
DEFAULT_CEILINGS_DIR = Path("docs/benchmarking/datasets")

# The power benchmark's protocol (docs/benchmarking/power/methodology.md).
POWER_PROTOCOL: dict[str, int] = {
    "n_windows": 89,
    "test_window_hours": 24,
    "training_lookback_days": 60,
}

# What a bundle ran with for a setting added after it was written, so the stale check below
# still sees it. UoPC voted over whole watts until the predictor setting existed (#241).
_BEFORE_SETTING_EXISTED: dict[str, Any] = {"predictor": "vote"}


@dataclass(frozen=True)
class Track:
    """One leaderboard: a prediction target and the benchmark that ranks it."""

    key: str
    title: str
    target: str
    # Runtime has no headroom until its ceilings match its protocol (#238).
    headroom: bool
    note: str = ""


TRACKS: tuple[Track, ...] = (
    Track(
        "runtime",
        "Job runtime",
        "runtime_seconds",
        headroom=False,
        note="MAE only: the runtime ceilings predate the current protocol (#238).",
    ),
    Track("avgpcon_per_node", "Average power per node", "avgpcon_per_node", headroom=True),
    Track(
        "maxpcon_per_node",
        "Peak power per node",
        "maxpcon_per_node",
        headroom=True,
        note="F-DATA and PM100 define peak differently; the average mixes the two.",
    ),
)
TRACK_BY_TARGET = {track.target: track for track in TRACKS}


# --- rosters and floors ---------------------------------------------------------------


def _short(dataset_id: str) -> str:
    return dataset_id.split(".")[-1]


def load_floors(ceilings_dir: Path) -> dict[tuple[str, str], float]:
    """Floor MAE per (target, dataset), from every ceiling file in ``ceilings_dir``.

    Matched on the file's own ``dataset_id`` and ``target_field`` rather than its name, so a
    power file named ``nlr_eagle_power.*`` still matches bundles whose dataset is
    ``nlr_eagle``. A file without ``target_field`` predates #230 and bounds runtime.
    """
    floors: dict[tuple[str, str], float] = {}
    if not ceilings_dir.is_dir():
        return floors
    for path in sorted(ceilings_dir.glob("*.ceiling.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            dataset = _short(str(data.get("dataset_id") or path.name.split(".")[0]))
            target = str(data.get("target_field") or "runtime_seconds")
            floors[(target, dataset)] = float(data["floor"]["mae"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return floors


def _roster(
    track: Track, floors: Mapping[tuple[str, str], float], cards: Sequence[Any]
) -> list[str]:
    """The datasets a track's table has a column for, whether or not anything ran on them."""
    if track.target == "runtime_seconds":
        return sorted(card.dataset for card in cards)
    return sorted(dataset for target, dataset in floors if target == track.target)


# --- which bundles count ------------------------------------------------------------


def _bundled_power_recipes() -> dict[str, dict[str, Any]]:
    """The bundled power benchmark recipes, by recipe id: their split, as shipped today."""
    from hpc_oda_commons.benchmark.recipes import load_recipe

    root = Path(str(ir.files("hpc_oda_commons") / "recipes" / "job-power"))
    recipes: dict[str, dict[str, Any]] = {}
    for path in sorted(root.glob("*_rolling_*.yml")):
        recipe = load_recipe(path)
        recipes[str(recipe["recipe_id"])] = recipe
    return recipes


def _split_values(metrics: Mapping[str, Any]) -> dict[str, Any]:
    """The split a bundle ran, from its summary, falling back to its run config."""
    summary = metrics.get("summary") or {}
    config = metrics.get("run_config") or {}
    keys = ("n_windows", "test_window_hours", "training_lookback_days")
    return {k: summary.get(k, config.get(k)) for k in keys}


def bundle_dataset(entry: Mapping[str, Any], power_recipes: Mapping[str, Mapping[str, Any]]) -> str:
    """The roster dataset a bundle ran on.

    A bundle records its table's folder name (``nlr_eagle_power_embedded``), not the recipe's
    dataset id, so a power bundle takes its dataset from its bundled recipe. Runtime matrix
    tables are named after their dataset card, so the recorded name already matches.
    """
    recipe = power_recipes.get(str(entry.get("recipe_id") or ""))
    if recipe is not None:
        return _short(str(recipe["dataset"]["id"]))
    return _short(str((entry.get("dataset") or {}).get("id") or ""))


def exclusion_reason(
    entry: Mapping[str, Any],
    metrics: Mapping[str, Any],
    *,
    cards_by_dataset: Mapping[str, Any],
    power_recipes: Mapping[str, Mapping[str, Any]],
) -> str | None:
    """Why a bundle is not a cell of its target's benchmark, or None when it is."""
    from hpc_oda_commons.benchmarking.hpc.matrix import (
        SPLIT,
        lookback_arms_for,
        n_windows_for,
    )

    target = entry.get("prediction_target")
    if target not in TRACK_BY_TARGET:
        return f"no leaderboard for target {target!r}"
    dataset = _short(str((entry.get("dataset") or {}).get("id") or ""))
    protocol = (metrics.get("run_config") or {}).get("protocol")
    if protocol:
        return f"protocol {protocol!r} is a study, not the benchmark"
    split = _split_values(metrics)
    if None in split.values():
        return "no rolling split recorded"

    if target == "runtime_seconds":
        card = cards_by_dataset.get(dataset)
        if card is None:
            return f"{dataset!r} is not in the runtime roster (no dataset card)"
        expected = {
            "n_windows": n_windows_for(card),
            "test_window_hours": int(SPLIT["test_window_hours"]),
        }
        for key, value in expected.items():
            if int(split[key]) != int(value):
                return f"{key}={split[key]}, the benchmark runs {value}"
        arms = lookback_arms_for(card)
        if int(split["training_lookback_days"]) not in arms:
            return f"lookback {split['training_lookback_days']} d is not one of {list(arms)}"
        return None

    for key, value in POWER_PROTOCOL.items():
        if int(split[key]) != value:
            return f"{key}={split[key]}, the benchmark runs {value}"
    recipe_id = str(entry.get("recipe_id") or "")
    recipe = power_recipes.get(recipe_id)
    if recipe is None:
        return f"recipe {recipe_id!r} is not a bundled benchmark recipe"
    # A bundle run before its recipe changed is not the benchmark's cell any more.
    config = metrics.get("run_config") or {}
    for key, value in (recipe.get("split") or {}).items():
        ran = config.get(key, _BEFORE_SETTING_EXISTED.get(key))
        if ran is not None and key not in POWER_PROTOCOL and ran != value:
            return f"stale: ran with {key}={ran}, the recipe now says {value}"
    return None


# --- cells ----------------------------------------------------------------------------


def _cell_mae(bundles: Sequence[tuple[dict[str, Any], dict[str, Any]]], burn_in: int) -> float:
    """A cell's MAE: the bundle's own, or the walk-forward policy over lookback arms (#190)."""
    if len(bundles) == 1:
        entry, metrics = bundles[0]
        if entry.get("prediction_target") != "runtime_seconds":
            return float(metrics["mae"])
        # One runtime arm: score it on the same post-burn-in windows a policy would use.
        arm = Arm.from_metrics("only", metrics)
        scored = common_scored_indices([arm])[burn_in:]
        return pooled_metric([arm.windows[i] for i in scored], "mae")
    configs = [metrics.get("run_config") or {} for _entry, metrics in bundles]
    keys = derive_arm_keys(configs)
    arms = [
        Arm.from_metrics(key, metrics) for key, (_e, metrics) in zip(keys, bundles, strict=True)
    ]
    return walk_forward(arms, metric="mae", burn_in=burn_in).score


def build_tables(
    bundles: Sequence[tuple[dict[str, Any], dict[str, Any]]],
    *,
    ceilings_dir: Path = DEFAULT_CEILINGS_DIR,
    cards: Sequence[Any] = (),
    burn_in: int = DEFAULT_BURN_IN,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The per-target tables, and every bundle left out with the reason.

    ``bundles`` pairs each leaderboard entry with its full ``metrics.json`` payload, oldest
    first, so a later bundle of the same configuration replaces an earlier one (#166).
    """
    floors = load_floors(ceilings_dir)
    cards_by_dataset = {card.dataset: card for card in cards}
    power_recipes = _bundled_power_recipes()

    excluded: list[dict[str, Any]] = []
    newest: dict[tuple[str, str, str, str], tuple[dict[str, Any], dict[str, Any]]] = {}
    for entry, metrics in bundles:
        reason = exclusion_reason(
            entry, metrics, cards_by_dataset=cards_by_dataset, power_recipes=power_recipes
        )
        if reason is not None:
            excluded.append({"bundle_dir": entry.get("bundle_dir"), "reason": reason})
            continue
        target = str(entry["prediction_target"])
        dataset = bundle_dataset(entry, power_recipes)
        model = str(entry["model"]["id"])
        arm = json.dumps(metrics.get("run_config") or {}, sort_keys=True, default=str)
        key = (target, dataset, model, arm)
        if key in newest:
            excluded.append(
                {
                    "bundle_dir": newest[key][0].get("bundle_dir"),
                    "reason": f"superseded by {entry.get('bundle_dir')}",
                }
            )
        newest[key] = (entry, metrics)

    grouped: dict[tuple[str, str, str], list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for (target, dataset, model, _arm), pair in newest.items():
        grouped.setdefault((target, dataset, model), []).append(pair)

    tables = []
    for track in TRACKS:
        roster = _roster(track, floors, cards)
        cells: dict[str, dict[str, dict[str, Any]]] = {}
        for (target, dataset, model), pairs in sorted(grouped.items()):
            if target != track.target:
                continue
            try:
                mae = _cell_mae(pairs, burn_in)
            except (ArmSelectionError, KeyError, TypeError, ValueError) as exc:
                for entry, _metrics in pairs:
                    excluded.append({"bundle_dir": entry.get("bundle_dir"), "reason": str(exc)})
                continue
            cells.setdefault(model, {})[dataset] = {
                "mae": mae,
                "bundles": [entry.get("bundle_dir") for entry, _m in pairs],
            }
        tables.append(_table(track, roster, cells, floors))
    return tables, excluded


def _table(
    track: Track,
    roster: list[str],
    cells: dict[str, dict[str, dict[str, Any]]],
    floors: Mapping[tuple[str, str], float],
) -> dict[str, Any]:
    datasets = sorted(set(roster) | {d for row in cells.values() for d in row})
    baselines = {d: cell["mae"] for d, cell in cells.get(BASELINE_MODEL, {}).items()}
    for row in cells.values():
        for dataset, cell in row.items():
            floor = floors.get((track.target, dataset))
            base = baselines.get(dataset)
            usable = track.headroom and floor is not None and base is not None and base > floor
            cell["headroom"] = (base - cell["mae"]) / (base - floor) if usable else None

    rows = []
    for model, row in cells.items():
        values = [row[d]["headroom"] for d in roster if d in row]
        complete = (
            track.headroom and bool(roster) and all(d in row for d in roster) and None not in values
        )
        rows.append(
            {
                "model": model,
                "average": sum(values) / len(values) if complete else None,
                "datasets_run": sum(1 for d in roster if d in row),
                "cells": row,
            }
        )
    # Ranked rows first, best average first; then incomplete rows, by model.
    rows.sort(key=lambda r: (r["average"] is None, -(r["average"] or 0.0), r["model"]))
    return {
        "key": track.key,
        "title": track.title,
        "target": track.target,
        "headroom": track.headroom,
        "note": track.note,
        "datasets": datasets,
        "roster": roster,
        "rows": rows,
    }
