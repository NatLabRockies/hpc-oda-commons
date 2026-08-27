"""Walk-forward ranking over real result bundles (#190)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hpc_oda_commons.benchmark.results import build_arm_ranking, write_arm_ranking
from hpc_oda_commons.kernel.artifacts.result_bundle import write_result_bundle

DATASET = "arm_ranking_demo"
# Arm keys name their axis since #197, so a bundle says what it ran without its filename.
LB10 = "training_lookback_days=10"
LB120 = "training_lookback_days=120"
MODEL = "model.job_runtime_xgboost"


def _windows(maes: list[float]) -> list[dict]:
    return [
        {
            "split_time": f"2026-03-{i + 1:02d}T00:00:00+00:00",
            "status": "ok",
            "test_rows_supervised": 100,
            "metrics": {"mae": mae, "rmse": mae * 2.0},
        }
        for i, mae in enumerate(maes)
    ]


def _write_arm(
    bundle_dir: Path,
    *,
    lookback: int,
    maes: list[float],
    dataset: str = DATASET,
    model: str = MODEL,
    created_at: str = "2026-03-10T00:00:00Z",
) -> None:
    pooled = sum(maes) / len(maes)
    metrics = {
        "mae": pooled,
        "rmse": pooled * 2.0,
        "definitions": [
            {"name": "mae", "target": "runtime_seconds"},
            {"name": "rmse", "target": "runtime_seconds"},
        ],
        "windows": _windows(maes),
        "summary": {"training_lookback_days": lookback, "n_windows": len(maes)},
    }
    provenance = {
        "schema_versions": {"input": "oda.job.v0.1.0", "result": "oda.result.v0.1.0"},
        "environment": {"python": "3.12.0", "packages": []},
        "code": {"package_version": "0.1.0", "git_commit": None},
    }
    result = {
        "schema_version": "oda.result.v0.1.0",
        "recipe_id": f"recipe.job_runtime.{dataset}_xgb_lb{lookback}d",
        "problem_domain": ["job-runtime-prediction"],
        "created_at": created_at,
        "metrics": {"mae": pooled, "rmse": pooled * 2.0},
        "provenance": provenance,
        "model": {"id": model, "version": "0.1.0"},
        "dataset": {"id": dataset, "schema_version": "oda.job.v0.1.0", "hash": "abc12345"},
    }
    write_result_bundle(bundle_dir, result=result, metrics=metrics, provenance=provenance)


# The short arm leads early and loses late; the long arm is the reverse. Any rule that
# selected on the test set would report the long arm's 1.0 and never show the crossover.
_SHORT = [1.0, 1.0, 9.0, 9.0, 9.0, 9.0]
_LONG = [6.0, 6.0, 1.0, 1.0, 1.0, 1.0]


def _three_arm_cell(runs: Path) -> None:
    _write_arm(runs / DATASET / "xgboost" / "benchmark-1", lookback=10, maes=_SHORT)
    _write_arm(runs / DATASET / "xgboost" / "benchmark-2", lookback=120, maes=_LONG)


def test_ranking_reports_the_policy_and_the_hindsight_arm(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _three_arm_cell(runs)

    ranking = build_arm_ranking(runs, burn_in=2)

    assert len(ranking["cells"]) == 1
    cell = ranking["cells"][0]
    assert cell["dataset"] == DATASET
    assert cell["choices"] == [LB10, LB10, LB120, LB120]
    assert cell["score"] == pytest.approx(5.0)
    assert cell["oracle_key"] == LB120
    assert cell["oracle_score"] == pytest.approx(1.0)


def test_a_cell_with_one_arm_is_named_not_dropped(tmp_path: Path) -> None:
    """A silently missing row reads as 'nothing to report' when it means 'not comparable'."""
    runs = tmp_path / "runs"
    _write_arm(runs / "solo" / "xgboost" / "benchmark-1", lookback=120, maes=_LONG, dataset="solo")

    ranking = build_arm_ranking(runs, burn_in=2)

    assert ranking["cells"] == []
    assert len(ranking["unranked"]) == 1
    assert "at least two" in ranking["unranked"][0]["reason"]


def test_arms_on_different_splits_are_reported_as_unranked(tmp_path: Path) -> None:
    """A staging mistake should surface as a named failure, not a plausible number."""
    runs = tmp_path / "runs"
    _write_arm(runs / DATASET / "xgboost" / "benchmark-1", lookback=10, maes=_SHORT)
    bundle = runs / DATASET / "xgboost" / "benchmark-2"
    _write_arm(bundle, lookback=120, maes=_LONG)
    metrics_path = bundle / "metrics.json"
    metrics_path.write_text(
        metrics_path.read_text(encoding="utf-8").replace("2026-03-01", "2026-04-01"),
        encoding="utf-8",
    )

    ranking = build_arm_ranking(runs, burn_in=2)

    assert ranking["cells"] == []
    assert "do not share a split" in ranking["unranked"][0]["reason"]


def test_a_rerun_arm_supersedes_its_predecessor(tmp_path: Path) -> None:
    """Same rule as the leaderboard (#166): the newest bundle for a cell is the one that counts."""
    runs = tmp_path / "runs"
    _three_arm_cell(runs)
    # The 10d arm re-run, now flat and clearly worse than its first attempt.
    _write_arm(
        runs / DATASET / "xgboost" / "benchmark-3",
        lookback=10,
        maes=[20.0] * 6,
        created_at="2026-03-11T00:00:00Z",
    )

    ranking = build_arm_ranking(runs, burn_in=2)

    cell = ranking["cells"][0]
    # History now favours the long arm from the first scored window, so the lag disappears.
    assert cell["choices"] == [LB120] * 4
    assert cell["arm_scores"][LB10] == pytest.approx(20.0)


def test_write_arm_ranking_round_trips(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _three_arm_cell(runs)
    ranking = build_arm_ranking(runs, burn_in=2)

    out = write_arm_ranking(ranking, tmp_path / "leaderboard")

    assert out.name == "arm-ranking.json"
    assert '"oracle_key"' in out.read_text(encoding="utf-8")


def test_bundles_written_before_run_config_still_rank(tmp_path: Path) -> None:
    """A format change must not strand every result measured so far (#197)."""
    runs = tmp_path / "runs"
    _write_arm(runs / DATASET / "xgboost" / "benchmark-1", lookback=10, maes=_SHORT)
    _write_arm(runs / DATASET / "xgboost" / "benchmark-2", lookback=120, maes=_LONG)
    # These fixtures carry no run_config, exactly like the bundles already on disk.
    for path in runs.rglob("metrics.json"):
        assert "run_config" not in json.loads(path.read_text(encoding="utf-8"))

    ranking = build_arm_ranking(runs, burn_in=2)

    assert ranking["cells"][0]["oracle_key"] == LB120


def test_a_recorded_config_keys_an_axis_the_summary_never_carried(tmp_path: Path) -> None:
    """The reason for run_config: the summary records three fields and nothing else."""
    runs = tmp_path / "runs"
    for i, (threshold, maes) in enumerate([(0, _SHORT), (500, _LONG)], start=1):
        bundle = runs / DATASET / "xgboost" / f"benchmark-{i}"
        _write_arm(bundle, lookback=120, maes=maes)
        path = bundle / "metrics.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["run_config"] = {
            "training_lookback_days": 120,
            "target_encode_min_cardinality": threshold,
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    ranking = build_arm_ranking(runs, burn_in=2)

    cell = ranking["cells"][0]
    assert cell["oracle_key"] == "target_encode_min_cardinality=500"
    assert set(cell["choice_counts"]) == {
        "target_encode_min_cardinality=0",
        "target_encode_min_cardinality=500",
    }
