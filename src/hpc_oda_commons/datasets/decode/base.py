"""
Decoders turn a dataset's fetched raw files into a single intermediate Parquet
file that the normalize stage can map onto a canonical ODA schema.

Supported inner formats: ``parquet``, ``csv`` (also TSV via a delimiter option), and
``swf`` (Standard Workload Format). Fetched resources may additionally be compressed
or archived -- ``.gz`` (single file), ``.zip``, or ``.tar``/``.tar.gz`` -- in which
case the contained files matching the inner format are transparently extracted and
concatenated. Other inner formats (``json``/``log``) are declared in the descriptor
schema but not yet implemented and raise a clear error.
"""

from __future__ import annotations

import fnmatch
import gzip
import shutil
import tarfile
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_FORMAT_EXTS: dict[str, tuple[str, ...]] = {
    "parquet": (".parquet",),
    "csv": (".csv", ".tsv", ".txt"),
    "swf": (".swf",),
    "json": (".json",),
}


class DecodeError(Exception):
    """Raised when a dataset's raw files cannot be decoded."""


def _members(dest: Path, exts: tuple[str, ...], member_glob: str | None) -> list[Path]:
    """Extracted files matching the inner format, optionally filtered to a member glob
    (matched against filename or the archive-relative path, e.g. ``*/cluster_log.csv``)."""

    def keep(p: Path) -> bool:
        if p.suffix.lower() not in exts:
            return False
        if member_glob is None:
            return True
        rel = p.relative_to(dest).as_posix()
        return fnmatch.fnmatch(p.name, member_glob) or fnmatch.fnmatch(rel, member_glob)

    return sorted(p for p in dest.rglob("*") if keep(p))


def _extract_one(
    path: Path, exts: tuple[str, ...], workdir: Path, member_glob: str | None = None
) -> list[Path]:
    """Expand a single fetched file into decodable inner files (or itself if plain)."""
    name = path.name.lower()
    if name.endswith(".zip"):
        dest = Path(tempfile.mkdtemp(dir=workdir))
        with zipfile.ZipFile(path) as archive:
            archive.extractall(dest)
        return _members(dest, exts, member_glob)
    if name.endswith((".tar.gz", ".tgz", ".tar")):
        dest = Path(tempfile.mkdtemp(dir=workdir))
        with tarfile.open(path) as archive:
            archive.extractall(dest)  # checksum-verified, trusted sources
        return _members(dest, exts, member_glob)
    if name.endswith(".gz"):
        inner = Path(tempfile.mkdtemp(dir=workdir)) / path.name[: -len(".gz")]
        with gzip.open(path, "rb") as src, inner.open("wb") as out:
            shutil.copyfileobj(src, out)
        return [inner]
    return [path]


def _expand(
    files: Sequence[Path], exts: tuple[str, ...], workdir: Path, member_glob: str | None = None
) -> list[Path]:
    expanded: list[Path] = []
    for f in files:
        expanded.extend(_extract_one(Path(f), exts, workdir, member_glob))
    if not expanded:
        raise DecodeError(f"no files matching {exts} found after extraction")
    return expanded


def decode_to_parquet(
    fmt: str,
    files: Sequence[Path],
    dest: Path,
    *,
    options: Mapping[str, Any] | None = None,
) -> None:
    """Decode ``files`` (of inner format ``fmt``) into a single Parquet file at ``dest``.

    Archived/compressed resources (.gz / .zip / .tar / .tar.gz) are extracted first and
    their ``fmt``-matching members concatenated with the plain inputs.
    """
    options = dict(options or {})
    exts = _FORMAT_EXTS.get(fmt)
    if exts is None:
        raise DecodeError(f"unsupported decode format: {fmt!r} (supported: parquet, csv)")

    with tempfile.TemporaryDirectory() as tmp:
        expanded = _expand(files, exts, Path(tmp), options.get("member_glob"))
        if fmt == "parquet":
            from hpc_oda_commons.datasets.decode.parquet import decode_parquet

            decode_parquet(expanded, dest, options=options)
        elif fmt == "swf":
            from hpc_oda_commons.datasets.decode.swf import decode_swf

            decode_swf(expanded, dest)
        elif fmt == "json":
            from hpc_oda_commons.datasets.decode.json import decode_json

            decode_json(expanded, dest, options=options)
        else:  # csv (incl. TSV via options.delimiter)
            from hpc_oda_commons.datasets.decode.csv import decode_csv

            decode_csv(expanded, dest, options=options)
