from __future__ import annotations

import json
from pathlib import Path

from hpc_oda_commons.benchmark.results import build_leaderboard, write_leaderboard
from hpc_oda_commons.kernel.artifacts.result_bundle import write_result_bundle
from hpc_oda_commons.tools.report import render_leaderboard_html
from tests.conftest import load_json


def _make_bundle(bundle_dir: Path) -> None:
    result = {
        "schema_version": "oda.result.v0.1.0",
        "recipe_id": "recipe.job_runtime.baseline_tiny",
        "problem_domain": ["job-runtime-prediction"],
        "created_at": "2026-02-05T00:00:00Z",
        "metrics": {"mae": 1.0, "rmse": 2.0},
        "provenance": {
            "schema_versions": {"input": "oda.job.v0.1.0", "result": "oda.result.v0.1.0"},
            "environment": {"python": "3.12.0", "packages": []},
            "code": {"package_version": "0.1.0", "git_commit": None},
        },
        "model": {"id": "model.job_runtime_baseline", "version": "0.1.0"},
        "dataset": {
            "id": "synthetic_job_runtime_tiny",
            "schema_version": "oda.job.v0.1.0",
            "hash": "abc12345",
        },
    }
    write_result_bundle(
        bundle_dir, result=result, metrics=result["metrics"], provenance=result["provenance"]
    )


def _make_invalid_bundle(bundle_dir: Path) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "result.json").write_text("{}", encoding="utf-8")
    (bundle_dir / "metrics.json").write_text("{}", encoding="utf-8")
    (bundle_dir / "provenance.json").write_text("{}", encoding="utf-8")


def test_build_leaderboard(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "runs" / "run-1"
    _make_bundle(bundle_dir)

    leaderboard = build_leaderboard(tmp_path / "runs")
    assert leaderboard["entries"], "expected leaderboard entries"
    entry = leaderboard["entries"][0]
    assert entry["model"]["id"] == "model.job_runtime_baseline"
    assert entry["dataset"]["hash"] == "abc12345"


def test_write_leaderboard_and_html(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "runs" / "run-2"
    _make_bundle(bundle_dir)

    leaderboard = build_leaderboard(tmp_path / "runs")
    out_dir = tmp_path / "leaderboard"
    json_path = write_leaderboard(leaderboard, out_dir)

    assert json_path.exists()
    html = render_leaderboard_html(leaderboard)
    assert "hpc-oda leaderboard" in html


def test_build_leaderboard_skips_invalid_bundle(tmp_path: Path) -> None:
    good_bundle = tmp_path / "runs" / "run-good"
    bad_bundle = tmp_path / "runs" / "run-bad"
    _make_bundle(good_bundle)
    _make_invalid_bundle(bad_bundle)

    leaderboard = build_leaderboard(tmp_path / "runs")
    assert len(leaderboard["entries"]) == 1
    assert leaderboard["entries"][0]["bundle_dir"] == str(good_bundle)


def test_build_leaderboard_orders_by_created_at(tmp_path: Path) -> None:
    older = tmp_path / "runs" / "run-older"
    newer = tmp_path / "runs" / "run-newer"

    _make_bundle(older)
    _make_bundle(newer)

    # Overwrite created_at to force ordering
    result_path = older / "result.json"
    result = load_json(result_path)
    result["created_at"] = "2026-01-01T00:00:00Z"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result_path = newer / "result.json"
    result = load_json(result_path)
    result["created_at"] = "2026-02-01T00:00:00Z"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    leaderboard = build_leaderboard(tmp_path / "runs")
    assert [e["bundle_dir"] for e in leaderboard["entries"]] == [str(older), str(newer)]
