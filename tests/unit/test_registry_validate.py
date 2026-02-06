from __future__ import annotations

from hpc_oda_commons.registry.snapshot import snapshot_resource_path
from hpc_oda_commons.registry.validate import validate_registry_snapshot


def test_registry_snapshot_validates() -> None:
    path = snapshot_resource_path()
    validate_registry_snapshot(path)
