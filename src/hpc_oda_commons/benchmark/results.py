"""
Result bundle schema helpers and readers/writers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hpc_oda_commons.benchmark.arm_selection import (
    DEFAULT_BURN_IN,
    DEFAULT_METRIC,
    Arm,
    ArmSelectionError,
    derive_arm_keys,
    walk_forward,
)
from hpc_oda_commons.benchmark.leaderboard_display import infer_prediction_target
from hpc_oda_commons.kernel.artifacts.result_bundle import (
    read_result_bundle,
    validate_result_bundle,
)
from hpc_oda_commons.kernel.paths import ensure_dir

LEADERBOARD_FORMAT_VERSION = "oda.leaderboard.v0.1.0"


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _collect_bundle_dirs(runs_dir: Path) -> list[Path]:
    if not runs_dir.exists():
        return []
    return [p.parent for p in runs_dir.rglob("result.json")]


def build_leaderboard_entry(bundle_dir: Path) -> dict[str, Any]:
    validate_result_bundle(bundle_dir)
    result, metrics, _prov = read_result_bundle(bundle_dir, validate=True)
    prediction_target = infer_prediction_target(metrics)

    entry = {
        "bundle_dir": str(bundle_dir),
        "created_at": result.get("created_at"),
        "recipe_id": result.get("recipe_id"),
        "problem_domain": result.get("problem_domain", []),
        "metrics": result.get("metrics", metrics),
        "prediction_target": prediction_target,
        "model": result.get("model", {}),
        "dataset": result.get("dataset", {}),
        "integrity": result.get("integrity"),
        "timing": result.get("timing"),
    }
    return entry


def _cell_key(entry: dict[str, Any]) -> tuple[Any, ...]:
    """What identifies a benchmark cell: one (dataset, model) pair.

    Falls back to the recipe id, then to the bundle path -- a bundle we cannot identify is
    left alone rather than merged with something it may not be.
    """
    dataset = (entry.get("dataset") or {}).get("id")
    model = (entry.get("model") or {}).get("id")
    # The recipe id is part of the identity, not a fallback. Since #170 the benchmark runs
    # each model at several training lookbacks, and those are different cells -- keying on
    # (dataset, model) alone would silently keep one arm of three and discard the rest.
    if dataset and model:
        return ("cell", dataset, model, entry.get("recipe_id"))
    if entry.get("recipe_id"):
        return ("recipe", entry["recipe_id"])
    return ("bundle", entry.get("bundle_dir"))


def build_leaderboard(runs_dir: Path) -> dict[str, Any]:
    """One entry per benchmark cell -- the newest bundle wins.

    Bundles are written to ``runs/<dataset>/<model>/benchmark-<timestamp>/``, so a cell that
    runs twice leaves two of them. Re-running a cell is the normal repair path, and emitting
    one entry per *bundle* silently double-weights it: a per-model mean or a
    best-model-per-dataset ranking counts the superseded run -- from code that has since been
    fixed -- equally with the run that replaced it (#166).

    ``overwrite: true`` in a recipe is easy to misread as preventing this. It governs the
    timestamped directory, not the previous result.
    """
    entries: list[dict[str, Any]] = []
    for bundle_dir in _collect_bundle_dirs(runs_dir):
        try:
            entries.append(build_leaderboard_entry(bundle_dir))
        except Exception:
            # Skip invalid bundles to keep report generation robust in v0.1
            continue

    entries.sort(key=lambda e: e.get("created_at") or "")
    newest: dict[tuple[Any, ...], dict[str, Any]] = {}
    superseded: list[dict[str, Any]] = []
    for entry in entries:  # ascending created_at, so a later bundle replaces an earlier one
        key = _cell_key(entry)
        if key in newest:
            superseded.append(newest[key])
        newest[key] = entry

    kept = sorted(newest.values(), key=lambda e: e.get("created_at") or "")
    return {
        "schema_version": LEADERBOARD_FORMAT_VERSION,
        "generated_at": _now_utc_iso(),
        "runs_dir": str(runs_dir),
        "entries": kept,
        # Named, not silently dropped: the same rule as anywhere else the tooling narrows
        # coverage. A reader can see which runs were superseded and by what.
        "superseded": [
            {
                "bundle_dir": e.get("bundle_dir"),
                "created_at": e.get("created_at"),
                "recipe_id": e.get("recipe_id"),
            }
            for e in superseded
        ],
    }


def write_leaderboard(leaderboard: dict[str, Any], out_dir: Path) -> Path:
    ensure_dir(out_dir)
    out_path = out_dir / "leaderboard.json"
    out_path.write_text(json.dumps(leaderboard, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_path


ARM_RANKING_FORMAT_VERSION = "oda.arm_ranking.v0.1.0"


def _arm_sort_key(arm_key: str) -> tuple:
    """Order arms by their values, numerically where the values are numbers."""
    parts = []
    for field in arm_key.split("+"):
        _name, _, value = field.partition("=")
        try:
            parts.append((0, float(value), ""))
        except ValueError:
            parts.append((1, 0.0, value))
    return tuple(parts)


def _legacy_arm_config(metrics: dict[str, Any]) -> dict[str, Any] | None:
    """Stand in for ``run_config`` on bundles written before it existed (#197).

    Those bundles record three split fields in their summary and nothing else, so the training
    lookback is the only axis they can express. Falling back to it keeps every result measured
    so far rankable instead of stranding it behind a format change.
    """
    summary = metrics.get("summary") or {}
    lookback = summary.get("training_lookback_days")
    if lookback is None:
        return None
    return {"training_lookback_days": int(lookback)}


def build_arm_ranking(
    runs_dir: Path,
    *,
    metric: str = DEFAULT_METRIC,
    burn_in: int = DEFAULT_BURN_IN,
) -> dict[str, Any]:
    """Rank each ``(dataset, model)`` cell by walk-forward choice among its arms.

    Supersedes on the **recorded configuration**, not on the recipe id. ``build_leaderboard``
    keys a cell as ``(dataset, model, recipe_id)``, which is correct there but too coarse
    here: two arms differing by a knob the recipe id does not spell out would collapse into
    one cell and the older would be discarded as superseded. #187 had to put the lookback
    into the recipe id by hand for exactly this reason; keying on the configuration means the
    next axis does not need the same remembering (#197). A genuine re-run -- same
    configuration, later timestamp -- still replaces its predecessor (#166).

    Cells that cannot be ranked are reported, not dropped: one arm is not a choice, and arms
    that disagree about the split are a staging error worth seeing rather than a row that
    quietly goes missing (#190).
    """
    entries: list[dict[str, Any]] = []
    for bundle_dir in _collect_bundle_dirs(runs_dir):
        try:
            entry = build_leaderboard_entry(bundle_dir)
            _result, metrics, _prov = read_result_bundle(bundle_dir, validate=False)
        except Exception:
            continue
        config = metrics.get("run_config") or _legacy_arm_config(metrics)
        if config is None:
            continue
        entry["_config"] = config
        entry["_metrics"] = metrics
        entries.append(entry)

    entries.sort(key=lambda e: e.get("created_at") or "")
    newest: dict[tuple[Any, ...], dict[str, Any]] = {}
    for entry in entries:  # ascending created_at, so a later bundle replaces an earlier one
        dataset = (entry.get("dataset") or {}).get("id")
        model = (entry.get("model") or {}).get("id")
        if not dataset or not model:
            continue
        newest[(dataset, model, json.dumps(entry["_config"], sort_keys=True))] = entry

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for (dataset, model, _cfg), entry in newest.items():
        grouped.setdefault((dataset, model), []).append(entry)

    cells: list[dict[str, Any]] = []
    unranked: list[dict[str, Any]] = []
    for (dataset, model), cell_entries in sorted(grouped.items()):
        loaded = [(e["_config"], e["_metrics"]) for e in cell_entries]
        if len(loaded) < 2:
            unranked.append(
                {
                    "dataset": dataset,
                    "model": model,
                    "reason": f"only {len(loaded)} arm(s) present; selection needs at least two",
                }
            )
            continue
        try:
            keys = derive_arm_keys([config for config, _metrics in loaded])
        except ArmSelectionError as exc:
            unranked.append({"dataset": dataset, "model": model, "reason": str(exc)})
            continue
        # Sorted so the walk-forward tie-break is deterministic and independent of the order
        # bundles happened to be read in. Numeric-suffixed keys sort by value, so the shortest
        # lookback still wins a tie -- the cheapest arm and the least dependent on history.
        arms = [
            Arm.from_metrics(key, metrics)
            for key, (_config, metrics) in sorted(
                zip(keys, loaded, strict=True), key=lambda pair: _arm_sort_key(pair[0])
            )
        ]
        try:
            result = walk_forward(arms, metric=metric, burn_in=burn_in)
        except ArmSelectionError as exc:
            unranked.append({"dataset": dataset, "model": model, "reason": str(exc)})
            continue
        cells.append({"dataset": dataset, "model": model, **result.to_dict()})

    return {
        "schema_version": ARM_RANKING_FORMAT_VERSION,
        "generated_at": _now_utc_iso(),
        "runs_dir": str(runs_dir),
        "metric": metric,
        "burn_in": burn_in,
        "cells": cells,
        "unranked": unranked,
    }


def write_arm_ranking(ranking: dict[str, Any], out_dir: Path) -> Path:
    ensure_dir(out_dir)
    out_path = out_dir / "arm-ranking.json"
    out_path.write_text(json.dumps(ranking, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_path
