"""Per-target leaderboards: a row per model, headroom per dataset, an average (#237)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hpc_oda_commons.benchmark.results import build_leaderboard
from hpc_oda_commons.benchmark.tracks import RUNTIME_PROTOCOL, build_tables
from hpc_oda_commons.benchmarking.hpc.matrix import Card
from hpc_oda_commons.kernel.artifacts.result_bundle import write_result_bundle
from hpc_oda_commons.models.job_power_uopc.model import UOPC_DEFAULT_PREDICTOR
from hpc_oda_commons.tools.report import render_leaderboard_html, render_runs_html

POWER_SPLIT = {"n_windows": 89, "test_window_hours": 24, "training_lookback_days": 60}
# The jobs every fixture cell and ceiling covers, so headroom applies unless a test says not.
ROWS = 1000
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
        "summary": {**POWER_SPLIT, "rows_scored": ROWS} if summary is None else summary,
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


def _label(runs: Path, bundle: Path) -> str:
    """How the leaderboard names a bundle: relative to the runs directory (#245)."""
    return bundle.relative_to(runs).as_posix()


def _ceiling(
    ceilings: Path, dataset_id: str, target: str, floor: float, scored_rows: int = ROWS
) -> None:
    ceilings.mkdir(parents=True, exist_ok=True)
    stem = dataset_id.split(".")[-1]
    payload = {
        "dataset_id": dataset_id,
        "target_field": target,
        "scored_rows": scored_rows,
        "floor": {"mae": floor},
    }
    (ceilings / f"{stem}.{target}.ceiling.json").write_text(json.dumps(payload))


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
        # Written before the predictor setting existed, so it voted (#241).
        (
            {"run_config": {**POWER_SPLIT, "k": 20, "theta": 500}},
            "stale: ran with predictor=vote",
        ),
    ],
    ids=["paper-protocol", "smoke-run", "ad-hoc-recipe", "stale-config", "predates-predictor"],
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
    assert reason in reasons[_label(runs, bundle)]
    table = _table(leaderboard, "avgpcon_per_node")
    assert "model.job_power_uopc" not in {r["model"] for r in table["rows"]}


def test_a_bundle_on_the_recipes_predictor_counts(power_runs) -> None:
    runs, ceilings = power_runs
    config = {**POWER_SPLIT, "k": 20, "theta": 500, "predictor": UOPC_DEFAULT_PREDICTOR}
    _bundle(
        runs,
        recipe_id="recipe.job_power.uopc_rolling_avg_pm100",
        model="model.job_power_uopc",
        mae=130.0,
        run_config=config,
    )
    leaderboard = build_leaderboard(runs, ceilings_dir=ceilings, cards_dir=ceilings)

    table = _table(leaderboard, "avgpcon_per_node")
    assert "model.job_power_uopc" in {r["model"] for r in table["rows"]}


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
    assert cell["bundles"] == [_label(runs, newer)]
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


