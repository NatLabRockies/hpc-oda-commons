"""
Lightweight HTML report builder for local results.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from hpc_oda_commons.benchmark.leaderboard_display import (
    REPO_BLOB_URL,
    card_name,
    dataset_doc,
    dataset_title,
    format_created_at,
    format_headroom,
    format_metric_value,
    metric_column_label,
    model_title,
    model_titles,
    prepare_leaderboard_rows,
)

_STYLE = """
    :root {
      --bg: #eef1f5;
      --card: #ffffff;
      --text: #0f172a;
      --muted: #475569;
      --faint: #94a3b8;
      --border: #cbd5e1;
      --rule: #e2e8f0;
      --head-bg: #1e293b;
      --head-text: #f8fafc;
      --stripe: #f8fafc;
      --hover: #eef2ff;
      --accent: #1d4ed8;
      --avg-bg: #eef2ff;
      --best: #bbf7d0;
      --best-text: #14532d;
      --neg: #b91c1c;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.4;
    }
    a { color: var(--accent); }
    .page {
      max-width: 1440px;
      margin: 0 auto;
      padding: 1.5rem 1rem 3rem;
    }
    .hero {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.25rem 1.5rem;
      margin-bottom: 1.25rem;
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem 1.5rem;
      align-items: center;
      justify-content: space-between;
    }
    h1 {
      margin: 0 0 0.3rem;
      font-size: 1.6rem;
      letter-spacing: -0.02em;
    }
    .meta {
      color: var(--muted);
      font-size: 0.92rem;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
      /* Size to the table inside, not the page (#247); a wide one still scrolls. */
      width: fit-content;
      max-width: 100%;
    }
    .card + .card { margin-top: 1.5rem; }
    h2 {
      margin: 0;
      padding: 1rem 1.25rem 0.2rem;
      font-size: 1.2rem;
    }
    .section-note {
      margin: 0;
      color: var(--muted);
      font-size: 0.9rem;
      padding: 0 1.25rem 0.85rem;
    }
    .table-wrap { overflow-x: auto; }
    table {
      width: auto;
      border-collapse: collapse;
      font-size: 0.92rem;
    }
    thead th {
      background: var(--head-bg);
      color: var(--head-text);
      text-align: right;
      font-size: 0.76rem;
      font-weight: 600;
      letter-spacing: 0.02em;
      padding: 0.7rem 0.8rem;
      white-space: nowrap;
      border-left: 1px solid #334155;
    }
    thead th:first-child { border-left: none; }
    thead th.col-text, thead th.col-rank { text-align: left; }
    tbody td {
      padding: 0.6rem 0.8rem;
      border-top: 1px solid var(--rule);
      border-left: 1px solid var(--rule);
      vertical-align: middle;
    }
    tbody td:first-child { border-left: none; }
    tbody tr:nth-child(even) td { background: var(--stripe); }
    tbody tr:hover td { background: var(--hover); }
    .recipe, .model {
      font-weight: 650;
      color: var(--text);
      white-space: nowrap;
    }
    a.model { text-decoration: none; border-bottom: 1px solid var(--faint); }
    a.model:hover, a.model:focus { color: var(--accent); border-bottom-color: var(--accent); }
    .muted { color: var(--muted); }
    .metric {
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
      text-align: right;
      font-weight: 600;
    }
    .metric.muted { color: var(--faint); font-weight: 400; }
    tbody td.best, tbody tr:nth-child(even) td.best, tbody tr:hover td.best {
      background: var(--best);
      color: var(--best-text);
      font-weight: 750;
    }
    td.col-avg, tbody tr:nth-child(even) td.col-avg {
      background: var(--avg-bg);
      font-weight: 750;
    }
    thead th.col-avg { background: #312e81; }
    .neg { color: var(--neg); }
    td.best .neg { color: var(--best-text); }
    .fallback { color: var(--muted); font-style: italic; font-weight: 500; }
    .nowrap { white-space: nowrap; }
    .col-rank {
      width: 2.5rem;
      min-width: 2.5rem;
      color: var(--muted);
      font-variant-numeric: tabular-nums;
      text-align: left;
    }
    .col-sticky {
      position: sticky;
      left: 0;
      z-index: 1;
      background: var(--card);
    }
    .col-sticky + .col-sticky {
      left: 2.5rem;
      border-right: 2px solid #94a3b8;
    }
    tbody td.col-sticky { background: #e8edf4; }
    tbody tr:nth-child(even) td.col-sticky { background: #dde4ee; }
    thead th.col-sticky { background: var(--head-bg); z-index: 2; }
    tbody tr:hover td.col-sticky { background: #d4dcf5; }
    .col-run {
      width: 1%;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
      color: var(--muted);
      font-size: 0.86rem;
    }
    .col-train {
      width: 1%;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
      font-weight: 600;
      position: sticky;
      right: 0;
      background: var(--card);
      box-shadow: -8px 0 8px -6px rgba(15, 23, 42, 0.12);
    }
    thead .col-train { background: var(--head-bg); z-index: 2; }
    tbody tr:hover .col-train { background: var(--hover); }
    .empty {
      text-align: center;
      color: var(--muted);
      padding: 2rem;
    }
    .legend {
      margin-top: 1.25rem;
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.55;
    }
    .pill {
      display: inline-block;
      background: #dbeafe;
      color: #1e3a8a;
      border-radius: 999px;
      padding: 0.15rem 0.55rem;
      font-size: 0.8rem;
      font-weight: 600;
      margin-left: 0.35rem;
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
    .status-excluded {
      color: var(--muted);
      font-size: 0.85rem;
    }
    /* Headroom % or MAE, one at a time (#247). Without the script, % shows. */
    body[data-show="mae"] .v-pct, body:not([data-show="mae"]) .v-mae,
    body[data-show="mae"] .col-avg { display: none; }
    .toggle {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.9rem;
      color: var(--muted);
    }
    .toggle .choices {
      display: inline-flex;
      border: 1px solid var(--head-bg);
      border-radius: 8px;
      overflow: hidden;
    }
    .toggle button {
      font: inherit;
      font-weight: 600;
      border: none;
      padding: 0.4rem 0.9rem;
      background: var(--card);
      color: var(--text);
      cursor: pointer;
    }
    .toggle button + button { border-left: 1px solid var(--head-bg); }
    .toggle button[aria-pressed="true"] { background: var(--head-bg); color: var(--head-text); }
    .toggle button:focus-visible { outline: 3px solid #93c5fd; outline-offset: -3px; }
    .head-link { color: #bfdbfe; text-decoration: none; }
    .head-link:hover, .head-link:focus { color: #ffffff; text-decoration: underline; }
    /* A caveat on a column: a mark on its header, the text on hover or focus (#247). */
    .note {
      position: relative;
      cursor: help;
      margin-left: 0.15rem;
      color: #fde68a;
      font-weight: 700;
    }
    .note:focus { outline: 2px solid #fde68a; outline-offset: 2px; border-radius: 2px; }
    .note:hover::after, .note:focus::after {
      content: attr(data-note);
      position: absolute;
      top: 1.6em;
      right: -0.5rem;
      width: 20rem;
      white-space: normal;
      text-align: left;
      background: #0f172a;
      color: #f8fafc;
      border: 1px solid #fde68a;
      padding: 0.55rem 0.7rem;
      border-radius: 6px;
      font: 400 0.82rem/1.45 Inter, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      letter-spacing: 0;
      z-index: 10;
    }
"""


def _page(title: str, hero: str, body: str, legend: str, script: str = "") -> str:
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
  </div>{f"<script>{script}</script>" if script else ""}
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


def _model_label(model_id: str) -> str:
    """A model's title, linked to its generated card in the repo when it is registered."""
    title = escape(model_title(model_id))
    if model_id not in model_titles():
        return f'<span class="model" title="{escape(model_id)}">{title}</span>'
    href = escape(f"{REPO_BLOB_URL}docs/models/{card_name(model_id)}")
    return f'<a class="model" href="{href}" title="{escape(model_id)}">{title}</a>'


def _dataset_label(dataset: str) -> str:
    """A column header: the dataset's title, linked to its page in the repo."""
    title = escape(dataset_title(dataset))
    doc = dataset_doc(dataset)
    if doc is None:
        return f'<span title="{escape(dataset)}">{title}</span>'
    return f'<a class="head-link" href="{escape(REPO_BLOB_URL + doc)}" title="{escape(dataset)}">{title}</a>'


def _note_mark(text: str) -> str:
    """A caveat on a column header: a mark, with the text on hover or keyboard focus."""
    if not text:
        return ""
    note = escape(text)
    return f'<sup class="note" tabindex="0" data-note="{note}" aria-label="Note: {note}">*</sup>'


def _table_cell(
    table: dict[str, Any], row: dict[str, Any], dataset: str, best: float | None
) -> str:
    """One cell: its headroom and its MAE, of which the page shows one at a time (#247)."""
    cell = row["cells"].get(dataset)
    if cell is None:
        return '<td class="metric muted">-</td>'
    mae = escape(format_metric_value("mae", float(cell["mae"]), target=table["target"]))
    headroom = cell.get("headroom")
    value = headroom if table["headroom"] else -cell["mae"]
    css = "metric best" if best is not None and value is not None and value == best else "metric"
    tip = [", ".join(str(b) for b in cell.get("bundles", []))]
    if cell.get("headroom_missing"):
        tip.append(f"no headroom: {cell['headroom_missing']}")
    if headroom is None:
        # No headroom to show, so the % view shows the MAE, marked as such.
        pct = f'<span class="v-pct fallback">{mae}</span>'
    else:
        neg = " neg" if headroom < 0 else ""
        pct = f'<span class="v-pct{neg}">{format_headroom(headroom)}</span>'
    return (
        f'<td class="{css}" title="{escape("; ".join(tip))}">'
        f'{pct}<span class="v-mae">{mae}</span></td>'
    )


def _render_table(table: dict[str, Any]) -> str:
    datasets = table["datasets"]
    best = _best_by_dataset(table)
    notes = table.get("dataset_notes") or {}
    head = "".join(f"<th>{_dataset_label(d)}{_note_mark(notes.get(d, ''))}</th>" for d in datasets)
    average_head = (
        f'<th class="col-avg">Average{_note_mark(table.get("average_note", ""))}</th>'
        if table["headroom"]
        else ""
    )
    body: list[str] = []
    rank = 0
    for row in table["rows"]:
        if row["average"] is not None:
            rank += 1
            rank_cell = str(rank)
            neg = " neg" if row["average"] < 0 else ""
            average = f'<td class="metric col-avg{neg}">{format_headroom(row["average"])}</td>'
        else:
            rank_cell = ""
            done = f"{row['datasets_run']}/{len(table['roster'])} datasets"
            average = (
                f'<td class="metric muted col-avg">{escape(done)}</td>' if table["headroom"] else ""
            )
        cells = "".join(_table_cell(table, row, d, best.get(d)) for d in datasets)
        body.append(
            f'<tr><td class="col-rank col-sticky">{rank_cell}</td>'
            f'<td class="col-sticky">{_model_label(str(row["model"]))}</td>{average}{cells}</tr>'
        )
    span = 2 + (1 if table["headroom"] else 0) + len(datasets)
    rows_html = (
        "\n".join(body) or f'<tr><td colspan="{span}" class="empty">No benchmark cells.</td></tr>'
    )
    caption = table.get("caption")
    caption_html = f'<p class="section-note">{escape(caption)}</p>' if caption else ""
    return f"""<section class="card">
      <h2>{escape(table["title"])}</h2>
      {caption_html}
      <div class="table-wrap">
      <table>
        <thead><tr><th class="col-rank col-sticky">#</th><th class="col-text col-sticky">Model</th>{average_head}{head}</tr></thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
      </div>
    </section>"""


_TOGGLE = (
    '<div class="toggle" role="group" aria-label="Show in each cell">Show'
    '<span class="choices">'
    '<button type="button" data-show="pct" aria-pressed="true">Headroom %</button>'
    '<button type="button" data-show="mae" aria-pressed="false">MAE</button>'
    "</span></div>"
)

# Switches every cell between headroom and MAE, and remembers the choice in this browser
# only. Storage can be unavailable (private windows, blocked site data), so every use of it
# is guarded and the page works without it.
_TOGGLE_SCRIPT = """
(function () {
  var KEY = "hpc-oda-leaderboard-show";
  var buttons = document.querySelectorAll(".toggle button");
  function show(view) {
    document.body.setAttribute("data-show", view);
    buttons.forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-show") === view));
    });
    try { localStorage.setItem(KEY, view); } catch (e) {}
  }
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) {}
  show(saved === "mae" ? "mae" : "pct");
  buttons.forEach(function (b) {
    b.addEventListener("click", function () { show(b.getAttribute("data-show")); });
  });
})();
"""


def render_leaderboard_html(leaderboard: dict[str, Any]) -> str:
    """One leaderboard per target: a row per model, an average, a column per dataset (#237)."""
    tables = leaderboard.get("tables", [])
    generated_at = format_created_at(leaderboard.get("generated_at"))
    runs_dir = escape(str(leaderboard.get("runs_dir", "")))
    n_excluded = len(leaderboard.get("excluded", []))
    hero = (
        "<div><h1>hpc-oda leaderboard</h1>"
        f'<div class="meta">Generated {escape(generated_at)} · source <code>{runs_dir}</code> · '
        f'<a href="runs.html">every run</a> ({n_excluded} not counted, with reasons)</div></div>'
        f"{_TOGGLE}"
    )
    body = "\n".join(_render_table(table) for table in tables if table["rows"])
    if not body:
        body = '<section class="card"><p class="empty">No benchmark cells found.</p></section>'
    legend = (
        "<b>Headroom %</b> is (baseline MAE − model MAE) / (baseline MAE − floor MAE), where "
        "the baseline is the window mean on that dataset and the floor its error ceiling: 0% is "
        "the baseline, 100% the floor, and red is worse than the baseline. <b>MAE</b> shows the "
        "error itself; it can't be averaged across datasets, so the Average column shows only "
        "with headroom. Models are ranked by average headroom, over every dataset in the table, "
        "for models that ran on all of them. Green marks the best in each dataset column. A * "
        "on a column header marks a caveat: hover over it, or tab to it. Only runs of each "
        "target's benchmark protocol count; the rest are listed on the runs page."
    )
    return _page("hpc-oda leaderboard", hero, body, legend, script=_TOGGLE_SCRIPT)


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
            f"<td>{_model_label(row['model_id'])}"
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
            <th class="col-run col-text">Run</th>
            <th class="col-text">Recipe</th>
            <th class="col-text">Model</th>
            <th class="col-text">Target</th>
            <th class="col-text">Dataset</th>
            {metric_headers}
            <th class="col-train">Train time</th>
            <th class="col-text">Leaderboard</th>
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
      <tr><th class="col-text">Metric</th><th>Value</th></tr>
    </thead>
    <tbody>
      {metric_rows}
    </tbody>
  </table>
</body>
</html>
"""
