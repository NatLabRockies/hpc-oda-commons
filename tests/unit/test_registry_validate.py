from __future__ import annotations

import json
from pathlib import Path

from hpc_oda_commons.registry.build import build_registry_payload
from hpc_oda_commons.registry.validate import validate_registry_snapshot


def test_the_built_registry_validates_as_a_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(build_registry_payload()), encoding="utf-8")
    validate_registry_snapshot(path)
