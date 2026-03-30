"""
Validate recipes and MDL constraints (pre-commit/CI).
"""

from __future__ import annotations

from pathlib import Path

from hpc_oda_commons.benchmark.recipes import load_recipe


def _iter_recipe_paths() -> list[Path]:
    roots = [Path("src/hpc_oda_commons/recipes"), Path("tests") / "fixtures" / "recipes"]
    paths: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.yml")) + sorted(root.rglob("*.yaml")):
            if "recipes/common/envs" in path.as_posix():
                continue
            if "recipes/common/metrics_mdl_examples" in path.as_posix():
                continue
            paths.append(path)
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
