"""
Shared formatting helpers for leaderboard HTML and CLI views.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

METRIC_LABELS: dict[str, str] = {
    "mae": "MAE",
    "rmse": "RMSE",
    "underprediction_ratio": "Under-predicted",
    "mape": "MAPE",
    "r2": "R²",
}

# Units of the targets MAE/RMSE are reported in, beyond runtime (formatted as a duration).
POWER_TARGET_UNITS: dict[str, str] = {
    "avgpcon_per_node": "W/node",
    "maxpcon_per_node": "W/node",
    "avgpcon": "W",
    "maxpcon": "W",
}


@functools.cache
def model_titles() -> dict[str, str]:
    """Each registered model's title for readers: its registry ``name`` (#247).

    The ids stay as they are in recipes and bundles; the job_runtime_ prefix predates power
    and is not a reader's concern. The registry is the one place a model's name is kept.
    """
    from hpc_oda_commons.registry.snapshot import load_registry_index

    return {
        entry.id: entry.name
        for entry in load_registry_index().entries
        if entry.entry_type == "model"
    }


def card_name(model_id: str) -> str:
    """A model card's file name under ``docs/models/``: the id without ``model.`` (#247)."""
    return f"{model_id.removeprefix('model.')}.md"


def model_title(model_id: str) -> str:
    """A model's title for readers; an unregistered model shows its short id."""
    return model_titles().get(str(model_id), short_registry_id(str(model_id), prefix="model."))


# What a reader sees for each dataset on the leaderboard (#247): the system's name, as its
# dataset card records it. The power track's F-DATA window shares Fugaku's.
DATASET_TITLES: dict[str, str] = {
    "alcf_djc_aurora": "Aurora",
    "alcf_djc_polaris": "Polaris",
    "alcf_djc_theta": "Theta",
    "atlas_mustang": "Mustang",
    "atlas_opentrinity": "Trinity",
    "ccin2p3_2024": "CC-IN2P3",
    "fdata_fugaku": "Fugaku",
    "fdata_fugaku_uopc": "Fugaku",
    "fresco_anvil": "Anvil",
    "fresco_conte": "Conte",
    "fresco_stampede1": "Stampede",
    "lassen": "Lassen",
    "mit_supercloud": "SuperCloud",
    "nlr_eagle": "Eagle",
    "nlr_kestrel": "Kestrel",
    "pm100": "Marconi100",
    "pwa_cea_curie": "Curie",
    "pwa_hpc2n": "Seth",
    "pwa_kit_fh2": "ForHLR II",
    "pwa_metacentrum": "MetaCentrum",
    "pwa_ricc": "RICC",
    "pwa_sdsc_blue": "Blue Horizon",
}


def dataset_title(dataset: str) -> str:
    """A dataset's title for readers; an unlisted dataset shows its id."""
    return DATASET_TITLES.get(str(dataset), str(dataset))


# The published pages link into the repo on GitHub (#247).
REPO_BLOB_URL = "https://github.com/NatLabRockies/hpc-oda-commons/blob/main/"
# A dataset's page is its card. Power's F-DATA window has no card of its own; the power
# methodology's roster describes it. Power's other datasets are the same systems as runtime
# cards, over other dates.
DATASET_DOCS: dict[str, str] = {
    "fdata_fugaku_uopc": "docs/benchmarking/power/methodology.md#dataset-roster",
}


def dataset_doc(dataset: str) -> str | None:
    """The repo path of a dataset's page, or None for a dataset that has no title."""
    dataset = str(dataset)
    if dataset not in DATASET_TITLES:
        return None
    return DATASET_DOCS.get(dataset, f"docs/benchmarking/datasets/{dataset}.md")


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


def format_headroom(value: float) -> str:
    """Headroom captured as a whole percentage; a share that rounds to zero is 0%, not -0%."""
    percent = round(100.0 * float(value))
    return f"{percent + 0:d}%"


def format_target_label(target: str | None) -> str:
    if not target:
        return "-"
    labels = {
        "runtime_seconds": "job runtime",
        "avgpcon_per_node": "average power per node",
        "maxpcon_per_node": "peak power per node",
        "avgpcon": "average job power",
        "maxpcon": "peak job power",
    }
    return labels.get(target, target.replace("_", " "))


def format_metric_value(name: str, value: float, *, target: str | None) -> str:
    if name == "underprediction_ratio":
        return f"{value:.1f}%"
    if name == "r2":
        return f"{value:.3f}"
    if name in {"mae", "rmse"} and target == "runtime_seconds":
        return format_duration(value)
    if name in {"mae", "rmse"} and target in POWER_TARGET_UNITS:
        return f"{value:,.1f} {POWER_TARGET_UNITS[target]}"
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
    seconds = timing.get("total_train_eval_seconds")
    if seconds is None:
        return "-"
    return format_duration(float(seconds))


def prepare_leaderboard_rows(
    entries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], dict[str | None, dict[str, float]]]:
    """Display rows, metric names, and the best value of each metric **per target**.

    Bests are per prediction target because errors in different targets are not
    comparable: an MAE in seconds is not "better" than one in watts (#204).
    """
    metric_names = collect_metric_names(entries)
    bests: dict[str | None, dict[str, float]] = {}
    for target in {entry.get("prediction_target") for entry in entries}:
        same = [entry for entry in entries if entry.get("prediction_target") == target]
        bests[target] = best_metric_values(same, metric_names)
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
                "is_best": is_best_metric(name, value, bests.get(target, {})),
            }

        model = entry.get("model", {})
        dataset = entry.get("dataset", {})
        rows.append(
            {
                "created_at": format_created_at_compact(entry.get("created_at")),
                "created_at_full": format_created_at(entry.get("created_at")),
                "recipe_id": str(entry.get("recipe_id", "")),
                "recipe_short": short_registry_id(
                    str(entry.get("recipe_id", "")), prefix="recipe."
                ),
                "model_id": str(model.get("id", "")),
                "model_short": short_registry_id(str(model.get("id", "")), prefix="model."),
                "model_title": model_title(str(model.get("id", ""))),
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
