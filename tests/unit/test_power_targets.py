"""Every runtime model predicts whatever column the recipe's metrics name (#204).

The table carries both runtime (900-1300 s) and per-node power (100-200 W) in ranges that
cannot be confused, so a model that silently kept predicting runtime would be caught by its
own y_true. The embedding is a float32 array, as the table loader hands it over: column scans
that compare every value with "" used to crash on it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from hpc_oda_commons.benchmark import runner
from hpc_oda_commons.models.feature_policy import feature_allowlist
from hpc_oda_commons.models.xgboost.model import (
    XGBoostConfig,
    XGBoostModel,
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
                    "embedding": np.asarray([cores, float(hour % 3), 1.0], dtype=np.float32),
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
    "uopc": runner.run_rolling_uopc,
}


@pytest.mark.parametrize("name", sorted(RUNNERS))
def test_every_rolling_model_predicts_the_recipe_target(name: str) -> None:
    split = {**SPLIT, "k": 3} if name in {"embedding_knn", "uopc"} else SPLIT
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
    model = XGBoostModel(XGBoostConfig(target_field=TARGET))
    usable, ignored = model.feature_field_report(_rows())
    assert TARGET in ignored and "runtime_seconds" in ignored
    assert TARGET not in usable and "runtime_seconds" not in usable


def test_the_target_cannot_be_admitted_as_an_extra_feature() -> None:
    with pytest.raises(ValueError, match="prediction target"):
        feature_allowlist({TARGET}, target=TARGET)

    model = XGBoostModel(
        XGBoostConfig(target_field=TARGET, extra_feature_fields=frozenset({TARGET}))
    )
    with pytest.raises(ValueError, match="prediction target"):
        model.allowed_feature_fields()


def test_the_embedding_cannot_be_the_target() -> None:
    from hpc_oda_commons.models.embedding_knn.model import (
        EmbeddingKnnConfig,
        EmbeddingKnnModel,
    )

    with pytest.raises(ValueError, match="prediction target"):
        EmbeddingKnnModel(EmbeddingKnnConfig(target_field="embedding", embedding_field="embedding"))


def test_rolling_recipes_can_report_mape_and_r2() -> None:
    """Needed to compare with UoPC, whose write-up reports both. They are computed over all
    scored rows; arm ranking still refuses to pool them from windows."""
    metrics = [*METRICS, {"name": "mape", "target": TARGET}, {"name": "r2", "target": TARGET}]
    scored, _, _ = runner.run_rolling_baseline(_rows(), split=SPLIT, metric_defs=metrics)
    assert set(scored) == {"mae", "rmse", "mape", "r2"}


def test_rolling_power_recipes_share_one_protocol() -> None:
    """The comparison is only fair if every model sees the same windows and rows: the same
    dataset, split shape and metric target per power quantity. Model-specific knobs (k,
    theta) may differ. Eagle and Kestrel (#217) use F-DATA's split shape, on their own
    tables, average power only. Their embedding models (#219) read the same slice with a
    computed embedding added, which keeps every row. PM100 (#230) has both targets, and its
    embedded table holds the prepared table's rows."""
    import importlib.resources as ir
    from pathlib import Path

    from hpc_oda_commons.benchmark.recipes import load_recipe

    root = Path(str(ir.files("hpc_oda_commons") / "recipes" / "job-power"))
    shared = ("method", "n_windows", "test_window_hours", "training_lookback_days")
    shapes: set[tuple] = set()
    models: dict[tuple[str, str], set[str]] = {}
    for path in sorted(root.glob("*_rolling_*.yml")):
        recipe = load_recipe(path)
        target = runner.recipe_target(recipe["metrics"])
        shapes.add(tuple(recipe["split"][k] for k in shared))
        block = recipe["dataset"]
        window = tuple((block.get("window") or {}).values())
        rows = (block["id"], window, tuple(block.get("require_nonnull") or ()))
        models.setdefault((target, rows), set()).add(recipe["model"]["id"])
    assert len(shapes) == 1, shapes
    fdata = (
        "fdata_fugaku",
        ("2023-11-30", "2024-04-30", "submit"),
        ("avgpcon_per_node", "maxpcon_per_node", "embedding"),
    )
    assert set(models) == {
        ("avgpcon_per_node", fdata),
        ("maxpcon_per_node", fdata),
        ("avgpcon_per_node", ("nlr_eagle", ("2023-05-01", "2023-09-30"), ())),
        ("avgpcon_per_node", ("nlr_kestrel", ("2025-08-01", "2026-01-01"), ())),
        ("avgpcon_per_node", ("pm100", (), ())),
        ("maxpcon_per_node", ("pm100", (), ())),
    }
    # Every system runs the same models.
    assert len({frozenset(ids) for ids in models.values()}) == 1, models


def test_nlr_embedding_recipes_read_the_embedded_slice() -> None:
    """Only the models that need an embedding read the embedded tables (#219, #230)."""
    import importlib.resources as ir
    from pathlib import Path

    from hpc_oda_commons.benchmark.recipes import load_recipe

    root = Path(str(ir.files("hpc_oda_commons") / "recipes" / "job-power"))
    needs_embedding = {"model.uopc", "model.embedding_knn"}
    for system in ("eagle", "kestrel", "pm100"):
        for path in sorted(root.glob(f"*_rolling_*_{system}.yml")):
            recipe = load_recipe(path)
            embedded = recipe["dataset"]["table_path"].endswith("_power_embedded/data.parquet")
            assert embedded == (recipe["model"]["id"] in needs_embedding), path.name
