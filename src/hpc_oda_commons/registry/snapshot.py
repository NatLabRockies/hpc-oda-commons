"""
Load the registry: built from the package's own files, or read from a snapshot file.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

from hpc_oda_commons.kernel.validate import validate_json
from hpc_oda_commons.registry.index import RegistryIndex
from hpc_oda_commons.registry.models import RegistrySnapshot

REGISTRY_SCHEMA_ID = "oda.registry.v0.2.0"


def load_registry_snapshot(path: Path | None = None) -> RegistrySnapshot:
    """The registry: built from the package's files (#249), or a snapshot JSON at ``path``."""
    if path is None:
        return _built_snapshot()
    path = Path(path)
    payload = _load_json(path)
    validate_json(payload, REGISTRY_SCHEMA_ID, path=path)
    return RegistrySnapshot.from_dict(payload)


@functools.cache
def _built_snapshot() -> RegistrySnapshot:
    from hpc_oda_commons.registry.build import build_registry_payload

    payload = build_registry_payload()
    validate_json(payload, REGISTRY_SCHEMA_ID)
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
