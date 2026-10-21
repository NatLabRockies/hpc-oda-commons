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

A cell shows headroom only when its floor, its baseline and the cell itself cover the same
jobs, checked as equal scored-row counts (#238). A ceiling computed on other windows -- such
as a runtime ceiling from before the walk-forward burn-in -- leaves that cell at MAE alone
rather than dividing numbers measured on different rows.
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
    _window_rows,
    common_scored_indices,
    derive_arm_keys,
    legacy_arm_config,
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

# The runtime benchmark's protocol: the fleet that has been run (plan 20260826-231908, 20
# datasets x 7 models x these lookbacks), testing 30 days in 6 h windows. The cards ask for
# 90 days (#191), but no fleet has run that yet, so the leaderboard counts what exists and
# moves to the cards' windows when #191's fleet does.
RUNTIME_PROTOCOL: dict[str, int] = {"n_windows": 120, "test_window_hours": 6}
RUNTIME_LOOKBACKS: tuple[int, ...] = (10, 30, 120)

# What a bundle ran with for a setting added after it was written, so the stale check below
# still sees it. UoPC voted over whole watts until the predictor setting existed (#241).
_BEFORE_SETTING_EXISTED: dict[str, Any] = {"predictor": "vote"}


@dataclass(frozen=True)
class Track:
    """One leaderboard: a prediction target and the benchmark that ranks it."""

    key: str
    title: str
    target: str
    headroom: bool
    note: str = ""


TRACKS: tuple[Track, ...] = (
    Track(
        "runtime",
        "Job runtime",
        "runtime_seconds",
        headroom=True,
        # Measured on the fleet of 2026-08-26 (#238); revisit when #191's fleet replaces it.
        note="30-day test, 10/30/120-day lookbacks. On alcf_djc_polaris the baseline's "
        "walk-forward pick scores 14% worse than its best single lookback, so headroom "
        "there reads high.",
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


@dataclass(frozen=True)
class Floor:
    """A dataset's floor MAE, and how many jobs it was measured on."""

    mae: float
    scored_rows: int


def load_floors(ceilings_dir: Path) -> dict[tuple[str, str], Floor]:
    """The floor per (target, dataset), from every ceiling file in ``ceilings_dir``.

    Matched on the file's own ``dataset_id`` and ``target_field`` rather than its name, so a
    power file named ``nlr_eagle_power.*`` still matches bundles whose dataset is
    ``nlr_eagle``. A file without ``target_field`` predates #230 and bounds runtime.
    """
    floors: dict[tuple[str, str], Floor] = {}
    if not ceilings_dir.is_dir():
        return floors
    for path in sorted(ceilings_dir.glob("*.ceiling.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            dataset = _short(str(data.get("dataset_id") or path.name.split(".")[0]))
            target = str(data.get("target_field") or "runtime_seconds")
            floors[(target, dataset)] = Floor(float(data["floor"]["mae"]), int(data["scored_rows"]))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return floors


def _roster(
    track: Track, floors: Mapping[tuple[str, str], Floor], cards: Sequence[Any]
) -> list[str]:
    """The datasets a track's table has a column for, whether or not anything ran on them.

    For runtime, every card the planner would run: a dataset too large for one node (today
    ``ccin2p3_2024``) keeps its card but is never planned, so it would leave every model's
    average incomplete.
    """
    if track.target == "runtime_seconds":
        from hpc_oda_commons.benchmarking.hpc.matrix import fits_a_node

        return sorted(card.dataset for card in cards if fits_a_node(card.effective_rows))
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
        for key, value in RUNTIME_PROTOCOL.items():
            if int(split[key]) != value:
                return f"{key}={split[key]}, the benchmark runs {value}"
        if int(split["training_lookback_days"]) not in RUNTIME_LOOKBACKS:
            return (
                f"lookback {split['training_lookback_days']} d is not one of "
                f"{list(RUNTIME_LOOKBACKS)}"
            )
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


def _arm_config(metrics: Mapping[str, Any]) -> dict[str, Any]:
    """What a bundle ran with: its ``run_config``, or for bundles from before #197 (the
    runtime fleet among them) the lookback its summary records."""
    return dict(metrics.get("run_config") or legacy_arm_config(metrics) or {})


def _cell_score(
    bundles: Sequence[tuple[dict[str, Any], dict[str, Any]]], burn_in: int
) -> tuple[float, int | None]:
    """A cell's MAE and the jobs it covers: the bundle's own, or the walk-forward policy over
    lookback arms (#190). The job count is None when a bundle does not record it."""
    if len(bundles) == 1:
        entry, metrics = bundles[0]
        if entry.get("prediction_target") != "runtime_seconds":
            rows = (metrics.get("summary") or {}).get("rows_scored")
            return float(metrics["mae"]), None if rows is None else int(rows)
        # One runtime arm: score it on the same post-burn-in windows a policy would use.
        arm = Arm.from_metrics("only", metrics)
        windows = [arm.windows[i] for i in common_scored_indices([arm])[burn_in:]]
        return pooled_metric(windows, "mae"), int(sum(_window_rows(w) for w in windows))
    configs = [_arm_config(metrics) for _entry, metrics in bundles]
    keys = derive_arm_keys(configs)
    arms = [
        Arm.from_metrics(key, metrics) for key, (_e, metrics) in zip(keys, bundles, strict=True)
    ]
    result = walk_forward(arms, metric="mae", burn_in=burn_in)
    return result.score, result.scored_rows


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
        arm = json.dumps(_arm_config(metrics), sort_keys=True, default=str)
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
                mae, rows = _cell_score(pairs, burn_in)
            except (ArmSelectionError, KeyError, TypeError, ValueError) as exc:
                for entry, _metrics in pairs:
                    excluded.append({"bundle_dir": entry.get("bundle_dir"), "reason": str(exc)})
                continue
            cells.setdefault(model, {})[dataset] = {
                "mae": mae,
                "scored_rows": rows,
                "bundles": [entry.get("bundle_dir") for entry, _m in pairs],
            }
        tables.append(_table(track, roster, cells, floors))
    return tables, excluded


_ROWS_DIFFER = "covers other jobs"


def _headroom_blocker(
    cell: Mapping[str, Any], floor: Floor | None, base: Mapping[str, Any] | None
) -> str | None:
    """Why a cell gets no headroom, or None when floor, baseline and cell are comparable.

    All three must cover the same jobs. A floor from other windows bounds other rows, and
    dividing by it would give a percentage of nothing in particular (#238).
    """
    if floor is None:
        return "no ceiling for this dataset"
    if base is None:
        return "no baseline cell"
    rows = cell.get("scored_rows")
    if rows is None or base.get("scored_rows") is None:
        return "a bundle does not record the jobs it scored"
    if not rows == base["scored_rows"] == floor.scored_rows:
        return (
            f"{_ROWS_DIFFER}: the ceiling {floor.scored_rows:,}, the baseline "
            f"{base['scored_rows']:,} and this cell {rows:,}"
        )
    if base["mae"] <= floor.mae:
        return "the baseline is already at the floor"
    return None


def _table(
    track: Track,
    roster: list[str],
    cells: dict[str, dict[str, dict[str, Any]]],
    floors: Mapping[tuple[str, str], Floor],
) -> dict[str, Any]:
    datasets = sorted(set(roster) | {d for row in cells.values() for d in row})
    baselines = cells.get(BASELINE_MODEL, {})
    mismatched = False
    for row in cells.values():
        for dataset, cell in row.items():
            floor = floors.get((track.target, dataset))
            base = baselines.get(dataset)
            reason = _headroom_blocker(cell, floor, base) if track.headroom else "no headroom"
            if reason is None:
                cell["headroom"] = (base["mae"] - cell["mae"]) / (base["mae"] - floor.mae)
            else:
                cell["headroom"] = None
                cell["headroom_missing"] = reason
                mismatched = mismatched or reason.startswith(_ROWS_DIFFER)

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
        "note": " ".join(
            n
            for n in (
                track.note,
                "Cells in MAE alone: their dataset's ceiling covers other jobs (#238)."
                if mismatched
                else "",
            )
            if n
        ),
        "datasets": datasets,
        "roster": roster,
        "rows": rows,
    }
