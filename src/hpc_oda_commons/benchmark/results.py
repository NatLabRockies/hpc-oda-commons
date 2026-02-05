"""
Result bundle schema helpers and readers/writers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hpc_oda_commons.kernel.artifacts.result_bundle import read_result_bundle, validate_result_bundle
from hpc_oda_commons.kernel.paths import ensure_dir

LEADERBOARD_SCHEMA_VERSION = "oda.leaderboard.v0.1.0"


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _collect_bundle_dirs(runs_dir: Path) -> list[Path]:
    if not runs_dir.exists():
        return []
    return [p.parent for p in runs_dir.rglob("result.json")]


def build_leaderboard_entry(bundle_dir: Path) -> dict[str, Any]:
    validate_result_bundle(bundle_dir)
    result, metrics, _prov = read_result_bundle(bundle_dir, validate=True)

    entry = {
        "bundle_dir": str(bundle_dir),
        "created_at": result.get("created_at"),
        "recipe_id": result.get("recipe_id"),
        "problem_domain": result.get("problem_domain", []),
        "metrics": result.get("metrics", metrics),
        "model": result.get("model", {}),
        "dataset": result.get("dataset", {}),
    }
    return entry


def build_leaderboard(runs_dir: Path) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for bundle_dir in _collect_bundle_dirs(runs_dir):
        try:
            entries.append(build_leaderboard_entry(bundle_dir))
        except Exception:
            # Skip invalid bundles to keep report generation robust in v0.1
            continue

    entries.sort(key=lambda e: e.get("created_at") or "")
    return {
        "schema_version": LEADERBOARD_SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "runs_dir": str(runs_dir),
        "entries": entries,
    }


def write_leaderboard(leaderboard: dict[str, Any], out_dir: Path) -> Path:
    ensure_dir(out_dir)
    out_path = out_dir / "leaderboard.json"
    out_path.write_text(json.dumps(leaderboard, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_path
