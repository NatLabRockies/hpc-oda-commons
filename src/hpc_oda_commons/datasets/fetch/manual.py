"""
Manual/gated backend.

Some datasets require registration, a survey, or an on-request agreement and
cannot be downloaded programmatically. For these (``source.kind == "manual"``),
the descriptor pins the expected ``sha256`` and provides ``instructions``. This
backend copies a user-supplied file from ``--from`` (if given) and lets the caller
verify its checksum; otherwise it raises :class:`ManualFetchRequired` with the
instructions. A file already present in the cache with a matching checksum is
reused by the orchestrator before this backend is ever called.
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from hpc_oda_commons.datasets.fetch.base import ManualFetchRequired


def materialize_manual(
    resource: Mapping[str, Any],
    dest: Path,
    *,
    source: Mapping[str, Any],
    source_dir: Path | None,
) -> None:
    filename = str(resource.get("filename"))
    if source_dir is not None:
        candidate = Path(source_dir) / filename
        if candidate.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate, dest)
            return
    instructions = str(source.get("instructions") or "This dataset must be obtained manually.")
    raise ManualFetchRequired(filename, instructions)
