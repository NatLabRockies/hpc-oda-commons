"""UoPC feature modes (#222): zscore (the default), embedding only, and balanced."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from hpc_oda_commons.benchmark.recipes import validate_recipe
from hpc_oda_commons.kernel.validate import SchemaValidationError
from hpc_oda_commons.models.job_power_uopc.model import (
    BALANCED_FREQUENCY_WEIGHT,
    BALANCED_NODE_WEIGHT,
    JobPowerUopcModel,
    balanced_numeric_features,
)
from hpc_oda_commons.models.job_power_uopc.rolling import (
    JobPowerUopcRollingConfig,
    JobPowerUopcRollingModel,
)

TARGET = "avgpcon_per_node"
METRICS = [{"name": "mae", "target": TARGET}, {"name": "rmse", "target": TARGET}]
BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_balanced_columns_weight_log_nodes_and_frequency_range() -> None:
    nodes = np.array([1, 16, 152064, 0, np.nan])
    frequency = np.array([2000, 2200, 2100, np.nan, 2000])
    cols = balanced_numeric_features(nodes, frequency, fit=np.ones(5, dtype=bool))

    assert cols[:, 0] == pytest.approx(BALANCED_NODE_WEIGHT * np.log2([1, 16, 152064, 1, 1]))
    assert cols[1, 0] == pytest.approx(0.8)  # 1 -> 16 nodes
    assert cols[:, 1] == pytest.approx(BALANCED_FREQUENCY_WEIGHT * np.array([0, 1, 0.5, 0, 0]))


def test_balanced_frequency_range_comes_from_the_fit_rows_only() -> None:
    frequency = np.array([2000.0, 2200.0, 2400.0])
    fit = np.array([True, True, False])  # the 2400 job is in the test period
    cols = balanced_numeric_features(np.ones(3), frequency, fit=fit)

    # Scaled over 2000-2200; the unseen 2400 is clipped to the top of that range.
    assert cols[:, 1] == pytest.approx([0.0, BALANCED_FREQUENCY_WEIGHT, BALANCED_FREQUENCY_WEIGHT])


def test_a_frequency_that_never_varies_contributes_nothing() -> None:
    cols = balanced_numeric_features(np.ones(3), np.full(3, 2200.0), fit=np.ones(3, dtype=bool))
    assert not cols[:, 1].any()


def _paper_rows() -> list[dict]:
    rng = np.random.default_rng(3)
    rows = []
    for idx in range(90):
        submit = datetime(2024, 1, 20, tzinfo=timezone.utc) + timedelta(hours=8 * idx)
        rows.append(
            {
                "job_id": idx,
                "user": f"u{idx % 3}",
                "submit_time": submit,
                "end_time": submit + timedelta(hours=2),
                "avgpcon": float(rng.integers(80, 300)),
                "maxpcon": float(rng.integers(300, 600)),
                "num_nodes_req": 2 ** int(rng.integers(0, 6)),
                "num_nodes_alloc": 1,
                "num_cores_req": 48,
                # The test period (from Feb 1) introduces a frequency history never saw.
                "freq_req": 2000 + 200 * (idx % 2) + (400 if idx >= 40 else 0),
                "embedding": rng.random(4).tolist(),
            }
        )
    return rows


@pytest.mark.parametrize(("features", "width"), [("zscore", 7), ("embedding", 4), ("balanced", 6)])
def test_paper_protocol_feature_width(features: str, width: int) -> None:
    prepared = JobPowerUopcModel()._prepare_paper_data(
        _paper_rows(), test_start="2024-02-01", features=features
    )
    assert prepared.features.shape[1] == width
    assert prepared.features_mode == features


def test_paper_protocol_fits_balanced_frequency_on_history_only() -> None:
    rows = _paper_rows()
    prepared = JobPowerUopcModel()._prepare_paper_data(
        rows, test_start="2024-02-01", features="balanced"
    )
    freq_col = prepared.features[:, -1]
    # History spans 2000-2200, so every later, higher frequency is clipped to the top.
    assert freq_col.max() == pytest.approx(BALANCED_FREQUENCY_WEIGHT)
    assert sorted({round(float(v), 6) for v in freq_col}) == [0.0, BALANCED_FREQUENCY_WEIGHT]


def _job(i: int, user: str, hour: float, power: float, nodes: float, emb: list[float]) -> dict:
    submit = BASE + timedelta(hours=hour)
    return {
        "job_id": i,
        "user": user,
        "submit_time": submit,
        "end_time": submit + timedelta(minutes=30),
        "num_cores_req": 48.0 * nodes,
        "num_nodes_req": nodes,
        "freq_req": 2200.0,
        "embedding": emb,
        TARGET: power,
    }


def _rows() -> list[dict]:
    """alice's 64-node jobs draw 200 W and her 1-node jobs 100 W. The test job is 64 nodes
    but its embedding matches the 1-node jobs exactly (the 64-node ones are 0.1 away). bob's
    whole-machine job inflates the nodes' spread, as on F-DATA."""
    rows = []
    for i in range(5):
        rows.append(_job(len(rows), "alice", i, 100.0, 1.0, [1.0, 0.0]))
        rows.append(_job(len(rows), "alice", i + 0.5, 200.0, 64.0, [0.995, 0.0998749]))
    rows.append(_job(len(rows), "bob", 6.0, 90.0, 152064.0, [0.0, 1.0]))
    rows.append(_job(len(rows), "alice", 20.0, 200.0, 64.0, [1.0, 0.0]))
    return rows


