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
        rows.append(
            {
                "created_at": entry.get("created_at", ""),
                "recipe_id": entry.get("recipe_id", ""),
                "model_id": model.get("id", ""),
                "model_version": model.get("version", ""),
                "dataset_id": dataset.get("id", ""),
                "dataset_hash": dataset.get("hash", ""),
                "metrics": ", ".join(f"{k}={v}" for k, v in metrics.items()),
            }
        )

    def _cell(value: str) -> str:
        return f"<td>{escape(str(value))}</td>"

    body_rows = "\n".join(
        "<tr>"
        + _cell(row["created_at"])
        + _cell(row["recipe_id"])
        + _cell(row["model_id"])
        + _cell(row["model_version"])
        + _cell(row["dataset_id"])
        + _cell(row["dataset_hash"])
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