def _lassen_card(tmp_path: Path) -> Card:
    return Card(
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


def _runtime_pairs(
    model: str, arms: dict[int, list[float]], *, run_config: bool = True, n_windows: int = 0
) -> list[tuple[dict, dict]]:
    """One bundle per lookback arm of ``model`` on lassen, a window of 10 jobs per MAE.

    The summary states the runtime protocol's window count (or ``n_windows``); the window
    list is kept short, since the policy reads the windows and the protocol check the
    summary. ``run_config=False`` writes a bundle from before #197, like the fleet's."""
    pairs = []
    for lookback, maes in arms.items():
        entry = {
            "bundle_dir": f"{model}-{lookback}",
            "prediction_target": "runtime_seconds",
            "recipe_id": f"recipe.job_runtime.lassen_{model}_lb{lookback}d",
            "dataset": {"id": "lassen"},
            "model": {"id": model},
        }
        metrics = {
            "mae": sum(maes) / len(maes),
            "summary": {
                "n_windows": n_windows or RUNTIME_PROTOCOL["n_windows"],
                "test_window_hours": RUNTIME_PROTOCOL["test_window_hours"],
                "training_lookback_days": lookback,
            },
            "windows": _windows(maes),
        }
        if run_config:
            metrics["run_config"] = {"training_lookback_days": lookback}
        pairs.append((entry, metrics))
    return pairs


def test_runtime_cells_use_the_walk_forward_choice(tmp_path: Path) -> None:
    """Two lookback arms: the cell is the policy's score, not the better arm's (#190)."""
    arms = {10: [5.0, 5.0, 1.0, 9.0], 30: [6.0, 6.0, 6.0, 2.0]}  # a: good early, bad late
    pairs = _runtime_pairs("model.job_runtime_xgboost", arms)

    tables, excluded = build_tables(
        pairs, ceilings_dir=tmp_path, cards=[_lassen_card(tmp_path)], burn_in=2
    )
    runtime = next(t for t in tables if t["key"] == "runtime")
    cell = runtime["rows"][0]["cells"]["lassen"]
    # After two burn-in windows: window 2 picks arm a (5 < 6) and scores 1.0; window 3 still
    # picks a (11/3 < 6) and scores 9.0. The better arm in hindsight (b) would claim 4.0.
    assert cell["mae"] == pytest.approx(5.0)
    assert cell["scored_rows"] == 20  # the two windows past the burn-in
    assert not excluded


def _runtime_tables(tmp_path: Path, ceiling_rows: int) -> dict:
    _ceiling(tmp_path, "dataset.job_runtime.lassen", "runtime_seconds", 1.0, ceiling_rows)
    pairs = _runtime_pairs("model.job_runtime_baseline", {10: [9.0] * 4, 30: [9.5] * 4})
    pairs += _runtime_pairs("model.job_runtime_xgboost", {10: [5.0] * 4, 30: [6.0] * 4})
    tables, _ = build_tables(
        pairs, ceilings_dir=tmp_path, cards=[_lassen_card(tmp_path)], burn_in=2
    )
    return next(t for t in tables if t["key"] == "runtime")


def test_runtime_headroom_when_the_ceiling_covers_the_same_jobs(tmp_path: Path) -> None:
    """The floor, the baseline and the cell all cover the 20 jobs past the burn-in (#238)."""
    runtime = _runtime_tables(tmp_path, ceiling_rows=20)
    xgb = _row(runtime, "model.job_runtime_xgboost")

    # Baseline 9 (its walk-forward pick, the 10-day arm), floor 1, model 5: halfway.
    assert xgb["cells"]["lassen"]["headroom"] == pytest.approx(0.5)
    assert xgb["average"] == pytest.approx(0.5)
    assert "covers other jobs" not in runtime["note"]


def test_runtime_shows_mae_alone_when_the_ceiling_covers_other_jobs(tmp_path: Path) -> None:
    """A ceiling from other windows, like those from before the burn-in, bounds other rows."""
    runtime = _runtime_tables(tmp_path, ceiling_rows=40)
    cell = _row(runtime, "model.job_runtime_xgboost")["cells"]["lassen"]

    assert cell["headroom"] is None and cell["mae"] == pytest.approx(5.0)
    assert cell["headroom_missing"].startswith("covers other jobs: the ceiling 40")
    assert "covers other jobs" in runtime["note"]
    assert all(row["average"] is None for row in runtime["rows"])


def _runtime_table(tmp_path: Path, pairs: list) -> tuple[dict, list]:
    tables, excluded = build_tables(
        pairs, ceilings_dir=tmp_path, cards=[_lassen_card(tmp_path)], burn_in=2
    )
    return next(t for t in tables if t["key"] == "runtime"), excluded


@pytest.mark.parametrize(
    ("arms", "n_windows", "reason"),
    [
        ({10: [5.0] * 4, 30: [6.0] * 4}, 360, "n_windows=360, the benchmark runs 120"),
        ({50: [5.0] * 4}, 0, "lookback 50 d is not one of [10, 30, 120]"),
    ],
    ids=["cards-90-days", "other-lookback"],
)
def test_runtime_counts_the_fleets_protocol_only(
    tmp_path: Path, arms: dict, n_windows: int, reason: str
) -> None:
    """The runtime benchmark is the fleet that has run: 30 days in 6 h windows at 10, 30 and
    120 days of lookback. The cards' 90 days count once #191's fleet runs them."""
    pairs = _runtime_pairs("model.job_runtime_xgboost", arms, n_windows=n_windows)
    runtime, excluded = _runtime_table(tmp_path, pairs)

    assert not runtime["rows"]
    assert {e["reason"] for e in excluded} == {reason}


def test_bundles_from_before_run_config_are_told_apart_by_their_lookback(tmp_path: Path) -> None:
    """The fleet's bundles predate run_config (#197); their summary holds the lookback."""
    arms = {10: [5.0, 5.0, 1.0, 9.0], 30: [6.0, 6.0, 6.0, 2.0]}
    pairs = _runtime_pairs("model.job_runtime_xgboost", arms, run_config=False)
    runtime, excluded = _runtime_table(tmp_path, pairs)

    assert runtime["rows"][0]["cells"]["lassen"]["mae"] == pytest.approx(5.0)
    assert not excluded


def test_a_dataset_too_large_to_plan_has_no_runtime_column(tmp_path: Path) -> None:
    """ccin2p3_2024 keeps its card, but the planner never runs it, so it would leave every
    model's average incomplete (#150)."""
    from dataclasses import replace

    from hpc_oda_commons.benchmarking.hpc.matrix import MAX_NODE_ROWS

    big = replace(_lassen_card(tmp_path), dataset="ccin2p3_2024", window_rows=MAX_NODE_ROWS + 1)
    tables, _ = build_tables([], ceilings_dir=tmp_path, cards=[_lassen_card(tmp_path), big])
    runtime = next(t for t in tables if t["key"] == "runtime")
    assert runtime["roster"] == ["lassen"]


def test_a_power_cell_on_other_jobs_gets_no_headroom(power_runs) -> None:
    runs, ceilings = power_runs
    _ceiling(ceilings, "dataset.job_runtime.pm100", "avgpcon_per_node", 100.0, ROWS + 1)
    leaderboard = build_leaderboard(runs, ceilings_dir=ceilings, cards_dir=ceilings)

    cell = _row(_table(leaderboard, "avgpcon_per_node"), "model.job_runtime_xgboost")["cells"]
    assert cell["pm100"]["headroom"] is None
    assert cell["nlr_eagle"]["headroom"] is not None


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


def test_published_pages_hold_no_absolute_path(power_runs, tmp_path: Path) -> None:
    """The leaderboard is published (#245): no page may carry the machine's paths, even when
    the runs directory is given as an absolute one, as the CLI does."""
    from hpc_oda_commons.tools.report import write_leaderboard_pages

    runs, ceilings = power_runs
    assert runs.is_absolute()
    leaderboard = build_leaderboard(runs, ceilings_dir=ceilings, cards_dir=ceilings)
    out = tmp_path / "site"
    write_leaderboard_pages(leaderboard, out)
    (out / "leaderboard.json").write_text(json.dumps(leaderboard))

    for page in ("index.html", "runs.html", "leaderboard.json"):
        assert str(tmp_path) not in (out / page).read_text(), page
    assert leaderboard["runs_dir"] == "runs"
