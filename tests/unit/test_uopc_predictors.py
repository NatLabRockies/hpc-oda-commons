"""UoPC predictors (#241): the neighbours' median (ours), their mean, and the authors' vote."""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

import hpc_oda_commons
from hpc_oda_commons.benchmark.recipes import load_recipe, validate_recipe
from hpc_oda_commons.benchmark.runner import resolved_run_config
from hpc_oda_commons.kernel.validate import SchemaValidationError
from hpc_oda_commons.models.job_power_uopc.model import (
    UOPC_DEFAULT_PREDICTOR,
    UOPC_PREDICTORS,
    JobPowerUopcModel,
    check_uopc_predictor,
    uopc_predict,
)
from hpc_oda_commons.models.job_power_uopc.rolling import (
    JobPowerUopcRollingConfig,
    JobPowerUopcRollingModel,
)

TARGET = "avgpcon_per_node"
METRICS = [{"name": "mae", "target": TARGET}, {"name": "rmse", "target": TARGET}]
BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
RECIPES = Path(hpc_oda_commons.__file__).parent / "recipes" / "job-power"
PAPER_COMPARISON = {
    "uopc_paper_reproduction_paper_setup.yml",
    "uopc_paper_reproduction_unpadded.yml",
}


def test_each_predictor_on_neighbours_that_all_differ() -> None:
    """Three neighbours, three different values: the vote is a three-way tie, which the
    authors' classifier breaks to the lowest value. The far row is never a neighbour."""
    context = np.asarray([[0.0], [0.1], [0.2], [9.0]])
    power = np.asarray([10.2, 30.1, 20.4, 500.0])
    query = np.asarray([[0.05]])

    predicted = {
        p: uopc_predict(context, (power,), query, k=3, predictor=p)[0][0] for p in UOPC_PREDICTORS
    }

    assert predicted["vote"] == 10.0  # rounded, and the lowest of the tie
    assert predicted["mean"] == pytest.approx((10.2 + 30.1 + 20.4) / 3)
    assert predicted["median"] == pytest.approx(20.4)


def test_every_target_shares_one_neighbour_set() -> None:
    context = np.asarray([[0.0], [1.0], [2.0], [9.0]])
    avg, peak = np.asarray([1.0, 2.0, 4.0, 99.0]), np.asarray([10.0, 20.0, 40.0, 990.0])
    for predictor in ("mean", "median"):
        got_avg, got_peak = uopc_predict(
            context, (avg, peak), np.asarray([[0.0]]), k=3, predictor=predictor
        )
        assert got_peak[0] == pytest.approx(10 * got_avg[0])


def test_the_default_is_the_median() -> None:
    """Chosen on the F-DATA reproduction protocol only, as k was (#241)."""
    assert UOPC_DEFAULT_PREDICTOR == "median"
    assert JobPowerUopcRollingConfig().predictor == UOPC_DEFAULT_PREDICTOR
    signature = inspect.signature(JobPowerUopcModel.evaluate_paper_reproduction)
    assert signature.parameters["predictor"].default == UOPC_DEFAULT_PREDICTOR


def test_an_unknown_predictor_is_an_error() -> None:
    with pytest.raises(ValueError, match="predictor must be one of"):
        check_uopc_predictor("mode")
    with pytest.raises(ValueError, match="predictor must be one of"):
        JobPowerUopcRollingModel(JobPowerUopcRollingConfig(predictor="mode"))


def _job(i: int, hour: float, power: float) -> dict:
    submit = BASE + timedelta(hours=hour)
    return {
        "job_id": i,
        "user": "alice",
        "submit_time": submit,
        "end_time": submit + timedelta(minutes=30),
        "num_cores_req": 48.0,
        "num_nodes_req": 1.0,
        "freq_req": 2200.0,
        "embedding": [1.0, 0.0],
        TARGET: power,
    }


def _rows() -> list[dict]:
    """Five identical jobs that drew different power, then one more to predict."""
    rows = [_job(i, i, power) for i, power in enumerate((100.0, 110.0, 120.0, 300.0, 310.0))]
    return [*rows, _job(5, 20.0, 150.0)]


@pytest.mark.parametrize(
    ("predictor", "expected"), [("vote", 100.0), ("mean", 188.0), ("median", 120.0)]
)
def test_the_rolling_protocol_uses_the_predictor(predictor: str, expected: float) -> None:
    model = JobPowerUopcRollingModel(
        JobPowerUopcRollingConfig(
            n_windows=1,
            test_window_hours=1,
            training_lookback_days=2,
            theta=10,
            k=5,
            predictor=predictor,
        )
    )

    result = model.evaluate(_rows(), metric_defs=METRICS, capture_artifacts=True)

    assert result["_y_pred"] == [pytest.approx(expected)]
    assert result["summary"]["predictor"] == predictor
    assert resolved_run_config(model)["predictor"] == predictor


def _recipe(model: str, split: dict) -> dict:
    return {
        "recipe_id": "recipe.job_power.uopc_predictor_test",
        "problem_domain": ["job-power-prediction"],
        "schema_version": "oda.job.v0.2.0",
        "dataset": {"id": "fdata_fugaku_uopc", "table_path": "data.parquet"},
        "model": {"id": model, "version": "0.1.0"},
        "metrics": METRICS,
        "split": split,
    }


@pytest.mark.parametrize(
    "split",
    [
        {"method": "cutoff", "test_start": "2024-02-01", "predictor": "vote"},
        {"method": "rolling", "n_windows": 3, "predictor": "median"},
    ],
)
def test_recipe_accepts_a_predictor_for_uopc(split: dict) -> None:
    validate_recipe(_recipe("model.job_power_uopc", split))


def test_recipe_rejects_a_predictor_elsewhere() -> None:
    split = {"method": "rolling", "n_windows": 3, "predictor": "mean"}
    with pytest.raises(SchemaValidationError, match="predictor only applies"):
        validate_recipe(_recipe("model.job_runtime_xgboost", split))


def test_recipe_rejects_an_unknown_predictor() -> None:
    split = {"method": "rolling", "n_windows": 3, "predictor": "mode"}
    with pytest.raises(SchemaValidationError):
        validate_recipe(_recipe("model.job_power_uopc", split))


def test_only_the_paper_comparison_recipes_vote() -> None:
    """Every bundled UoPC recipe says its predictor, so the leaderboard can tell a bundle
    that voted from one that did not (#241)."""
    predictors = {r.name: load_recipe(r)["split"]["predictor"] for r in RECIPES.glob("uopc_*.yml")}

    assert {n: p for n, p in predictors.items() if n in PAPER_COMPARISON} == dict.fromkeys(
        PAPER_COMPARISON, "vote"
    )
    ours = set(predictors) - PAPER_COMPARISON
    assert ours and all(predictors[n] == UOPC_DEFAULT_PREDICTOR for n in ours)
