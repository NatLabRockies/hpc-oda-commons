"""
Shared formatting helpers for leaderboard HTML and CLI views.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

METRIC_LABELS: dict[str, str] = {
    "mae": "MAE",
    "rmse": "RMSE",
    "underprediction_ratio": "Under-predicted",
    "mape": "MAPE",
    "r2": "R²",
}

LOWER_IS_BETTER = frozenset({"mae", "rmse", "mape", "underprediction_ratio"})
HIGHER_IS_BETTER = frozenset({"r2"})


def infer_prediction_target(metrics_payload: dict[str, Any]) -> str | None:
    definitions = metrics_payload.get("definitions")
    if not isinstance(definitions, list):
        return None
    targets = {str(defn.get("target", "")).strip() for defn in definitions if defn.get("target")}
    if not targets:
        return None
    if len(targets) == 1:
        return next(iter(targets))
    return ", ".join(sorted(targets))


def short_registry_id(value: str, *, prefix: str = "") -> str:
    text = str(value or "")
    if prefix and text.startswith(prefix):
        text = text[len(prefix) :]
    if "." in text:
        return text.rsplit(".", 1)[-1]
    return text


def short_dataset_label(dataset_id: str, *, table_path: str | None = None) -> str:
    return resolve_dataset_folder_name(dataset_id, table_path=table_path)


def resolve_dataset_folder_name(
    dataset_id: str,
    *,
    table_path: str | None = None,
) -> str:
    """Return the ingest folder name (parent of data.parquet) for display/records."""
    candidates: list[Path] = []
    if table_path:
        candidates.append(Path(table_path))
    if dataset_id:
        candidates.append(Path(dataset_id))

    for path in candidates:
        if path.name in {"data.parquet", "data"} or path.suffix == ".parquet":
            parent_name = path.parent.name
            if parent_name:
                return parent_name
        name = path.name
        if name:
            return name

    return dataset_id or "-"


def format_created_at(value: str | None) -> str:
    if not value:
        return "-"
    text = str(value).replace("Z", "+00:00")
    if "T" in text:
        date_part, time_part = text.split("T", 1)
        time_part = time_part.split(".")[0].split("+")[0]
        return f"{date_part} {time_part} UTC"
    return text


def format_created_at_compact(value: str | None) -> str:
    """Compact run timestamp for leaderboard tables (full value kept in title)."""
    if not value:
        return "-"
    text = str(value).replace("Z", "+00:00")
    if "T" not in text:
        return text
    date_part, time_part = text.split("T", 1)
    time_part = time_part.split(".")[0].split("+")[0]
    month_day = date_part[5:] if len(date_part) >= 10 else date_part
    hour_min = time_part[:5] if len(time_part) >= 5 else time_part
    return f"{month_day} {hour_min}"


def format_duration(seconds: float) -> str:
    value = abs(float(seconds))
    if value < 60:
        return f"{value:.0f}s"
    if value < 3600:
        return f"{value / 60:.1f} min"
    hours = value / 3600
    if hours < 48:
        return f"{hours:.1f} h"
    return f"{hours / 24:.1f} d"


def format_target_label(target: str | None) -> str:
    if not target:
        return "-"
    labels = {
        "runtime_seconds": "job runtime",
    }
    return labels.get(target, target.replace("_", " "))


def format_metric_value(name: str, value: float, *, target: str | None) -> str:
    if name == "underprediction_ratio":
        return f"{value:.1f}%"
    if name == "r2":
        return f"{value:.3f}"
    if name in {"mae", "rmse"} and target == "runtime_seconds":
        return format_duration(value)
    if name == "mape":
        return f"{value:.1%}"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, float):
        return f"{value:.3g}"
    return str(value)


def metric_column_label(name: str, *, target: str | None) -> str:
    base = METRIC_LABELS.get(name, name.upper())
    if name in {"mae", "rmse"} and target == "runtime_seconds":
        return f"{base} (avg error)" if name == "mae" else f"{base} (spread)"
    if name == "underprediction_ratio":
        return "Under-predicted"
    return base


def collect_metric_names(entries: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        for name in entry.get("metrics", {}):
            if name not in seen:
                seen.add(name)
                names.append(name)
    preferred = ["mae", "rmse", "underprediction_ratio", "mape", "r2"]
    ordered = [name for name in preferred if name in seen]
    ordered.extend(name for name in names if name not in ordered)
    return ordered


def best_metric_values(entries: list[dict[str, Any]], metric_names: list[str]) -> dict[str, float]:
    bests: dict[str, float] = {}
    for name in metric_names:
        values = [
            float(entry["metrics"][name])
            for entry in entries
            if isinstance(entry.get("metrics"), dict) and name in entry["metrics"]
        ]
        if not values:
            continue
        if name in LOWER_IS_BETTER:
            bests[name] = min(values)
        elif name in HIGHER_IS_BETTER:
            bests[name] = max(values)
    return bests


def is_best_metric(name: str, value: float, bests: dict[str, float]) -> bool:
    if name not in bests:
        return False
    best = bests[name]
    if name in LOWER_IS_BETTER:
        return abs(value - best) < 1e-9
    if name in HIGHER_IS_BETTER:
        return abs(value - best) < 1e-9
    return False


def format_training_time(timing: dict[str, Any] | None) -> str:
    if not timing:
        return "-"
    seconds = timing.get("total_training_seconds")
    if seconds is None:
        return "-"
    return format_duration(float(seconds))


def prepare_leaderboard_rows(
    entries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], dict[str, float]]:
    metric_names = collect_metric_names(entries)
    bests = best_metric_values(entries, metric_names)
    rows: list[dict[str, Any]] = []

    for entry in entries:
        metrics = entry.get("metrics", {})
        target = entry.get("prediction_target")
        row_metrics: dict[str, dict[str, Any]] = {}
        for name in metric_names:
            if name not in metrics:
                continue
            value = float(metrics[name])
            row_metrics[name] = {
                "raw": value,
                "display": format_metric_value(name, value, target=target),
                "is_best": is_best_metric(name, value, bests),
            }

        model = entry.get("model", {})
        dataset = entry.get("dataset", {})
        rows.append(
            {
                "created_at": format_created_at_compact(entry.get("created_at")),
                "created_at_full": format_created_at(entry.get("created_at")),
                "recipe_id": str(entry.get("recipe_id", "")),
                "recipe_short": short_registry_id(str(entry.get("recipe_id", "")), prefix="recipe."),
                "model_id": str(model.get("id", "")),
                "model_short": short_registry_id(str(model.get("id", "")), prefix="model."),
                "model_version": str(model.get("version", "")),
                "dataset_label": short_dataset_label(
                    str(dataset.get("id", "")),
                    table_path=str(dataset.get("table_path", "")) or None,
                ),
                "prediction_target": target,
                "target_label": format_target_label(target),
                "metrics": row_metrics,
                "training_time": format_training_time(entry.get("timing")),
                "bundle_dir": str(entry.get("bundle_dir", "")),
            }
        )
    return rows, metric_names, bests
