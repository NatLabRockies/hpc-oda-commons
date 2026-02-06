from __future__ import annotations

from hpc_oda_commons.tools.report.html import render_analysis_html


def test_render_analysis_html_smoke() -> None:
    report = {
        "summary": {"report_id": "analysis-123", "created_at": "2026-01-01T00:00:00Z"},
        "model": {"id": "model.job_runtime_baseline", "version": "0.1.0"},
        "dataset": {"id": "dataset", "schema_version": "oda.job.v0.1.0", "hash": "abc123"},
        "metrics": {"mae": 1.0, "rmse": 2.0},
    }
    html = render_analysis_html(report)
    assert "hpc-oda analysis report" in html
