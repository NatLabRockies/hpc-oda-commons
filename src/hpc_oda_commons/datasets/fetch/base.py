"""
Fetch orchestration for public dataset descriptors.

Network access is quarantined here: fetching is opt-in, every resource is verified
against its descriptor ``sha256``, results are cached and reused, and a per-dataset
lockfile records exactly what was retrieved. Under offline mode only already-cached
(checksum-verified) resources are usable.

The actual byte transfer is delegated to a backend (``http`` for direct downloads,
``manual`` for gated datasets); this module owns slice selection, the size
guardrail, the offline gate, checksum verification, cache reuse, and the lockfile.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hpc_oda_commons.datasets.descriptor import Descriptor

DEFAULT_MAX_BYTES = 5 * 10**9  # 5 GB refuse-by-default guardrail
_CHUNK = 1 << 20  # 1 MiB


class FetchError(Exception):
    """Base class for fetch failures."""


class SizeLimitExceeded(FetchError):
    def __init__(self, selected_bytes: int, limit: int) -> None:
        self.selected_bytes = selected_bytes
        self.limit = limit
        super().__init__(
            f"selected download is {selected_bytes} bytes, at/above the {limit}-byte limit"
        )


class UnknownSizeError(FetchError):
    def __init__(self) -> None:
        super().__init__("selected download size is unknown; confirm to proceed")


class OfflineError(FetchError):
    def __init__(self, filename: str) -> None:
        self.filename = filename
        super().__init__(f"offline: '{filename}' is not cached")


class ChecksumMismatch(FetchError):
    def __init__(self, filename: str, expected: str, actual: str) -> None:
        self.filename = filename
        self.expected = expected
        self.actual = actual
        super().__init__(f"checksum mismatch for '{filename}': expected {expected}, got {actual}")


class ManualFetchRequired(FetchError):
    def __init__(self, filename: str, instructions: str) -> None:
        self.filename = filename
        self.instructions = instructions
        super().__init__(f"manual fetch required for '{filename}'")


@dataclass(frozen=True)
class CachedResource:
    filename: str
    path: Path
    sha256: str
    bytes: int | None
    reused: bool


@dataclass(frozen=True)
class FetchResult:
    dataset_id: str
    slice: str | None
    resources: tuple[CachedResource, ...]
    lockfile_path: Path
    total_bytes: int
    unknown_size: bool


def parse_size(value: str | int) -> int:
    """Parse a human size like '5GB' / '500MB' / '2GiB' (or an int of bytes)."""
    if isinstance(value, int):
        return value
    text = value.strip().upper()
    units = {
        "TIB": 2**40,
        "GIB": 2**30,
        "MIB": 2**20,
        "KIB": 2**10,
        "TB": 10**12,
        "GB": 10**9,
        "MB": 10**6,
        "KB": 10**3,
        "B": 1,
    }
    for suffix in sorted(units, key=len, reverse=True):
        if text.endswith(suffix):
            number = text[: -len(suffix)].strip()
            return int(float(number) * units[suffix])
    return int(float(text))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def select_resources(
    source: Mapping[str, Any], *, slice_name: str | None, select_all: bool
) -> tuple[list[dict[str, Any]], str | None]:
    """Resolve which resources to fetch, applying named slices if present."""
    resources = [dict(r) for r in (source.get("resources") or [])]
    slices = source.get("slices")
    if not slices:
        if slice_name:
            raise FetchError("descriptor defines no slices; drop --slice")
        return resources, None
    if select_all:
        return resources, "all"
    name = slice_name or slices.get("default")
    available = slices.get("available") or {}
    if name not in available:
        raise FetchError(f"unknown slice '{name}'")
    globs = available[name].get("include") or []
    selected = [
        r for r in resources if any(fnmatch.fnmatch(str(r.get("filename")), g) for g in globs)
    ]
    if not selected:
        raise FetchError(f"slice '{name}' matched no resources")
    return selected, str(name)


def _selected_size(resources: Sequence[Mapping[str, Any]]) -> tuple[int, bool]:
    total = 0
    unknown = False
    for resource in resources:
        raw = resource.get("bytes")
        if raw is None:
            unknown = True
        else:
            total += int(raw)
    return total, unknown


def _materialize(
    kind: str,
    resource: Mapping[str, Any],
    dest: Path,
    *,
    source: Mapping[str, Any],
    source_dir: Path | None,
) -> None:
    if kind == "manual":
        from hpc_oda_commons.datasets.fetch.manual import materialize_manual

        materialize_manual(resource, dest, source=source, source_dir=source_dir)
    else:
        from hpc_oda_commons.datasets.fetch.http import materialize_http

        materialize_http(resource, dest)


def _tool_version() -> str:
    try:
        from importlib.metadata import version

        return version("hpc-oda-commons")
    except Exception:  # pragma: no cover - metadata may be unavailable
        return "0.0.0"


def _write_lockfile(
    dataset_cache: Path,
    descriptor: Descriptor,
    slice_name: str | None,
    cached: Sequence[CachedResource],
    descriptor_sha256: str | None,
) -> Path:
    payload = {
        "dataset_id": descriptor.dataset_id,
        "descriptor_version": descriptor.version,
        "descriptor_sha256": descriptor_sha256,
        "slice": slice_name,
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "tool_version": _tool_version(),
        "resources": [
            {"filename": r.filename, "sha256": r.sha256, "bytes": r.bytes} for r in cached
        ],
    }
    dataset_cache.mkdir(parents=True, exist_ok=True)
    lockfile_path = dataset_cache / f"{descriptor.dataset_id}.lock.json"
    lockfile_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return lockfile_path


def fetch_descriptor(
    descriptor: Descriptor,
    *,
    cache_dir: Path,
    slice_name: str | None = None,
    select_all: bool = False,
    max_bytes: int = DEFAULT_MAX_BYTES,
    allow_large: bool = False,
    offline: bool = False,
    assume_yes: bool = False,
    source_dir: Path | None = None,
    descriptor_sha256: str | None = None,
) -> FetchResult:
    """
    Fetch a descriptor's selected resources into ``cache_dir/<dataset_id>/raw`` and
    write ``<dataset_id>.lock.json``.

    Resources already cached with a matching ``sha256`` are reused (idempotent).
    The size guardrail refuses selections at/above ``max_bytes`` unless
    ``allow_large``; unknown total size requires ``assume_yes``. When ``offline``,
    any resource not already cached raises :class:`OfflineError`.
    """
    source = descriptor.source
    kind = str(source.get("kind"))
    resources, resolved_slice = select_resources(
        source, slice_name=slice_name, select_all=select_all
    )
    total, unknown = _selected_size(resources)

    if unknown and not assume_yes:
        raise UnknownSizeError()
    if not unknown and not allow_large and total >= max_bytes:
        raise SizeLimitExceeded(total, max_bytes)

    dataset_cache = Path(cache_dir) / descriptor.dataset_id
    raw_dir = dataset_cache / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    cached: list[CachedResource] = []
    for resource in resources:
        filename = str(resource.get("filename"))
        expected = str(resource.get("sha256"))
        dest = raw_dir / filename

        if dest.exists() and sha256_file(dest) == expected:
            cached.append(CachedResource(filename, dest, expected, resource.get("bytes"), True))
            continue
        if offline:
            raise OfflineError(filename)

        _materialize(kind, resource, dest, source=source, source_dir=source_dir)

        actual = sha256_file(dest)
        if actual != expected:
            dest.unlink(missing_ok=True)
            raise ChecksumMismatch(filename, expected, actual)
        cached.append(CachedResource(filename, dest, expected, resource.get("bytes"), False))

    lockfile_path = _write_lockfile(
        dataset_cache, descriptor, resolved_slice, cached, descriptor_sha256
    )
    return FetchResult(
        dataset_id=descriptor.dataset_id,
        slice=resolved_slice,
        resources=tuple(cached),
        lockfile_path=lockfile_path,
        total_bytes=total,
        unknown_size=unknown,
    )
