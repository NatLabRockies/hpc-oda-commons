"""
Schema sanity checks: load all packaged schema JSON files.
"""

from __future__ import annotations

from pathlib import Path


def _iter_schema_paths() -> list[Path]:
    root = Path("src/hpc_oda_commons/schemas")
    if not root.exists():
        return []
    return sorted(root.rglob("*.json"))


def main() -> int:
    import json

    paths = _iter_schema_paths()
    if not paths:
        print("No schemas found.")
        return 0

    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise SystemExit(f"Schema is not a JSON object: {path}")
        if "$id" not in payload:
            raise SystemExit(f"Schema missing $id: {path}")

    print(f"Validated {len(paths)} schema file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
