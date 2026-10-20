"""Every relative Markdown link in the docs resolves, anchors included (#232).

Moving or renaming a doc used to break links silently. This walks the repository's own
Markdown (the root files and everything under docs/), skips fenced and inline code, and
checks each relative link's file, and its ``#anchor`` against the target's headings as
GitHub renders them.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = sorted([*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md")])

_FENCE = re.compile(r"^(```|~~~).*?^\1", re.MULTILINE | re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$", re.MULTILINE)
_HTML_ID = re.compile(r"<a\s+(?:name|id)=\"([^\"]+)\"")


def _strip_code(text: str) -> str:
    return _INLINE_CODE.sub("", _FENCE.sub("", text))


def _slug(heading: str) -> str:
    """GitHub's heading anchor: link text kept, punctuation dropped, spaces to hyphens."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading).lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


@cache
def _anchors(path: Path) -> frozenset[str]:
    text = _FENCE.sub("", path.read_text(encoding="utf-8"))
    seen: dict[str, int] = {}
    anchors = set(_HTML_ID.findall(text))
    for heading in _HEADING.findall(text):
        slug = _slug(heading)
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    return frozenset(anchors)


def _broken_links(doc: Path) -> list[str]:
    broken = []
    for target in _LINK.findall(_strip_code(doc.read_text(encoding="utf-8"))):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
            continue  # http:, https:, mailto: ...
        path_part, _, anchor = target.partition("#")
        resolved = (doc.parent / path_part).resolve() if path_part else doc
        if not resolved.exists():
            broken.append(f"{target}: no such file")
        elif anchor and resolved.suffix == ".md" and anchor not in _anchors(resolved):
            broken.append(f"{target}: no heading #{anchor}")
    return broken


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_relative_links_resolve(doc: Path) -> None:
    assert _broken_links(doc) == []


def test_slug_matches_github() -> None:
    assert _slug("Our reproduction (θ = 500, k = 20)") == "our-reproduction-θ--500-k--20"
    assert _slug("Nodes requested, not allocated") == "nodes-requested-not-allocated"
    assert _slug("`cutoff` — the paper protocol") == "cutoff--the-paper-protocol"