def _model(features: str, **overrides) -> JobPowerUopcRollingModel:
    cfg = {"n_windows": 1, "test_window_hours": 1, "training_lookback_days": 2, "theta": 10}
    cfg = {**cfg, "k": 3, "features": features, **overrides}
    return JobPowerUopcRollingModel(JobPowerUopcRollingConfig(**cfg))


@pytest.mark.parametrize(
    ("features", "prediction"),
    [
        # z-scored nodes: the whole-machine job makes 1 vs 64 nodes negligible.
        ("zscore", 100.0),
        # The embedding alone can't see nodes at all.
        ("embedding", 100.0),
        # log2 nodes: 64 nodes is 1.2 from 1 node, far more than the 0.1 name difference.
        ("balanced", 200.0),
    ],
)
def test_rolling_feature_modes_choose_different_neighbours(
    features: str, prediction: float
) -> None:
    result = _model(features).evaluate(_rows(), metric_defs=METRICS, capture_artifacts=True)

    assert result["_y_true"] == [200.0]
    assert result["_y_pred"] == [prediction]
    assert result["summary"]["features"].startswith("emb")


def test_rolling_balanced_works_without_a_frequency_column() -> None:
    """Eagle and Kestrel have no requested frequency."""
    rows = [{k: v for k, v in r.items() if k != "freq_req"} for r in _rows()]
    result = _model("balanced").evaluate(rows, metric_defs=METRICS, capture_artifacts=True)
    assert result["_y_pred"] == [200.0]


def test_zscore_is_the_default() -> None:
    assert JobPowerUopcRollingConfig().features == "zscore"


def test_unknown_mode_is_an_error() -> None:
    with pytest.raises(ValueError, match="features must be one of"):
        _model("tfidf")


def _recipe(model: str, split: dict) -> dict:
    return {
        "recipe_id": "recipe.job_power.uopc_features_test",
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
        {"method": "cutoff", "test_start": "2024-02-01", "uopc_features": "balanced"},
        {"method": "rolling", "n_windows": 3, "uopc_features": "embedding"},
    ],
)
def test_recipe_accepts_uopc_features_for_uopc(split: dict) -> None:
    validate_recipe(_recipe("model.job_power_uopc", split))


@pytest.mark.parametrize(
    ("model", "split"),
    [
        ("model.job_runtime_xgboost", {"method": "rolling", "n_windows": 3}),
        ("model.job_power_uopc", {"method": "fixed", "train_fraction": 0.8, "seed": 0}),
    ],
)
def test_recipe_rejects_uopc_features_elsewhere(model: str, split: dict) -> None:
    with pytest.raises(SchemaValidationError, match="uopc_features only applies"):
        validate_recipe(_recipe(model, {**split, "uopc_features": "balanced"}))


def test_recipe_rejects_an_unknown_mode() -> None:
    split = {"method": "rolling", "n_windows": 3, "uopc_features": "tfidf"}
    with pytest.raises(SchemaValidationError):
        validate_recipe(_recipe("model.job_power_uopc", split))
