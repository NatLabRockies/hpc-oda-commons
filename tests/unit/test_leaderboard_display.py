from __future__ import annotations

from hpc_oda_commons.benchmark.leaderboard_display import (
    format_created_at_compact,
    format_duration,
    format_metric_value,
    infer_prediction_target,
    prepare_leaderboard_rows,
    short_registry_id,
)
from hpc_oda_commons.tools.report.html import render_leaderboard_html


def test_infer_prediction_target_from_definitions() -> None:
    payload = {
        "definitions": [
            {"name": "mae", "target": "runtime_seconds"},
            {"name": "rmse", "target": "runtime_seconds"},
        ]
    }
    assert infer_prediction_target(payload) == "runtime_seconds"


def test_format_created_at_compact() -> None:
    assert format_created_at_compact("2026-06-10T14:08:59.387806Z") == "06-10 14:08"
    assert format_created_at_compact(None) == "-"


def test_resolve_dataset_folder_name_from_parquet_path() -> None:
    from hpc_oda_commons.benchmark.leaderboard_display import resolve_dataset_folder_name

    path = "/data/ingested/jobs_parquet/fugaku_24_04/data.parquet"
    assert resolve_dataset_folder_name(path) == "fugaku_24_04"
    assert resolve_dataset_folder_name("jobs-parquet-20260601") == "jobs-parquet-20260601"


def test_format_runtime_metrics_as_human_durations() -> None:
    assert format_metric_value("mae", 3661.0, target="runtime_seconds") == "1.0 h"
    assert format_metric_value("underprediction_ratio", 34.2, target="runtime_seconds") == "34.2%"


def test_prepare_leaderboard_rows_marks_best_metric() -> None:
    entries = [
        {
            "created_at": "2026-01-01T00:00:00Z",
            "recipe_id": "recipe.job_runtime.baseline_tiny",
            "model": {"id": "model.job_runtime_baseline", "version": "0.1.0"},
            "dataset": {"id": "synthetic_job_runtime_tiny"},
            "prediction_target": "runtime_seconds",
            "metrics": {"mae": 10.0, "rmse": 20.0},
        },
        {
            "created_at": "2026-02-01T00:00:00Z",
            "recipe_id": "recipe.job_runtime.xgb_hourly_recent",
            "model": {"id": "model.job_runtime_xgboost", "version": "0.1.0"},
            "dataset": {"id": "synthetic_job_runtime_tiny"},
            "prediction_target": "runtime_seconds",
            "metrics": {"mae": 5.0, "rmse": 12.0},
        },
    ]

    rows, metric_names, bests = prepare_leaderboard_rows(entries)
    assert metric_names == ["mae", "rmse"]
    assert bests["mae"] == 5.0
    assert rows[1]["metrics"]["mae"]["is_best"] is True
    assert (
        short_registry_id("recipe.job_runtime.baseline_tiny", prefix="recipe.") == "baseline_tiny"
    )


def test_render_leaderboard_html_uses_target_and_hides_hash_columns() -> None:
    leaderboard = {
        "generated_at": "2026-06-01T00:00:00Z",
        "runs_dir": "/tmp/runs",
        "entries": [
            {
                "created_at": "2026-06-01T00:00:00Z",
                "recipe_id": "recipe.job_runtime.baseline_tiny",
                "model": {"id": "model.job_runtime_baseline", "version": "0.1.0"},
                "dataset": {"id": "jobs-parquet-20260601"},
                "prediction_target": "runtime_seconds",
                "metrics": {"mae": 120.0, "rmse": 240.0},
            }
        ],
    }

    html = render_leaderboard_html(leaderboard)
    assert "Target" in html
    assert "job runtime" in html
    assert "Code Hash" not in html
    assert "Dataset Hash" not in html
    assert format_duration(120.0) in html


def test_render_leaderboard_html_aligns_columns_when_metric_missing() -> None:
    # Regression test for column misalignment: an entry missing an early metric
    # (mae) must render a dash under the MAE column and keep its rmse value under
    # the RMSE column, not shifted left.
    leaderboard = {
        "generated_at": "2026-06-01T00:00:00Z",
        "runs_dir": "/tmp/runs",
        "entries": [
            {
                "created_at": "2026-06-01T00:00:00Z",
                "recipe_id": "recipe.x.full",
                "model": {"id": "model.x.full", "version": "0.1.0"},
                "dataset": {"id": "ds"},
                "prediction_target": "maxpcon",
                "metrics": {"mae": 10.0, "rmse": 20.0},
            },
            {
                "created_at": "2026-06-02T00:00:00Z",
                "recipe_id": "recipe.x.partial",
                "model": {"id": "model.x.partial", "version": "0.1.0"},
                "dataset": {"id": "ds"},
                "prediction_target": "maxpcon",
                "metrics": {"rmse": 999.0},
            },
        ],
    }

    html = render_leaderboard_html(leaderboard)
    partial_row = next(seg for seg in html.split("<tr>") if "partial" in seg)
    dash_idx = partial_row.index('class="metric muted">-')
    value_idx = partial_row.index(">999<")
    # The MAE dash must come before the RMSE value (columns stay aligned).
    assert dash_idx < value_idx
