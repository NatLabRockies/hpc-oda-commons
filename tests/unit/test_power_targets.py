"""Every runtime model predicts whatever column the recipe's metrics name (#204).

The table carries both runtime (900-1300 s) and per-node power (100-200 W) in ranges that
cannot be confused, so a model that silently kept predicting runtime would be caught by its
own y_true.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from hpc_oda_commons.benchmark import runner
from hpc_oda_commons.models.feature_policy import feature_allowlist
from hpc_oda_commons.models.job_runtime_xgboost.model import (
    JobRuntimeXGBoostConfig,
    JobRuntimeXGBoostModel,
)

TARGET = "avgpcon_per_node"
SPLIT = {"method": "rolling", "n_windows": 4, "test_window_hours": 1, "training_lookback_days": 100}
METRICS = [{"name": "mae", "target": TARGET}, {"name": "rmse", "target": TARGET}]


def _rows() -> list[dict[str, object]]:
    base = datetime(2026, 1, 1, 20, 0, 0, tzinfo=timezone.utc)
    users = ["alice", "bob", "charlie"]
    names = ["vasp_relax", "gromacs_md", "lammps_run", "python_train"]
    rows: list[dict[str, object]] = []
    for hour in range(10):
        for j in range(4):
            submit = base + timedelta(hours=hour, minutes=10 * j)
            cores = float(j + 1)
            rows.append(
                {
                    "job_id": hour * 4 + j,
                    "submit_time": submit,
                    "end_time": submit + timedelta(minutes=20 + j),
                    "partition": "compute" if (hour + j) % 2 == 0 else "debug",
                    "user": users[hour % 3],
                    "name": names[j],
                    "num_cores_req": cores,
                    "requested_seconds": 3600.0 * (1 + j % 2),
                    "runtime_seconds": 900.0 + 30 * hour + 20 * j,
                    TARGET: 100.0 + 20 * cores + hour,
                    "embedding": [cores, float(hour % 3), 1.0],
                }
            )
    return rows


POWER_VALUES = {float(r[TARGET]) for r in _rows()}

RUNNERS = {
    "baseline": runner.run_rolling_baseline,
    "xgboost": runner.run_rolling_xgboost,
    "random_forest": runner.run_rolling_random_forest,
    "mlp": runner.run_rolling_mlp,
    "tfidf_knn": runner.run_rolling_tfidf_knn,
    "embedding_knn": runner.run_rolling_embedding_knn,
    "signature_memorizer": runner.run_rolling_signature_memorizer,
    "moe_xgboost": runner.run_rolling_moe_xgboost,
}


@pytest.mark.parametrize("name", sorted(RUNNERS))
def test_every_rolling_model_predicts_the_recipe_target(name: str) -> None:
    split = {**SPLIT, "k": 3} if name == "embedding_knn" else SPLIT
    _, payload, artifacts = RUNNERS[name](
        _rows(), split=split, metric_defs=METRICS, capture_artifacts=True
    )

    assert artifacts.y_true, f"{name} scored nothing"
    assert set(artifacts.y_true) <= POWER_VALUES, f"{name} scored something other than power"
    recorded = payload.get("run_config", {}).get("target_field") or payload["summary"].get(
        "target_field"
    )
    assert recorded == TARGET


def test_runtime_is_still_the_default_target() -> None:
    """Recipes that predate #204 name runtime_seconds and must behave exactly as before."""
    runtime_metrics = [{"name": "mae", "target": "runtime_seconds"}]
    _, payload, artifacts = runner.run_rolling_xgboost(
        _rows(), split=SPLIT, metric_defs=runtime_metrics, capture_artifacts=True
    )
    assert set(artifacts.y_true).isdisjoint(POWER_VALUES)
    assert payload["run_config"]["target_field"] == "runtime_seconds"


def test_neither_runtime_nor_power_is_ever_a_feature() -> None:
    """Predicting power, runtime is a post-hoc column like any other, and vice versa."""
    model = JobRuntimeXGBoostModel(JobRuntimeXGBoostConfig(target_field=TARGET))
    usable, ignored = model.feature_field_report(_rows())
    assert TARGET in ignored and "runtime_seconds" in ignored
    assert TARGET not in usable and "runtime_seconds" not in usable


def test_the_target_cannot_be_admitted_as_an_extra_feature() -> None:
    with pytest.raises(ValueError, match="prediction target"):
        feature_allowlist({TARGET}, target=TARGET)

    model = JobRuntimeXGBoostModel(
        JobRuntimeXGBoostConfig(target_field=TARGET, extra_feature_fields=frozenset({TARGET}))
    )
    with pytest.raises(ValueError, match="prediction target"):
        model.allowed_feature_fields()


def test_the_embedding_cannot_be_the_target() -> None:
    from hpc_oda_commons.models.job_runtime_embedding_knn.model import (
        JobRuntimeEmbeddingKnnConfig,
        JobRuntimeEmbeddingKnnModel,
    )

    with pytest.raises(ValueError, match="prediction target"):
        JobRuntimeEmbeddingKnnModel(
            JobRuntimeEmbeddingKnnConfig(target_field="embedding", embedding_field="embedding")
        )
