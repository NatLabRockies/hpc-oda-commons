"""
Lightweight HTML report builder for local results.
"""

from __future__ import annotations

from html import escape
from typing import Any


def render_leaderboard_html(leaderboard: dict[str, Any]) -> str:
    entries = leaderboard.get("entries", [])
    rows = []
    for entry in entries:
        model = entry.get("model", {})
        dataset = entry.get("dataset", {})
        metrics = entry.get("metrics", {})
        integrity = entry.get("integrity") or {}
        code_hash = integrity.get("code_hash", "")
        validated = integrity.get("validated")
        rows.append(
            {
                "created_at": entry.get("created_at", ""),
                "recipe_id": entry.get("recipe_id", ""),
                "model_id": model.get("id", ""),
                "model_version": model.get("version", ""),
                "dataset_id": dataset.get("id", ""),
                "dataset_hash": dataset.get("hash", ""),
                "validated": "yes" if validated else ("no" if validated is False else ""),
                "code_hash": code_hash or "",
                "metrics": ", ".join(f"{k}={v}" for k, v in metrics.items()),
            }
        )

    def _cell(value: str) -> str:
        return f"<td>{escape(str(value))}</td>"

    def _hash_cell(value: str) -> str:
        if value and len(value) >= 12:
            return f'<td title="{escape(value)}">{escape(value[:12])}&hellip;</td>'
        return f"<td>{escape(str(value))}</td>"

    body_rows = "\n".join(
        "<tr>"
        + _cell(row["created_at"])
        + _cell(row["recipe_id"])
        + _cell(row["model_id"])
        + _cell(row["model_version"])
        + _cell(row["dataset_id"])
        + _hash_cell(row["dataset_hash"])
        + _cell(row["validated"])
        + _hash_cell(row["code_hash"])
        + _cell(row["metrics"])
        + "</tr>"
        for row in rows
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>hpc-oda leaderboard</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background: #f5f5f5; }}
    caption {{ text-align: left; font-weight: bold; margin-bottom: 0.5rem; }}
  </style>
</head>
<body>
  <table>
    <caption>hpc-oda leaderboard</caption>
    <thead>
      <tr>
        <th>Created</th>
        <th>Recipe</th>
        <th>Model</th>
        <th>Model Version</th>
        <th>Dataset</th>
        <th>Dataset Hash</th>
        <th>Validated</th>
        <th>Code Hash</th>
        <th>Metrics</th>
      </tr>
    </thead>
    <tbody>
      {body_rows}
    </tbody>
  </table>
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
