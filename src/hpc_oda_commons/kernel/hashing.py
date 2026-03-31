from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HashedInput:
    path: str
    sha256: str | None
    size_bytes: int | None
    mtime_epoch: float | None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_package_source(
    package_dir: Path,
    *,
    exclude_relative: set[str] | None = None,
) -> str:
    """Hash all .py files in a package directory for integrity verification.

    Returns a deterministic SHA-256 hex digest. Files are sorted by relative path
    so the hash is stable across platforms.
    """
    excl = exclude_relative or set()
    py_files = sorted(package_dir.rglob("*.py"))
    h = hashlib.sha256()
    for py_file in py_files:
        rel = str(py_file.relative_to(package_dir))
        if rel in excl:
            continue
        file_hash = sha256_file(py_file)
        h.update(f"{rel}\0{file_hash}\n".encode())
    return h.hexdigest()


def resolve_package_dir() -> Path | None:
    """Resolve the installed hpc_oda_commons package directory."""
    try:
        from importlib.resources import files

        pkg = files("hpc_oda_commons")
        pkg_path = Path(str(pkg))
        if pkg_path.is_dir():
            return pkg_path
    except Exception:
        pass
    return None


def hash_input(path: Path, *, content: bool = True) -> HashedInput:
    """
    Hash an input path.
    - If the file exists and content=True, compute sha256 of file bytes.
    - Always record path string; attempt to record size + mtime when available.
    """
    sha = None
    size = None
    mtime = None

    try:
        st = path.stat()
        size = int(st.st_size)
        mtime = float(st.st_mtime)
        if content and path.is_file():
            sha = sha256_file(path)
    except FileNotFoundError:
        pass

    return HashedInput(
        path=str(path),
        sha256=sha,
        size_bytes=size,
        mtime_epoch=mtime,
    )
