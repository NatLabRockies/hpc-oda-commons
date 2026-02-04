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
