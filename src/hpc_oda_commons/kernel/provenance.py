from __future__ import annotations

import os
import subprocess
from importlib import metadata
from pathlib import Path

from hpc_oda_commons.kernel.hashing import HashedInput, hash_input


def python_version() -> str:
    vi = os.sys.version_info
    return f"{vi.major}.{vi.minor}.{vi.micro}"


def package_version(dist_name: str = "hpc-oda-commons") -> str:
    try:
        return metadata.version(dist_name)
    except metadata.PackageNotFoundError:
        return "0.0.0"


def git_commit_if_available(project_root: Path | None = None) -> str | None:
    """
    Best-effort git commit capture; returns None if not a git checkout or git missing.
    """
    cwd = str(project_root) if project_root else None
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if proc.returncode != 0:
            return None
        sha = proc.stdout.strip()
        return sha if sha else None
    except Exception:
        return None


def pip_freeze_minimal() -> list[str]:
    """
    Best-effort package snapshot. Keep optional because it can be slow.
    """
    try:
        proc = subprocess.run(
            [os.sys.executable, "-m", "pip", "freeze"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode != 0:
            return []
        lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
        return sorted(lines)
    except Exception:
        return []


def build_provenance(
    *,
    input_schema: str,
    result_schema: str,
    inputs: list[Path],
    project_root: Path | None = None,
    capture_packages: bool = False,
    source_hash: str | None = None,
) -> dict:
    hashed_inputs: list[HashedInput] = [hash_input(p, content=True) for p in inputs]
    env_pkgs: list[str] = pip_freeze_minimal() if capture_packages else []

    return {
        "schema_versions": {"input": input_schema, "result": result_schema},
        "environment": {"python": python_version(), "packages": env_pkgs},
        "code": {
            "package_version": package_version(),
            "git_commit": git_commit_if_available(project_root),
            "source_hash": source_hash,
        },
        "inputs": [
            {
                "path": hi.path,
                "sha256": hi.sha256,
                "size_bytes": hi.size_bytes,
                "mtime_epoch": hi.mtime_epoch,
            }
            for hi in hashed_inputs
        ],
    }
