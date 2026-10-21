"""
Lightweight HTML report builder for local results.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from hpc_oda_commons.benchmark.leaderboard_display import (
    format_created_at,
    format_headroom,
    format_metric_value,
    metric_column_label,
    prepare_leaderboard_rows,
    short_registry_id,
)

_STYLE = """
    :root {
      --bg: #f7f8fb;
      --card: #ffffff;
      --text: #1f2937;
      --muted: #6b7280;
      --border: #e5e7eb;
      --accent: #2563eb;
      --best: #ecfdf5;
      --best-text: #047857;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
      background: linear-gradient(180deg, #eef2ff 0%, var(--bg) 180px);
      color: var(--text);
    }
    .page {
      max-width: 1280px;
      margin: 0 auto;
      padding: 2rem 1.25rem 3rem;
    }
    .hero {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 1.5rem 1.75rem;
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
      margin-bottom: 1.25rem;
    }
    h1 {
      margin: 0 0 0.35rem;
      font-size: 1.75rem;
      letter-spacing: -0.02em;
    }
    .meta {
      color: var(--muted);
      font-size: 0.95rem;
      line-height: 1.5;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
    }
    .table-wrap {
      overflow-x: auto;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.95rem;
    }
    thead th {
      position: sticky;
      top: 0;
      background: #f9fafb;
      color: #374151;
      text-align: left;
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      padding: 0.85rem 1rem;
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }
    tbody td {
      padding: 0.9rem 1rem;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }
    tbody tr:hover {
      background: #fafbff;
    }
    tbody tr:last-child td {
      border-bottom: none;
    }
    .recipe, .model {
      font-weight: 600;
      color: #111827;
    }
    .muted {
      color: var(--muted);
    }
    .metric {
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
      font-weight: 600;
    }
    .metric.best {
      background: var(--best);
      color: var(--best-text);
    }
    .nowrap {
      white-space: nowrap;
    }
    .col-run {
      width: 1%;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
      color: var(--muted);
      font-size: 0.88rem;
    }
    .col-train {
      width: 1%;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
      font-weight: 600;
      position: sticky;
      right: 0;
      background: var(--card);
      box-shadow: -8px 0 8px -6px rgba(15, 23, 42, 0.08);
    }
    thead .col-train {
      background: #f9fafb;
      z-index: 2;
    }
    tbody tr:hover .col-train {
      background: #fafbff;
    }
    .empty {
      text-align: center;
      color: var(--muted);
      padding: 2rem;
    }
    .legend {
      margin-top: 1rem;
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.5;
    }
    .pill {
      display: inline-block;
      background: #eff6ff;
      color: #1d4ed8;
      border-radius: 999px;
      padding: 0.15rem 0.55rem;
      font-size: 0.8rem;
      font-weight: 600;
      margin-left: 0.35rem;
    }
    h2 {
      margin: 0;
      padding: 1rem 1.25rem 0.25rem;
      font-size: 1.15rem;
    }
    .section-note {
      color: var(--muted);
      font-size: 0.9rem;
      padding: 0 1.25rem 0.75rem;
    }
    .card + .card {
      margin-top: 1.25rem;
    }
    .cell-main {
      display: block;
      font-variant-numeric: tabular-nums;
      font-weight: 600;
    }
    .cell-sub {
      display: block;
      color: var(--muted);
      font-size: 0.8rem;
      font-variant-numeric: tabular-nums;
    }
    td.best .cell-main {
      color: var(--best-text);
    }
    td.best {
      background: var(--best);
    }
    .col-rank {
      width: 1%;
      color: var(--muted);
      font-variant-numeric: tabular-nums;
    }
    .status-excluded {
      color: var(--muted);
      font-size: 0.85rem;
    }
"""


def _page(title: str, hero: str, body: str, legend: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <style>{_STYLE}  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      {hero}
    </section>
    {body}
    <p class="legend">{legend}</p>
  </div>
</body>
</html>
"""


# --- the per-target leaderboards (index.html) -------------------------------------------


def _best_by_dataset(table: dict[str, Any]) -> dict[str, float]:
    """The best value in each dataset column: highest headroom, or lowest MAE without it."""
    best: dict[str, float] = {}
    for dataset in table["datasets"]:
        values = []
        for row in table["rows"]:
            cell = row["cells"].get(dataset)
            if cell is None:
                continue
            value = cell["headroom"] if table["headroom"] else -cell["mae"]
            if value is not None:
                values.append(value)
        if values:
            best[dataset] = max(values)
    return best


def _table_cell(
    table: dict[str, Any], row: dict[str, Any], dataset: str, best: float | None
) -> str:
    cell = row["cells"].get(dataset)
    if cell is None:
        return '<td class="metric muted">-</td>'
    mae = format_metric_value("mae", float(cell["mae"]), target=table["target"])
    headroom = cell.get("headroom")
    value = headroom if table["headroom"] else -cell["mae"]
    css = "metric best" if best is not None and value is not None and value == best else "metric"
    title = escape(
        "; ".join(
            [", ".join(str(b) for b in cell.get("bundles", []))]
            + ([f"no headroom: {cell['headroom_missing']}"] if cell.get("headroom_missing") else [])
        )
    )
    if headroom is None:
        return (
            f'<td class="{css}" title="{title}"><span class="cell-main">{escape(mae)}</span></td>'
        )
    return (
        f'<td class="{css}" title="{title}"><span class="cell-main">{format_headroom(headroom)}</span>'
        f'<span class="cell-sub">MAE {escape(mae)}</span></td>'
    )


def _render_table(table: dict[str, Any]) -> str:
    datasets = table["datasets"]
    best = _best_by_dataset(table)
    head = "".join(f"<th>{escape(d)}</th>" for d in datasets)
    average_head = "<th>Average</th>" if table["headroom"] else ""
    body: list[str] = []
    rank = 0
    for row in table["rows"]:
        model = short_registry_id(str(row["model"]), prefix="model.")
        if row["average"] is not None:
            rank += 1
            rank_cell = str(rank)
            average = (
                f'<td class="metric"><span class="cell-main">{format_headroom(row["average"])}'
                "</span></td>"
            )
        else:
            rank_cell = ""
            done = f"{row['datasets_run']}/{len(table['roster'])} datasets"
            average = f'<td class="metric muted">{escape(done)}</td>' if table["headroom"] else ""
        cells = "".join(_table_cell(table, row, d, best.get(d)) for d in datasets)
        body.append(
            f'<tr><td class="col-rank">{rank_cell}</td>'
            f'<td><span class="model" title="{escape(str(row["model"]))}">{escape(model)}</span></td>'
            f"{average}{cells}</tr>"
        )
    span = 2 + (1 if table["headroom"] else 0) + len(datasets)
    rows_html = (
        "\n".join(body) or f'<tr><td colspan="{span}" class="empty">No benchmark cells.</td></tr>'
    )
    note = f'<p class="section-note">{escape(table["note"])}</p>' if table.get("note") else ""
    return f"""<section class="card">
      <h2>{escape(table["title"])}</h2>
      {note}
      <div class="table-wrap">
      <table>
        <thead><tr><th class="col-rank">#</th><th>Model</th>{average_head}{head}</tr></thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
      </div>
    </section>"""


def render_leaderboard_html(leaderboard: dict[str, Any]) -> str:
    """One leaderboard per target: a row per model, an average, a column per dataset (#237)."""
    tables = leaderboard.get("tables", [])
    generated_at = format_created_at(leaderboard.get("generated_at"))
    runs_dir = escape(str(leaderboard.get("runs_dir", "")))
    n_excluded = len(leaderboard.get("excluded", []))
    hero = (
        "<h1>hpc-oda leaderboard</h1>"
        f'<div class="meta">Generated {escape(generated_at)} · source <code>{runs_dir}</code> · '
        f'<a href="runs.html">every run</a> ({n_excluded} not counted, with reasons)</div>'
    )
    body = "\n".join(_render_table(table) for table in tables if table["rows"])
    if not body:
        body = '<section class="card"><p class="empty">No benchmark cells found.</p></section>'
    legend = (
        "Each cell is <b>headroom captured</b>: (baseline MAE − model MAE) / (baseline MAE − "
        "floor MAE), where the baseline is the window mean on that dataset and the floor its "
        "error ceiling. 0% is the baseline and 100% the floor; the MAE is shown beneath. "
        "The average is over every dataset in the table, for models that ran on all of them. "
        "Green marks the best in each dataset column. Only runs of each target's benchmark "
        "protocol count; the rest are listed on the runs page."
    )
    return _page("hpc-oda leaderboard", hero, body, legend)


# --- every bundle (runs.html) -----------------------------------------------------------


def _metric_cell(row: dict[str, Any], name: str) -> str:
    """Render one metric cell, or a muted dash when this row lacks the metric.

    Emitting a cell per column in order keeps values aligned under their headers
    even when different runs report different metric subsets.
    """
    metric = row["metrics"].get(name)
    if metric is None:
        return '<td class="metric muted">-</td>'
    title = (
        f"{metric_column_label(name, target=row.get('prediction_target'))}: {metric.get('raw', '')}"
    )
    return (
        f'<td class="metric" title="{escape(title)}">{escape(str(metric.get("display", "")))}</td>'
    )


def render_runs_html(leaderboard: dict[str, Any]) -> str:
    """Every bundle, one row each, and whether it counts on a leaderboard and why not."""
    entries = leaderboard.get("entries", [])
    rows, metric_names, _bests = prepare_leaderboard_rows(entries)
    reasons = {
        str(e.get("bundle_dir")): str(e.get("reason")) for e in leaderboard.get("excluded", [])
    }
    generated_at = format_created_at(leaderboard.get("generated_at"))
    runs_dir = escape(str(leaderboard.get("runs_dir", "")))

    metric_headers = "".join(
        f"<th>{escape(metric_column_label(name, target=None))}</th>" for name in metric_names
    )
    body_rows: list[str] = []
    for row in rows:
        metric_cells = "".join(_metric_cell(row, name) for name in metric_names)
        reason = reasons.get(row["bundle_dir"])
        status = (
            f'<td class="status-excluded">not counted: {escape(reason)}</td>'
            if reason
            else "<td>counted</td>"
        )
        body_rows.append(
            "<tr>"
            f'<td class="col-run" title="{escape(row["created_at_full"])}">{escape(row["created_at"])}</td>'
            f'<td><span class="recipe" title="{escape(row["recipe_id"])}">{escape(row["recipe_short"])}</span></td>'
            f'<td><span class="model" title="{escape(row["model_id"])}">{escape(row["model_short"])}</span>'
            f'<span class="muted"> v{escape(row["model_version"])}</span></td>'
            f"<td>{escape(row['target_label'])}</td>"
            f'<td title="{escape(row["dataset_label"])}">{escape(row["dataset_label"])}</td>'
            f"{metric_cells}"
            f'<td class="col-train nowrap">{escape(row["training_time"])}</td>'
            f"{status}"
            "</tr>"
        )
    empty = f'<tr><td colspan="{7 + len(metric_names)}" class="empty">No benchmark runs found.</td></tr>'
    rows_html = "\n".join(body_rows) if rows else empty
    hero = (
        "<h1>hpc-oda runs</h1>"
        f'<div class="meta">Generated {escape(generated_at)} · {len(rows)} run(s) · source '
        f'<code>{runs_dir}</code> · <a href="index.html">leaderboards</a></div>'
    )
    body = f"""<section class="card">
      <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th class="col-run">Run</th>
            <th>Recipe</th>
            <th>Model</th>
            <th>Target</th>
            <th>Dataset</th>
            {metric_headers}
            <th class="col-train">Train time</th>
            <th>Leaderboard</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
      </div>
    </section>"""
    legend = (
        "Every result bundle, one row each, for checking runs. These rows are not a ranking: "
        "errors in different datasets and protocols are not comparable. Metrics are shown in "
        "human-friendly units. Full provenance remains in each run bundle under <code>runs/</code>."
    )
    return _page("hpc-oda runs", hero, body, legend)


def write_leaderboard_pages(leaderboard: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    """Write ``index.html`` (the per-target leaderboards) and ``runs.html`` (every bundle)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    index = out_dir / "index.html"
    runs = out_dir / "runs.html"
    index.write_text(render_leaderboard_html(leaderboard), encoding="utf-8")
    runs.write_text(render_runs_html(leaderboard), encoding="utf-8")
    return index, runs


def render_analysis_html(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    metrics = report.get("metrics", {})
    model = report.get("model", {})
    dataset = report.get("dataset", {})

    def _cell(value: str) -> str:
        return f"<td>{escape(str(value))}</td>"

    metric_rows = "\n".join("<tr>" + _cell(k) + _cell(v) + "</tr>" for k, v in metrics.items())

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>hpc-oda analysis report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background: #f5f5f5; }}
    h1 {{ margin-bottom: 0.5rem; }}
  </style>
</head>
<body>
  <h1>hpc-oda analysis report</h1>
  <p><strong>Created:</strong> {escape(str(summary.get("created_at", "")))}</p>
  <p><strong>Report ID:</strong> {escape(str(summary.get("report_id", "")))}</p>

  <h2>Model</h2>
  <p><strong>ID:</strong> {escape(str(model.get("id", "")))}</p>
  <p><strong>Version:</strong> {escape(str(model.get("version", "")))}</p>

  <h2>Dataset</h2>
  <p><strong>ID:</strong> {escape(str(dataset.get("id", "")))}</p>
  <p><strong>Schema:</strong> {escape(str(dataset.get("schema_version", "")))}</p>
  <p><strong>Hash:</strong> {escape(str(dataset.get("hash", "")))}</p>

  <h2>Metrics</h2>
  <table>
    <thead>
      <tr><th>Metric</th><th>Value</th></tr>
    </thead>
    <tbody>
      {metric_rows}
    </tbody>
  </table>
</body>
</html>
"""
