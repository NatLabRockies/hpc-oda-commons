"""
Load bundled registry snapshot + optional update mechanism.
"""

from __future__ import annotations

import importlib.resources as ir
from pathlib import Path
from typing import Any

from hpc_oda_commons.kernel.validate import validate_json
from hpc_oda_commons.registry.index import RegistryIndex
from hpc_oda_commons.registry.models import RegistrySnapshot

REGISTRY_SCHEMA_ID = "oda.registry.v0.2.0"


class RegistrySnapshotNotFound(FileNotFoundError):
    def __init__(self, resolved_path: str) -> None:
        super().__init__(f"Registry snapshot not found at {resolved_path}")
        self.resolved_path = resolved_path


def snapshot_resource_path() -> Path:
    base = ir.files("hpc_oda_commons")
    candidate = base / "registry" / "snapshot.json"
    if not candidate.is_file():
        raise RegistrySnapshotNotFound(str(candidate))
    return Path(str(candidate))


def load_registry_snapshot(path: Path | None = None) -> RegistrySnapshot:
    path = Path(path) if path else snapshot_resource_path()
    payload = _load_json(path)
    validate_json(payload, REGISTRY_SCHEMA_ID, path=path)
    return RegistrySnapshot.from_dict(payload)


def load_registry_index(path: Path | None = None) -> RegistryIndex:
    snapshot = load_registry_snapshot(path)
    return RegistryIndex.from_entries(snapshot.entries)


def _load_json(path: Path) -> dict[str, Any]:
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Registry snapshot must be a JSON object: {path}")
    return payload
