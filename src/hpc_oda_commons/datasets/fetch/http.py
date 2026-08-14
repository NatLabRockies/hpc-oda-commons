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
_HTML_MARKERS = (b"<!doctype html", b"<html")
_HTML_SUFFIXES = (".htm", ".html")


def _reject_html_payload(resource: Mapping[str, Any], path: Path, content_type: str) -> None:
    """Fail loudly when the response body is a web page rather than the pinned file.

    A landing/login page or a network appliance's block notice is served with HTTP
    200, so it lands on disk as a plausible-looking download and only surfaces later
    as a checksum mismatch — which reads as "the source file changed" and sends
    people off to re-pin a sha256 that was never wrong.
    """
    filename = str(resource.get("filename", ""))
    if filename.lower().endswith(_HTML_SUFFIXES):
        return
    with path.open("rb") as handle:
        head = handle.read(512)
    if not head.lstrip()[:16].lower().startswith(_HTML_MARKERS):
        return
    detail = f", Content-Type: {content_type}" if content_type else ""
    raise FetchError(
        f"'{filename}': the server returned an HTML page ({path.stat().st_size} bytes"
        f"{detail}) instead of the file. Either the URL now points at a landing or login "
        "page, or the request was answered before it reached the source (captive portal, "
        "proxy, or filtering appliance). Fetch the URL by hand and look at what comes "
        "back — the pinned sha256 is likely still correct."
    )


def materialize_http(resource: Mapping[str, Any], dest: Path) -> None:
    url = resource.get("url")
    if not url:
        raise FetchError(f"resource '{resource.get('filename')}' has no url")

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest.with_name(dest.name + ".part")
    try:
        with urllib.request.urlopen(str(url), timeout=_TIMEOUT_SECONDS) as response:
            content_type = str(response.headers.get("Content-Type", "") or "")
            with tmp_path.open("wb") as out:
                shutil.copyfileobj(response, out)
        _reject_html_payload(resource, tmp_path, content_type)
        tmp_path.replace(dest)
    except FetchError:
        tmp_path.unlink(missing_ok=True)
        raise
    except Exception as exc:  # pragma: no cover - network/file errors
        tmp_path.unlink(missing_ok=True)
        raise FetchError(f"failed to fetch {url}: {exc}") from exc
