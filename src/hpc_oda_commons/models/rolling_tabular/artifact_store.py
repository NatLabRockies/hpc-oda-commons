"""
On-disk cache for the rolling-tabular daily preprocessing artifacts (#213).

Building a day's OHE + SVD artifacts is the dominant cost of a rolling-tabular run: on
F-DATA's 60-day lookback it is ~100 s per day, serial, before any window is fitted. And the
work is the same for every model on the same table and protocol -- XGBoost, Random Forest,
MLP and the MoE's shared part all build identical artifacts, as do runs on different targets
over the same rows. This store builds each one once.

Entries are keyed by **content**, not by dataset ids or split parameters: a SHA-256 over the
training rows' values in the columns the build reads, the settings it reads, a builder
version and the library versions. A hit therefore returns what a fresh build would have
produced from the same inputs, and any change to the rows or settings is a miss.

Entries are pickles. Only point the store at a directory this tool writes and you control:
unpickling runs code, so a store is not a way to exchange artifacts with anyone else.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import pickle
import tempfile
import warnings
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

# Bump whenever the daily build changes what it produces from the same inputs, so entries
# written by the old build stop matching.
DAILY_ARTIFACTS_VERSION = 1

# The environment variable that moves (a path) or disables (``off``) the benchmark runner's
# store.
CACHE_ENV = "HPC_ODA_PREPROCESSING_CACHE"
_DISABLED = frozenset({"off", "0", "false", "no", "none"})


def _library_versions() -> dict[str, str]:
    """The libraries whose numerics or pickled objects an entry depends on."""
    versions: dict[str, str] = {}
    for package in ("sklearn", "numpy", "scipy"):
        try:
            versions[package] = str(importlib.import_module(package).__version__)
        except Exception:  # noqa: BLE001 - an absent library is recorded, not fatal
            versions[package] = "unavailable"
    return versions


def _column_bytes(values: list[Any]) -> bytes:
    """A byte encoding that tells apart every value the build can tell apart.

    ``repr`` keeps types (``1``, ``1.0`` and ``True`` differ, and the column detection
    depends on that) and round-trips floats exactly. Arrays are the exception: their repr
    elides long contents with ``...``, so they contribute their raw bytes instead.
    """
    if not any(isinstance(v, np.ndarray) for v in values):
        return repr(values).encode("utf-8")
    parts: list[bytes] = []
    for v in values:
        if isinstance(v, np.ndarray):
            parts.append(f"<ndarray {v.dtype.str} {v.shape}>".encode())
            parts.append(np.ascontiguousarray(v).tobytes())
        else:
            parts.append(repr(v).encode("utf-8"))
        parts.append(b"\x1f")
    return b"".join(parts)


def daily_artifacts_key(
    rows: Sequence[Mapping[str, Any]],
    *,
    columns: Sequence[str],
    settings: Mapping[str, Any],
) -> str:
    """The content key for one day's artifacts.

    ``columns`` must name every column the build reads, and ``settings`` every setting; the
    caller is the one that knows (``RollingTabularModel._daily_artifacts_key``).
    """
    digest = hashlib.sha256()
    header = {
        "version": DAILY_ARTIFACTS_VERSION,
        "libraries": _library_versions(),
        "settings": dict(settings),
        "columns": list(columns),
        "rows": len(rows),
    }
    digest.update(json.dumps(header, sort_keys=True, default=str).encode("utf-8"))
    for column in columns:
        digest.update(b"\x1e" + column.encode("utf-8") + b"\x1e")
        digest.update(_column_bytes([row.get(column) for row in rows]))
    return digest.hexdigest()


class DailyArtifactStore:
    """A directory of daily artifacts, one pickle per content key.

    Writes go to a temporary file and are renamed into place, so concurrent runs sharing a
    directory (array jobs on a cluster) never read a half-written entry. An entry that cannot
    be read is treated as a miss and rebuilt.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.pkl"

    def load(self, key: str) -> Any | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            with path.open("rb") as fh:
                return pickle.load(fh)
        except Exception as exc:  # noqa: BLE001 - any unreadable entry is a miss
            warnings.warn(
                f"ignoring unreadable preprocessing cache entry {path.name}: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            return None

    def save(self, key: str, value: Any) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{key[:8]}-", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                pickle.dump(value, fh, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def default_artifact_store(cwd: Path | None = None) -> DailyArtifactStore | None:
    """The benchmark runner's store: ``.hpc_oda/cache/preprocessing`` under the working
    directory, or wherever ``HPC_ODA_PREPROCESSING_CACHE`` points; ``off`` disables it."""
    env = os.environ.get(CACHE_ENV, "").strip()
    if env.lower() in _DISABLED:
        return None
    if env:
        return DailyArtifactStore(Path(env).expanduser())
    return DailyArtifactStore((cwd or Path.cwd()) / ".hpc_oda" / "cache" / "preprocessing")
