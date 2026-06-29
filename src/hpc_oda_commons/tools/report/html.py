"""
Lightweight HTML report builder for local results.
"""

from __future__ import annotations

from html import escape
from typing import Any

from hpc_oda_commons.benchmark.leaderboard_display import (
    format_created_at,
    metric_column_label,
    prepare_leaderboard_rows,
)


def render_leaderboard_html(leaderboard: dict[str, Any]) -> str:
    entries = leaderboard.get("entries", [])
    rows, metric_names, _bests = prepare_leaderboard_rows(entries)
    generated_at = format_created_at(leaderboard.get("generated_at"))
    runs_dir = escape(str(leaderboard.get("runs_dir", "")))

    metric_headers = "".join(
        f"<th>{escape(metric_column_label(name, target=None))}</th>" for name in metric_names
    )

    body_rows: list[str] = []
    for row in rows:
        metric_cells = "".join(
            f'<td class="{"metric best" if row["metrics"][name].get("is_best") else "metric"}" '
            f'title="{escape(metric_column_label(name, target=row.get("prediction_target")))}: '
            f'{escape(str(row["metrics"][name].get("raw", "")))}">'
            f'{escape(str(row["metrics"][name].get("display", "")))}</td>'
            for name in metric_names
            if name in row["metrics"]
        )
        missing_cells = "".join(
            '<td class="metric muted">-</td>' for name in metric_names if name not in row["metrics"]
        )
        body_rows.append(
            "<tr>"
            f'<td class="col-run" title="{escape(row["created_at_full"])}">{escape(row["created_at"])}</td>'
            f'<td><span class="recipe" title="{escape(row["recipe_id"])}">{escape(row["recipe_short"])}</span></td>'
            f'<td><span class="model" title="{escape(row["model_id"])}">{escape(row["model_short"])}</span>'
            f'<span class="muted"> v{escape(row["model_version"])}</span></td>'
            f'<td>{escape(row["target_label"])}</td>'
            f'<td title="{escape(row["dataset_label"])}">{escape(row["dataset_label"])}</td>'
            f"{metric_cells}{missing_cells}"
            f'<td class="col-train nowrap">{escape(row["training_time"])}</td>'
            "</tr>"
        )

    empty_state = (
        f'<tr><td colspan="{6 + len(metric_names)}" class="empty">No benchmark runs found.</td></tr>'
        if not rows
        else "\n".join(body_rows)
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>hpc-oda leaderboard</title>
  <style>
    :root {{
      --bg: #f7f8fb;
      --card: #ffffff;
      --text: #1f2937;
      --muted: #6b7280;
      --border: #e5e7eb;
      --accent: #2563eb;
      --best: #ecfdf5;
      --best-text: #047857;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
      background: linear-gradient(180deg, #eef2ff 0%, var(--bg) 180px);
      color: var(--text);
    }}
    .page {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 2rem 1.25rem 3rem;
    }}
    .hero {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 1.5rem 1.75rem;
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
      margin-bottom: 1.25rem;
    }}
    h1 {{
      margin: 0 0 0.35rem;
      font-size: 1.75rem;
      letter-spacing: -0.02em;
    }}
    .meta {{
      color: var(--muted);
      font-size: 0.95rem;
      line-height: 1.5;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
    }}
    .table-wrap {{
      overflow-x: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.95rem;
    }}
    thead th {{
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
    }}
    tbody td {{
      padding: 0.9rem 1rem;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }}
    tbody tr:hover {{
      background: #fafbff;
    }}
    tbody tr:last-child td {{
      border-bottom: none;
    }}
    .recipe, .model {{
      font-weight: 600;
      color: #111827;
    }}
    .muted {{
      color: var(--muted);
    }}
    .metric {{
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
      font-weight: 600;
    }}
    .metric.best {{
      background: var(--best);
      color: var(--best-text);
    }}
    .nowrap {{
      white-space: nowrap;
    }}
    .col-run {{
      width: 1%;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
      color: var(--muted);
      font-size: 0.88rem;
    }}
    .col-train {{
      width: 1%;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
      font-weight: 600;
      position: sticky;
      right: 0;
      background: var(--card);
      box-shadow: -8px 0 8px -6px rgba(15, 23, 42, 0.08);
    }}
    thead .col-train {{
      background: #f9fafb;
      z-index: 2;
    }}
    tbody tr:hover .col-train {{
      background: #fafbff;
    }}
    .empty {{
      text-align: center;
      color: var(--muted);
      padding: 2rem;
    }}
    .legend {{
      margin-top: 1rem;
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.5;
    }}
    .pill {{
      display: inline-block;
      background: #eff6ff;
      color: #1d4ed8;
      border-radius: 999px;
      padding: 0.15rem 0.55rem;
      font-size: 0.8rem;
      font-weight: 600;
      margin-left: 0.35rem;
    }}
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <h1>hpc-oda leaderboard</h1>
      <div class="meta">
        Generated {escape(generated_at)} · {len(rows)} run(s) · source <code>{runs_dir}</code>
      </div>
    </section>

    <section class="card">
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
          </tr>
        </thead>
        <tbody>
          {empty_state}
        </tbody>
      </table>
      </div>
    </section>

    <p class="legend">
      Metrics are shown in human-friendly units when the prediction target is job runtime.
      Green cells mark the best value in each metric column for this leaderboard.
      Full provenance remains in each run bundle under <code>runs/</code>.
    </p>
  </div>
</body>
</html>
"""


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
