"""
Decoders turn a dataset's fetched raw files into a single intermediate Parquet
file that the normalize stage can map onto a canonical ODA schema.

P3 supports ``parquet`` and ``csv``; ``swf``/``json``/``log``/``tar`` are declared
in the descriptor schema but not yet implemented (they serve the deferred Parallel
Workloads Archive and log corpora) and raise a clear error.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


class DecodeError(Exception):
    """Raised when a dataset's raw files cannot be decoded."""


def decode_to_parquet(
    fmt: str,
    files: Sequence[Path],
    dest: Path,
    *,
    options: Mapping[str, Any] | None = None,
) -> None:
    """Decode ``files`` (of format ``fmt``) into a single Parquet file at ``dest``."""
    options = dict(options or {})
    if fmt == "parquet":
        from hpc_oda_commons.datasets.decode.parquet import decode_parquet

        decode_parquet(files, dest)
    elif fmt == "csv":
        from hpc_oda_commons.datasets.decode.csv import decode_csv

        decode_csv(files, dest, options=options)
    else:
        raise DecodeError(f"unsupported decode format: {fmt!r} (P3 supports parquet, csv)")
