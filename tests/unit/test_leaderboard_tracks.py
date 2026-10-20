"""Per-target leaderboards: a row per model, headroom per dataset, an average (#237)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hpc_oda_commons.benchmark.results import build_leaderboard
from hpc_oda_commons.benchmark.tracks import build_tables
from hpc_oda_commons.benchmarking.hpc.matrix import Card
from hpc_oda_commons.kernel.artifacts.result_bundle import write_result_bundle
from hpc_oda_commons.tools.report import render_leaderboard_html, render_runs_html

POWER_SPLIT = {"n_windows": 89, "test_window_hours": 24, "training_lookback_days": 60}
_counter = iter(range(10_000))


def _bundle(
    runs: Path,
    *,
    recipe_id: str,
    model: str,
    target: str = "avgpcon_per_node",
    mae: float,
    dataset: str = "pm100",
    summary: dict | None = None,
    run_config: dict | None = None,
    windows: list | None = None,
    created_at: str | None = None,
) -> Path:
    n = next(_counter)
    bundle_dir = runs / f"benchmark-{n:04d}"
    metrics = {
        "mae": mae,
        "definitions": [{"name": "mae", "target": target}],
        "summary": dict(POWER_SPLIT) if summary is None else summary,
    }
    if run_config is not None:
        metrics["run_config"] = run_config
    if windows is not None:
        metrics["windows"] = windows
    result = {
        "schema_version": "oda.result.v0.1.0",
        "recipe_id": recipe_id,
        "problem_domain": ["job-power-prediction"],
        "created_at": created_at or f"2026-10-20T00:{n // 60:02d}:{n % 60:02d}Z",
        "metrics": {"mae": mae, "rmse": mae},
        "provenance": {
            "schema_versions": {"input": "oda.job.v0.2.0", "result": "oda.result.v0.1.0"},
            "environment": {"python": "3.12.0", "packages": []},
            "code": {"package_version": "0.1.0", "git_commit": None},
        },
        "model": {"id": model, "version": "0.1.0"},
        "dataset": {"id": dataset, "schema_version": "oda.job.v0.2.0", "hash": "abc12345"},
    }
    provenance = {
        "schema_versions": {"input": "oda.job.v0.2.0", "result": "oda.result.v0.1.0"},
        "environment": {"python": "3.12.0", "packages": []},
        "code": {"package_version": "0.1.0", "git_commit": None},
    }
    write_result_bundle(bundle_dir, result=result, metrics=metrics, provenance=provenance)
    return bundle_dir


def _ceiling(ceilings: Path, dataset_id: str, target: str, floor: float) -> None:
    ceilings.mkdir(parents=True, exist_ok=True)
    stem = dataset_id.split(".")[-1]
    (ceilings / f"{stem}.{target}.ceiling.json").write_text(
        json.dumps({"dataset_id": dataset_id, "target_field": target, "floor": {"mae": floor}})
    )


@pytest.fixture
def power_runs(tmp_path: Path) -> tuple[Path, Path]:
    """PM100 and Eagle average power: a baseline, XGBoost on both, MoE on PM100 only."""
    runs, ceilings = tmp_path / "runs", tmp_path / "ceilings"
    _ceiling(ceilings, "dataset.job_runtime.pm100", "avgpcon_per_node", 100.0)
    _ceiling(ceilings, "dataset.job_runtime.nlr_eagle", "avgpcon_per_node", 20.0)
    for system, base, xgb in (("pm100", 150.0, 125.0), ("eagle", 90.0, 62.0)):
        _bundle(
            runs,
            recipe_id=f"recipe.job_power.baseline_rolling_avg_{system}",
            model="model.job_runtime_baseline",
            mae=base,
            dataset=f"x_{system}",
        )
        _bundle(
            runs,
            recipe_id=f"recipe.job_power.xgboost_rolling_avg_{system}",
            model="model.job_runtime_xgboost",
            mae=xgb,
            dataset=f"x_{system}",
        )
    _bundle(
        runs,
        recipe_id="recipe.job_power.moe_xgboost_rolling_avg_pm100",
        model="model.job_runtime_moe_xgboost",
        mae=140.0,
    )
    return runs, ceilings


def _table(leaderboard: dict, key: str) -> dict:
    return next(t for t in leaderboard["tables"] if t["key"] == key)


def _row(table: dict, model: str) -> dict:
    return next(r for r in table["rows"] if r["model"] == model)


def test_headroom_is_measured_from_the_baseline_to_the_floor(power_runs) -> None:
    runs, ceilings = power_runs
    table = _table(
        build_leaderboard(runs, ceilings_dir=ceilings, cards_dir=ceilings), "avgpcon_per_node"
    )

    xgb = _row(table, "model.job_runtime_xgboost")
    assert xgb["cells"]["pm100"]["headroom"] == pytest.approx((150 - 125) / (150 - 100))
    assert xgb["cells"]["nlr_eagle"]["headroom"] == pytest.approx((90 - 62) / (90 - 20))
    assert xgb["average"] == pytest.approx((0.5 + 0.4) / 2)
    assert _row(table, "model.job_runtime_baseline")["average"] == 0.0


def test_a_model_missing_a_dataset_has_no_average(power_runs) -> None:
    runs, ceilings = power_runs
    table = _table(
        build_leaderboard(runs, ceilings_dir=ceilings, cards_dir=ceilings), "avgpcon_per_node"
    )

    moe = _row(table, "model.job_runtime_moe_xgboost")
    assert moe["average"] is None
    assert moe["datasets_run"] == 1
    # Ranked rows come first, best average first; incomplete rows after.
    assert [r["model"] for r in table["rows"]] == [
        "model.job_runtime_xgboost",
        "model.job_runtime_baseline",
        "model.job_runtime_moe_xgboost",
    ]


def test_bundles_take_their_dataset_from_the_recipe(power_runs) -> None:
    """A bundle records its table's folder name; the recipe says which dataset that is."""
    runs, ceilings = power_runs
    table = _table(
        build_leaderboard(runs, ceilings_dir=ceilings, cards_dir=ceilings), "avgpcon_per_node"
    )
    assert table["datasets"] == ["nlr_eagle", "pm100"]


