"""Code integrity: source hashing and validation against known-good commits."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hpc_oda_commons.kernel.hashing import hash_package_source, resolve_package_dir
from hpc_oda_commons.kernel.provenance import git_commit_if_available


def _known_hashes_path() -> Path:
    """Path to the known_hashes.json file shipped with the package."""
    return Path(__file__).resolve().parent.parent / "integrity" / "known_hashes.json"


def _load_known_hashes() -> dict[str, str]:
    path = _known_hashes_path()
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("hashes", {})


def compute_source_hash() -> str | None:
    """Compute SHA-256 of all .py files in the hpc_oda_commons package."""
    pkg_dir = resolve_package_dir()
    if pkg_dir is None:
        return None
    return hash_package_source(pkg_dir)


def check_integrity(*, project_root: Path | None = None) -> dict[str, Any]:
    """Compute source hash and check against known validated hashes.

    Returns a dict with:
        code_hash: str | None — SHA-256 of current source
        validated: bool — True if code_hash matches a known-good commit
        git_commit: str | None — current git commit
    """
    code_hash = compute_source_hash()
    git_commit = git_commit_if_available(project_root)
    known = _load_known_hashes()

    validated = False
    if code_hash is not None and git_commit is not None:
        validated = known.get(git_commit) == code_hash

    return {
        "code_hash": code_hash,
        "validated": validated,
        "git_commit": git_commit,
    }


def record_hash(*, project_root: Path | None = None) -> dict[str, str | None]:
    """Compute current source hash and record it in known_hashes.json.

    Returns the recorded (git_commit, source_hash) pair.
    """
    code_hash = compute_source_hash()
    git_commit = git_commit_if_available(project_root)

    if code_hash is None or git_commit is None:
        return {"git_commit": git_commit, "source_hash": code_hash}

    path = _known_hashes_path()
    data: dict[str, Any] = {"hashes": {}}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))

    data.setdefault("hashes", {})[git_commit] = code_hash
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {"git_commit": git_commit, "source_hash": code_hash}
