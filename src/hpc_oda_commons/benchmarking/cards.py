"""Assemble, render, and write **dataset cards**.

A dataset card is the single source of truth for a dataset's benchmark use: it records the
characterization and the chosen rolling-benchmark window (with rationale), as machine-readable
JSON (``<stem>.card.json``, validated against ``oda.dataset_card.v0.1.0``) plus a human-readable
Markdown rendering (``<stem>.md``). The benchmark runner consumes the JSON; people read the MD.
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


def render_card_markdown(card: dict[str, Any]) -> str:
    """Render a dataset card as human-readable Markdown."""
    char = card["characterization"]
    win = card["benchmark_window"]
    hs = char.get("healthy_span", {})
    dv = char.get("daily_volume", {})
    src = card.get("source", {})
    lines: list[str] = []

    lines.append(f"# Dataset card — `{card['dataset_id']}`")
    lines.append("")
    lines.append(f"*Generated {card['generated_at']} · schema `{card['schema_version']}`.*")
    lines.append("")
    if src.get("system") or src.get("descriptor"):
        lines.append(
            f"**System:** {src.get('system', '?')}  ·  **Descriptor:** "
            f"`{src.get('descriptor', '?')}`"
        )
        lines.append("")

    lines.append("## Characterization")
    lines.append("")
    lines.append(f"- **Rows:** {_fmt_int(char.get('n_rows'))}")
    lines.append(
        f"- **Healthy span:** {hs.get('start')} → {hs.get('end')} "
        f"({_fmt_int(hs.get('days'))} days, {_fmt_int(hs.get('rows'))} rows)"
    )
    lines.append(f"- **Job rate:** {_fmt_int(char.get('rate_per_day'))} jobs/day (span avg)")
    lines.append(
        f"- **Daily volume:** median {_fmt_int(dv.get('median'))}, "
        f"min {_fmt_int(dv.get('min'))}, max {_fmt_int(dv.get('max'))} "
        f"(gap floor {_fmt_int(dv.get('gap_floor'))})"
    )
    gaps = char.get("gaps", [])
    if gaps:
        lines.append(f"- **Missing blocks (span):** {len(gaps)}")
        for g in gaps:
            lines.append(f"    - {g['start']} → {g['end']} ({g['days']} days)")
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
        lines.append("")
        lines.append("| feature | distinct | missing % |")
        lines.append("|---|---:|---:|")
        for name, meta in cols.items():
            lines.append(
                f"| `{name}` | {_fmt_int(meta.get('cardinality'))} | "
                f"{100 * meta.get('missingness', 0):.1f} |"
            )

    lines.append("")
    lines.append("## Benchmark window")
    lines.append("")
    rule = win.get("rule", {})
    verdict = "✅ healthy" if win.get("healthy") else "⚠️ UNHEALTHY"
    lines.append(
        f"- **Window:** {win.get('window_start')} → {win.get('window_end')} "
        f"({rule.get('train_days')}d train + {rule.get('test_days')}d test)"
    )
    lines.append(f"- **Test period:** {win.get('test_start')} → {win.get('test_end')}")
    lines.append(
        f"- **Rows in window:** {_fmt_int(win.get('n_rows'))} "
        f"({_fmt_int(win.get('rate_per_day'))} jobs/day)"
    )
    lines.append(f"- **Anchor:** {rule.get('anchor')} of healthy span")
    lines.append(f"- **Health:** {verdict}")
    lines.append(f"- **Rationale:** {win.get('rationale')}")

    decisions = card.get("decisions", [])
    if decisions:
        lines.append("")
        lines.append("## Decisions")
        lines.append("")
        for d in decisions:
            lines.append(f"- {d}")

    prov = card.get("provenance", {})
    code = prov.get("code", {})
    lines.append("")
    lines.append("---")
    lines.append(
        f"*Provenance: git `{code.get('git_commit', '?')}`, "
        f"package `{code.get('package_version', '?')}`.*"
    )
    lines.append("")
    return "\n".join(lines)


def write_card(card: dict[str, Any], out_dir: Path, *, stem: str) -> tuple[Path, Path]:
    """Write ``<stem>.card.json`` + ``<stem>.md`` under ``out_dir``. Returns both paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{stem}.card.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(card, indent=2, sort_keys=False) + "\n")
    md_path.write_text(render_card_markdown(card))
    return json_path, md_path
