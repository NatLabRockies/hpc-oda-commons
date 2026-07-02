"""
Validate registry JSON against registry schema.
"""

from __future__ import annotations

from pathlib import Path

from hpc_oda_commons.kernel.validate import validate_json

REGISTRY_SCHEMA_ID = "oda.registry.v0.2.0"


def validate_registry_snapshot(path: Path) -> dict:
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Registry snapshot must be a JSON object.")
    validate_json(payload, REGISTRY_SCHEMA_ID, path=path)
    return payload