def test_the_roster_comes_from_the_ceiling_files(power_runs) -> None:
    """A dataset with a ceiling but no runs is a column, and blanks every average."""
    runs, ceilings = power_runs
    _ceiling(ceilings, "dataset.job_runtime.nlr_kestrel", "avgpcon_per_node", 25.0)
    table = _table(
        build_leaderboard(runs, ceilings_dir=ceilings, cards_dir=ceilings), "avgpcon_per_node"
    )
    assert "nlr_kestrel" in table["datasets"]
    assert all(row["average"] is None for row in table["rows"])


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"summary": {}, "run_config": {"protocol": "paper_reproduction"}}, "is a study"),
        ({"summary": {**POWER_SPLIT, "n_windows": 3}}, "n_windows=3"),
        ({"recipe_id": "recipe.job_power.uopc_rolling_avg_pm100__balanced"}, "not a bundled"),
        ({"run_config": {**POWER_SPLIT, "k": 5, "theta": 500}}, "stale: ran with k=5"),
    ],
    ids=["paper-protocol", "smoke-run", "ad-hoc-recipe", "stale-config"],
)
def test_only_the_benchmark_protocol_counts(power_runs, kwargs: dict, reason: str) -> None:
    runs, ceilings = power_runs
    args = {
        "recipe_id": "recipe.job_power.uopc_rolling_avg_pm100",
        "model": "model.job_power_uopc",
        "mae": 1.0,
    }
    bundle = _bundle(runs, **{**args, **kwargs})
    leaderboard = build_leaderboard(runs, ceilings_dir=ceilings, cards_dir=ceilings)

    reasons = {e["bundle_dir"]: e["reason"] for e in leaderboard["excluded"]}
    assert reason in reasons[str(bundle)]
    table = _table(leaderboard, "avgpcon_per_node")
    assert "model.job_power_uopc" not in {r["model"] for r in table["rows"]}


def test_a_rerun_replaces_its_cell_and_is_named(power_runs) -> None:
    runs, ceilings = power_runs
    newer = _bundle(
        runs,
        recipe_id="recipe.job_power.xgboost_rolling_avg_pm100",
        model="model.job_runtime_xgboost",
        mae=110.0,
        created_at="2026-10-21T00:00:00Z",
    )
    leaderboard = build_leaderboard(runs, ceilings_dir=ceilings, cards_dir=ceilings)

    cell = _row(_table(leaderboard, "avgpcon_per_node"), "model.job_runtime_xgboost")["cells"][
        "pm100"
    ]
    assert cell["mae"] == 110.0
    assert cell["bundles"] == [str(newer)]
    assert any(e["reason"].startswith("superseded by") for e in leaderboard["excluded"])


