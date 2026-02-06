"""
Sync and validate the registry snapshot into the packaged location.
"""

from __future__ import annotations

from pathlib import Path

from hpc_oda_commons.registry.validate import validate_registry_snapshot


def main() -> int:
    src = Path("registry/snapshot.json")
    if not src.exists():
        raise SystemExit(f"Missing registry snapshot: {src}")

    validate_registry_snapshot(src)

    dest = Path("src/hpc_oda_commons/registry/snapshot.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"Validated and synced registry snapshot to {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
