"""
Stdlib HTTP(S)/file backend for dataset fetching.

Uses only :mod:`urllib` — no third-party HTTP dependency — so it covers direct
downloads from Zenodo/OSTI/OEDI/GitHub and ``file://`` URLs (used by tests).
Downloads stream to a ``.part`` sidecar and are atomically moved into place; the
caller verifies the checksum afterwards.
"""

from __future__ import annotations

import shutil
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from hpc_oda_commons.datasets.fetch.base import FetchError

_TIMEOUT_SECONDS = 60


def materialize_http(resource: Mapping[str, Any], dest: Path) -> None:
    url = resource.get("url")
    if not url:
        raise FetchError(f"resource '{resource.get('filename')}' has no url")

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest.with_name(dest.name + ".part")
    try:
        with urllib.request.urlopen(str(url), timeout=_TIMEOUT_SECONDS) as response:
            with tmp_path.open("wb") as out:
                shutil.copyfileobj(response, out)
        tmp_path.replace(dest)
    except FetchError:
        tmp_path.unlink(missing_ok=True)
        raise
    except Exception as exc:  # pragma: no cover - network/file errors
        tmp_path.unlink(missing_ok=True)
        raise FetchError(f"failed to fetch {url}: {exc}") from exc
