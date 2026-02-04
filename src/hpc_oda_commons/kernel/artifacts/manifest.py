from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hpc_oda_commons.kernel.paths import ensure_parent_dir
from hpc_oda_commons.kernel.validate import validate_json, validate_json_file


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_manifest(
    *,
    input_schema_version: str,
    adapter: dict[str, str] | None,
    inputs: list[dict[str, Any]],
    artifact: dict[str, Any],
    provenance: dict[str, Any],
    transformations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "oda.manifest.v0.1.0",
        "created_at": _now_utc_iso(),
        "input_schema_version": input_schema_version,
        "adapter": adapter or {},
        "inputs": inputs,
        "artifact": artifact,
        "transformations": transformations or [],
        "provenance": provenance,
    }


def write_manifest(path: Path, manifest: dict[str, Any], *, validate: bool = True) -> None:
    if validate:
        validate_json(manifest, "oda.manifest.v0.1.0", path=path)
    ensure_parent_dir(path)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_manifest(path: Path, *, validate: bool = True) -> dict[str, Any]:
    obj = (
        validate_json_file(path, "oda.manifest.v0.1.0")
        if validate
        else json.loads(path.read_text(encoding="utf-8"))
    )
    return obj


def validate_manifest(path: Path) -> dict[str, Any]:
    return validate_json_file(path, "oda.manifest.v0.1.0")