def test_each_target_has_its_own_table(power_runs) -> None:
    runs, ceilings = power_runs
    _ceiling(ceilings, "dataset.job_runtime.pm100", "maxpcon_per_node", 120.0)
    _bundle(
        runs,
        recipe_id="recipe.job_power.xgboost_rolling_peak_pm100",
        model="model.job_runtime_xgboost",
        target="maxpcon_per_node",
        mae=180.0,
    )
    leaderboard = build_leaderboard(runs, ceilings_dir=ceilings, cards_dir=ceilings)

    peak = _table(leaderboard, "maxpcon_per_node")
    assert [r["model"] for r in peak["rows"]] == ["model.job_runtime_xgboost"]
    assert peak["datasets"] == ["pm100"]
    avg_models = [r["model"] for r in _table(leaderboard, "avgpcon_per_node")["rows"]]
    assert len(avg_models) == len(set(avg_models))  # one row per model


def _windows(maes: list[float]) -> list[dict]:
    return [
        {"status": "ok", "split_time": f"t{i}", "test_rows_supervised": 10, "metrics": {"mae": v}}
        for i, v in enumerate(maes)
    ]


def test_runtime_cells_use_the_walk_forward_choice_and_show_no_headroom(tmp_path: Path) -> None:
    """Two lookback arms: the cell is the policy's score, not the better arm's (#190)."""
    card = Card(
        dataset="lassen",
        window_rows=1000,
        window_start="2026-01-01",
        window_end="2026-03-31",
        train_days=60,
        healthy=True,
        system="Lassen",
        source_table="x",
        card_path=tmp_path / "lassen.card.json",
        history_days=120,
        test_days=1,
    )
    summary = {"n_windows": 4, "test_window_hours": 6}
    arm_a = [5.0, 5.0, 1.0, 9.0]  # good early, bad late
    arm_b = [6.0, 6.0, 6.0, 2.0]
    pairs = []
    for lookback, maes in ((10, arm_a), (30, arm_b)):
        entry = {
            "bundle_dir": f"b{lookback}",
            "prediction_target": "runtime_seconds",
            "recipe_id": f"recipe.job_runtime.lassen_xgb_lb{lookback}d",
            "dataset": {"id": "lassen"},
            "model": {"id": "model.job_runtime_xgboost"},
        }
        metrics = {
            "mae": sum(maes) / 4,
            "summary": {**summary, "training_lookback_days": lookback},
            "run_config": {"training_lookback_days": lookback},
            "windows": _windows(maes),
        }
        pairs.append((entry, metrics))

    tables, excluded = build_tables(pairs, ceilings_dir=tmp_path, cards=[card], burn_in=2)
    runtime = next(t for t in tables if t["key"] == "runtime")
    cell = runtime["rows"][0]["cells"]["lassen"]
    # After two burn-in windows: window 2 picks arm a (5 < 6) and scores 1.0; window 3 still
    # picks a (11/3 < 6) and scores 9.0. The better arm in hindsight (b) would claim 4.0.
    assert cell["mae"] == pytest.approx(5.0)
    assert cell["headroom"] is None and runtime["rows"][0]["average"] is None
    assert not excluded


def test_pages_render_tables_and_list_what_was_left_out(power_runs) -> None:
    runs, ceilings = power_runs
    smoke = _bundle(
        runs,
        recipe_id="recipe.job_power.xgboost_rolling_avg_pm100",
        model="model.job_runtime_xgboost",
        mae=1.0,
        summary={**POWER_SPLIT, "n_windows": 3},
    )
    leaderboard = build_leaderboard(runs, ceilings_dir=ceilings, cards_dir=ceilings)

    index = render_leaderboard_html(leaderboard)
    assert "Average power per node" in index and "Average" in index
    assert "50%" in index  # XGBoost's PM100 headroom
    assert 'href="runs.html"' in index
    runs_html = render_runs_html(leaderboard)
    assert "not counted: n_windows=3" in runs_html
    assert str(smoke) not in index
