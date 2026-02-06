"""
Validate recipes and MDL constraints (pre-commit/CI).
"""

from __future__ import annotations

from pathlib import Path

from hpc_oda_commons.benchmark.recipes import load_recipe


def _iter_recipe_paths() -> list[Path]:
    roots = [Path("recipes"), Path("tests") / "fixtures" / "recipes"]
    paths: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        paths.extend(sorted(root.rglob("*.yml")))
        paths.extend(sorted(root.rglob("*.yaml")))
    return paths


def main() -> int:
    paths = _iter_recipe_paths()
    if not paths:
        print("No recipes found.")
        return 0
    for path in paths:
        load_recipe(path, validate=True)
    print(f"Validated {len(paths)} recipe(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
