"""
Sync canonical repo recipes into packaged recipe assets.

Canonical source of truth: recipes/
Packaged destination: src/hpc_oda_commons/recipes/
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

RECIPE_SUFFIXES = {".yml", ".yaml", ".toml"}


@dataclass(frozen=True)
class RecipeDiff:
    missing_in_packaged: tuple[Path, ...]
    extra_in_packaged: tuple[Path, ...]
    different_content: tuple[Path, ...]

    def is_clean(self) -> bool:
        return (
            not self.missing_in_packaged
            and not self.extra_in_packaged
            and not self.different_content
        )


def _recipe_files(root: Path) -> dict[Path, Path]:
    files: dict[Path, Path] = {}
    if not root.exists():
        return files
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in RECIPE_SUFFIXES:
            continue
        rel = path.relative_to(root)
        files[rel] = path
    return files


def diff_recipes(canonical_root: Path, packaged_root: Path) -> RecipeDiff:
    canonical = _recipe_files(canonical_root)
    packaged = _recipe_files(packaged_root)

    canonical_keys = set(canonical.keys())
    packaged_keys = set(packaged.keys())

    missing = tuple(sorted(canonical_keys - packaged_keys))
    extra = tuple(sorted(packaged_keys - canonical_keys))

    common = canonical_keys & packaged_keys
    different = tuple(
        sorted(rel for rel in common if canonical[rel].read_bytes() != packaged[rel].read_bytes())
    )

    return RecipeDiff(
        missing_in_packaged=missing,
        extra_in_packaged=extra,
        different_content=different,
    )


def _prune_empty_dirs(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def sync_recipes(canonical_root: Path, packaged_root: Path) -> RecipeDiff:
    canonical = _recipe_files(canonical_root)
    packaged = _recipe_files(packaged_root)

    packaged_root.mkdir(parents=True, exist_ok=True)

    for rel, src in canonical.items():
        dest = packaged_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        payload = src.read_bytes()
        if not dest.exists() or dest.read_bytes() != payload:
            dest.write_bytes(payload)

    for rel in sorted(set(packaged.keys()) - set(canonical.keys())):
        (packaged_root / rel).unlink()

    _prune_empty_dirs(packaged_root)
    return diff_recipes(canonical_root, packaged_root)


def _print_diff(diff: RecipeDiff) -> None:
    if diff.missing_in_packaged:
        print("Missing packaged recipe files:")
        for rel in diff.missing_in_packaged:
            print(f"  - {rel.as_posix()}")
    if diff.extra_in_packaged:
        print("Extra packaged recipe files:")
        for rel in diff.extra_in_packaged:
            print(f"  - {rel.as_posix()}")
    if diff.different_content:
        print("Packaged recipe files with content drift:")
        for rel in diff.different_content:
            print(f"  - {rel.as_posix()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check for drift only (non-zero exit if packaged recipes differ).",
    )
    parser.add_argument(
        "--canonical-root",
        default="recipes",
        help="Path to canonical recipe root (default: recipes).",
    )
    parser.add_argument(
        "--packaged-root",
        default="src/hpc_oda_commons/recipes",
        help="Path to packaged recipe root (default: src/hpc_oda_commons/recipes).",
    )
    args = parser.parse_args()

    canonical_root = Path(args.canonical_root)
    packaged_root = Path(args.packaged_root)

    if args.check:
        diff = diff_recipes(canonical_root, packaged_root)
        if diff.is_clean():
            print("Packaged recipes are in sync.")
            return 0
        _print_diff(diff)
        return 1

    diff = sync_recipes(canonical_root, packaged_root)
    if diff.is_clean():
        print(f"Synced packaged recipes from {canonical_root} to {packaged_root}.")
        return 0

    _print_diff(diff)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
