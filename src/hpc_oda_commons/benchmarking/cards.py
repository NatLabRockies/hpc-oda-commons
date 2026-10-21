"""Assemble, render, and write **dataset cards**.

A dataset card is the single source of truth for a dataset's benchmark use: it records the
characterization and the chosen rolling-benchmark window (with rationale), as machine-readable
JSON (``<stem>.card.json``, validated against ``oda.dataset_card.v0.1.0``). The benchmark runner
consumes the JSON; people read it in the dataset's generated card (#249).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hpc_oda_commons.benchmarking.characterize import CARD_SCHEMA_VERSION
from hpc_oda_commons.kernel.provenance import build_provenance


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_card(
    dataset_id: str,
    table_path: Path,
    characterization: dict[str, Any],
    window: dict[str, Any],
    *,
    source: dict[str, Any] | None = None,
    decisions: list[str] | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Assemble a dataset-card dict from a characterization + window choice.

    ``characterization`` may still carry the private ``_daily`` series; it is stripped here.
    """
    char = {k: v for k, v in characterization.items() if not k.startswith("_")}
    provenance = build_provenance(
        input_schema="oda.job.v0.2.0",
        result_schema=CARD_SCHEMA_VERSION,
        inputs=[table_path],
        project_root=project_root,
    )
    return {
        "schema_version": CARD_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "generated_at": _now_iso(),
        "source": {"table_path": str(table_path), **(source or {})},
        "characterization": char,
        "benchmark_window": window,
        "decisions": decisions or [],
        "provenance": provenance,
    }


def _fmt_int(x: Any) -> str:
    try:
        return f"{int(x):,}"
    except (TypeError, ValueError):
        return str(x)


def characterization_lines(card: dict[str, Any]) -> list[str]:
    """A card's characterization of its table, as Markdown lines (no heading)."""
    char = card["characterization"]
    hs = char.get("healthy_span", {})
    dv = char.get("daily_volume", {})
    lines = [
        f"- **Rows:** {_fmt_int(char.get('n_rows'))}",
        f"- **Healthy span:** {hs.get('start')} → {hs.get('end')} "
        f"({_fmt_int(hs.get('days'))} days, {_fmt_int(hs.get('rows'))} rows)",
        f"- **Job rate:** {_fmt_int(char.get('rate_per_day'))} jobs/day (span avg)",
        f"- **Daily volume:** median {_fmt_int(dv.get('median'))}, "
        f"min {_fmt_int(dv.get('min'))}, max {_fmt_int(dv.get('max'))} "
        f"(gap floor {_fmt_int(dv.get('gap_floor'))})",
    ]
    gaps = char.get("gaps", [])
    if gaps:
        lines.append(f"- **Missing blocks (span):** {len(gaps)}")
        lines.extend(f"    - {g['start']} → {g['end']} ({g['days']} days)" for g in gaps)
    else:
        lines.append("- **Missing blocks (span):** none")
    rt = char.get("runtime_seconds", {})
    if rt:
        lines.append(
            f"- **Runtime (s):** median {_fmt_int(rt.get('median'))}, "
            f"p90 {_fmt_int(rt.get('p90'))}, p99 {_fmt_int(rt.get('p99'))}, "
            f"max {_fmt_int(rt.get('max'))}"
        )
    cols = char.get("columns", {})
    if cols:
        lines += ["", "| feature | distinct | missing % |", "|---|---:|---:|"]
        lines.extend(
            f"| `{name}` | {_fmt_int(meta.get('cardinality'))} | "
            f"{100 * meta.get('missingness', 0):.1f} |"
            for name, meta in cols.items()
        )
    return lines


def window_lines(card: dict[str, Any]) -> list[str]:
    """A card's benchmark window and the decisions behind it, as Markdown lines."""
    win = card["benchmark_window"]
    rule = win.get("rule", {})
    verdict = "✅ healthy" if win.get("healthy") else "⚠️ UNHEALTHY"
    lines = [
        f"- **Window:** {win.get('window_start')} → {win.get('window_end')} "
        f"({rule.get('train_days')}d train + {rule.get('test_days')}d test)",
        f"- **Test period:** {win.get('test_start')} → {win.get('test_end')}",
        f"- **Rows in window:** {_fmt_int(win.get('n_rows'))} "
        f"({_fmt_int(win.get('rate_per_day'))} jobs/day)",
        f"- **Pinned:** ends {rule['pinned_end']}, the window the benchmark ran on"
        if rule.get("pinned_end")
        else f"- **Anchor:** {rule.get('anchor')} of healthy span",
        f"- **Health:** {verdict}",
        f"- **Rationale:** {win.get('rationale')}",
    ]
    lines.extend(f"- **Decision:** {d}" for d in card.get("decisions", []))
    return lines


def write_card(card: dict[str, Any], out_dir: Path, *, stem: str) -> Path:
    """Write ``<stem>.card.json`` under ``out_dir`` and return its path. People read it in
    the dataset's generated card (``hpc-oda datasets cards``, #249)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{stem}.card.json"
    json_path.write_text(json.dumps(card, indent=2, sort_keys=False) + "\n")
    return json_path
