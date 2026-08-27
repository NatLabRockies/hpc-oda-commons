"""
Result bundle schema helpers and readers/writers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
    if dataset and model:
        return ("cell", dataset, model)
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
