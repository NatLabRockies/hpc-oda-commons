"""docs/benchmarking/runtime/ceilings.md copies its tables from the ceiling JSON (#257).

The tables are written by hand for reading, so this test holds them to the committed
`docs/benchmarking/datasets/*.ceiling.json`: regenerate a ceiling and the page must follow.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "docs" / "benchmarking" / "runtime" / "ceilings.md"
CEILINGS = ROOT / "docs" / "benchmarking" / "datasets"
LOOKBACKS = ("1d", "10d", "30d", "60d", "120d", "all")


def _runtime_ceilings() -> dict[str, dict]:
    out = {}
    for path in sorted(CEILINGS.glob("*.ceiling.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("target_field", "runtime_seconds") == "runtime_seconds":
            out[path.name.removesuffix(".ceiling.json")] = data
    return out


def _rows(section: str) -> dict[str, list[str]]:
    """The table under a heading, as dataset -> cells."""
    text = PAGE.read_text(encoding="utf-8").split(f"## {section}", 1)[1].split("\n## ", 1)[0]
    rows = {}
    for line in text.splitlines():
        match = re.match(r"\| `([a-z0-9_]+)` \|(.*)\|\s*$", line)
        if match:
            rows[match.group(1)] = [c.strip() for c in match.group(2).split("|")]
    return rows


def _n(value: float) -> str:
    return f"{round(value):,}"


def _pct(share: float) -> str:
    return f"{share * 100:.1f}%"


def test_every_runtime_ceiling_is_on_the_page() -> None:
    ceilings = _runtime_ceilings()
    for section in ("The floor, per dataset", "How tight is each bound?", "Causal memorization"):
        assert sorted(_rows(section)) == sorted(ceilings), section


def test_the_floor_table_matches_the_json() -> None:
    for name, cells in _rows("The floor, per dataset").items():
        data = _runtime_ceilings()[name]
        floor = data["floor"]
        expected = [_n(data["scored_rows"]), _n(floor["signatures"])]
        expected += [_n(floor["mae"]), _n(floor["rmse"])]
        assert cells == expected, name


def test_the_tightness_table_matches_the_json() -> None:
    for name, cells in _rows("How tight is each bound?").items():
        sizes = _runtime_ceilings()[name]["floor"]["group_sizes"]
        median = f"{sizes['median']:g}"
        assert cells[0] == f"{_n(sizes['min'])} / {median} / {_n(sizes['max'])}", name
        assert cells[1].split()[0] == _pct(sizes["singleton_row_share"]), name


def test_the_memorization_table_matches_the_json() -> None:
    best_counts: Counter[str] = Counter()
    for name, cells in _rows("Causal memorization").items():
        memo = _runtime_ceilings()[name]["causal_memorization"]
        best = memo["best_lookback"]
        best_counts[best] += 1
        for lookback, cell in zip(LOOKBACKS, cells, strict=False):
            mae = _n(memo["sweep"][lookback]["mae"])
            assert cell == (f"**{mae}**" if lookback == best else mae), (name, lookback)
        assert cells[6] == best, name
        assert cells[7] == f"{round(memo['sweep'][best]['coverage'] * 100)}%", name
    summary = ", ".join(f"{lb} ×{best_counts[lb]}" for lb in LOOKBACKS if best_counts[lb])
    assert f"Optimal lookback: {summary}." in PAGE.read_text(encoding="utf-8")
