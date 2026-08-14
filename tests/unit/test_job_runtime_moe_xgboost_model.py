"""Unit tests for the MoE XGBoost model."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from hpc_oda_commons.models.job_runtime_moe_xgboost.model import (
    POOLED_USER,
    UNKNOWN_BIN,
    MoEXGBoostConfig,
    MoEXGBoostModel,
    _Routing,
)
from hpc_oda_commons.models.job_runtime_xgboost.model import (
    JobRuntimeXGBoostConfig,
    JobRuntimeXGBoostModel,
)

pytest.importorskip("xgboost")
pytest.importorskip("sklearn")

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
# Two partition limits, the way a real system's requests pile up.
SHORT_LIMIT = 2 * 3600.0
LONG_LIMIT = 48 * 3600.0

SPLIT_KWARGS = {
    "n_windows": 8,
    "test_window_hours": 6,
    "training_lookback_days": 10,
    "max_svd_components": 8,
    "target_max_one_hot_width": 64,
}


def _rows(*, user_of=lambda i: f"user_{i % 5}", n: int = 600) -> list[dict[str, object]]:
    """Jobs clustered at two partition limits, with one heavy user.

    Every third job belongs to ``heavy_user``, so it clears the power-user
    percentile the tests configure; the rest are spread across five users.
    """
    rows: list[dict[str, object]] = []
    for i in range(n):
        submit = BASE + timedelta(minutes=20 * i)
        if i % 4 == 0:
            requested, runtime = LONG_LIMIT, 40_000.0 + 100.0 * (i % 11)
        else:
            requested, runtime = SHORT_LIMIT, 300.0 + 20.0 * (i % 13)
        rows.append(
            {
                "job_id": i,
                "submit_time": submit,
                "end_time": submit + timedelta(seconds=runtime),
                "runtime_seconds": runtime,
                "requested_seconds": requested,
                "partition": "long" if requested == LONG_LIMIT else "debug",
                "user": "heavy_user" if i % 3 == 0 else user_of(i),
                "num_cores_req": 1 + (i % 8),
            }
        )
    return rows


def _model(**overrides) -> MoEXGBoostModel:
    settings: dict[str, object] = {
        **SPLIT_KWARGS,
        "n_estimators": 10,
        "max_depth": 3,
        "min_expert_rows": 20,
        "power_user_percentile": 0.75,
    }
    settings.update(overrides)
    return MoEXGBoostModel(MoEXGBoostConfig(**settings))  # type: ignore[arg-type]


def test_evaluate_returns_finite_metrics() -> None:
    payload = _model().evaluate(_rows())

    assert math.isfinite(payload["mae"]) and payload["mae"] >= 0.0
    assert math.isfinite(payload["rmse"]) and payload["rmse"] >= 0.0
    assert payload["summary"]["rows_scored"] >= 1


def test_scores_exactly_the_rows_a_single_model_scores() -> None:
    """The property that makes its MAE comparable with the other models'.

    Routing happens inside the shared window, so the scored population must match
    a plain XGBoost run on the same rows with the same split — no bin dropped, no
    window grid of its own.
    """
    rows = _rows()
    flat = JobRuntimeXGBoostModel(JobRuntimeXGBoostConfig(**SPLIT_KWARGS)).evaluate(
        rows, capture_artifacts=True
    )
    moe = _model().evaluate(rows, capture_artifacts=True)

    assert moe["summary"]["rows_scored"] == flat["summary"]["rows_scored"]
    assert moe["summary"]["windows_scored"] == flat["summary"]["windows_scored"]
    # Same rows, in the same order: the true values line up exactly.
    assert moe["_y_true"] == flat["_y_true"]


def test_payload_matches_the_shared_rolling_shape() -> None:
    """A leaderboard consumer should not have to special-case this model."""
    rows = _rows()
    flat = JobRuntimeXGBoostModel(JobRuntimeXGBoostConfig(**SPLIT_KWARGS)).evaluate(rows)
    moe = _model().evaluate(rows)

    assert set(flat["summary"]) <= set(moe["summary"])
    assert "moe_routing" in moe["summary"]
    assert set(flat["windows"][0]) == set(moe["windows"][0])


def test_bin_edges_come_from_the_data() -> None:
    """#124's ask: boundaries that follow each system's partition limits."""
    model = _model()
    edges = model._wallclock_edges(_rows())

    assert edges[-1] == math.inf
    # The 2h cluster is the dominant mode, so it becomes the first boundary.
    assert edges[0] == pytest.approx(SHORT_LIMIT)
    # k detected clusters become k edges plus one open bin above the largest.
    assert len(edges) <= model.config.n_wallclock_bins + 1


def test_largest_cluster_gets_its_own_bin() -> None:
    """The biggest long-job cluster must not be merged into the catch-all.

    Truncating the edge list dropped the largest detected mode, so on Kestrel the
    48h cluster (10.6% of jobs) shared a bin with the 0.6% requesting *more* than
    48h -- the one place the wallclock signal should be sharpest.
    """
    base = BASE
    rows: list[dict[str, object]] = []
    for i in range(600):
        submit = base + timedelta(minutes=20 * i)
        # a dominant short cluster, a large 48h cluster, and a few rare longer jobs
        requested = LONG_LIMIT if i % 3 else SHORT_LIMIT
        if i % 97 == 0:
            requested = 96 * 3600.0
        runtime = 300.0 + (i % 17) * 30.0
        rows.append(
            {
                "job_id": i,
                "submit_time": submit,
                "end_time": submit + timedelta(seconds=runtime),
                "runtime_seconds": runtime,
                "requested_seconds": requested,
                "partition": "p",
                "user": f"user_{i % 4}",
                "num_cores_req": 1 + (i % 4),
            }
        )

    edges = _model()._wallclock_edges(rows)

    assert LONG_LIMIT in edges, "the largest cluster needs its own boundary"
    assert edges[-1] == math.inf
    routing = _Routing(bin_edges=edges, power_users=frozenset())
    # the 48h cluster and the rarer 96h jobs land in different bins
    assert routing.bin_index({"requested_seconds": LONG_LIMIT}) != routing.bin_index(
        {"requested_seconds": 96 * 3600.0}
    )


def test_explicit_bin_edges_override_the_derived_ones() -> None:
    model = _model(wallclock_bin_edges_hours=(1.0, 12.0))
    assert model._wallclock_edges(_rows()) == (3600.0, 43200.0, math.inf)


def test_missing_user_and_wallclock_route_to_the_pool() -> None:
    """A null user used to crash routing outright; a null wallclock was read as 0."""
    model = _model()
    routing = model._build_daily_preprocessing_artifacts(_rows()).routing

    assert routing.key({"user": None, "requested_seconds": SHORT_LIMIT})[0] == POOLED_USER
    assert routing.key({"requested_seconds": SHORT_LIMIT})[0] == POOLED_USER
    assert routing.key({"user": "heavy_user", "requested_seconds": None})[1] == UNKNOWN_BIN
    assert routing.key({"user": "heavy_user"})[1] == UNKNOWN_BIN


def test_evaluates_a_table_whose_user_column_is_entirely_null() -> None:
    rows = _rows(user_of=lambda i: None)
    for row in rows:
        row["user"] = None

    payload = _model().evaluate(rows)

    assert payload["summary"]["rows_scored"] >= 1
    assert payload["summary"]["moe_routing"]["power_users_last"] == 0


def test_routing_is_derived_from_training_rows_only() -> None:
    """No look-ahead: a user who only appears after the split cannot be a power user."""
    rows = _rows()
    train_rows = rows[: len(rows) // 2]
    for row in rows[len(rows) // 2 :]:
        row["user"] = "late_arrival"

    routing = _model()._build_daily_preprocessing_artifacts(train_rows).routing

    assert "late_arrival" not in routing.power_users
    assert "heavy_user" in routing.power_users


def test_sparse_bins_fall_back_instead_of_dropping_rows() -> None:
    """Raising the expert threshold above the data must not cost coverage."""
    rows = _rows()
    covered = _model(min_expert_rows=10).evaluate(rows)
    starved = _model(min_expert_rows=10_000).evaluate(rows)

    assert starved["summary"]["rows_scored"] == covered["summary"]["rows_scored"]
    assert starved["summary"]["moe_routing"]["routed_row_fraction"] == 0.0
    assert covered["summary"]["moe_routing"]["routed_row_fraction"] > 0.0


def test_time_decay_changes_the_fit() -> None:
    rows = _rows()
    flat = _model(time_decay_rate=0.0).evaluate(rows, capture_artifacts=True)
    decayed = _model(time_decay_rate=0.5).evaluate(rows, capture_artifacts=True)

    assert flat["_y_pred"] != decayed["_y_pred"]


def test_config_defaults() -> None:
    config = MoEXGBoostConfig()
    # Off by default, like the shared base: a differing default would confound every
    # comparison between this model and any other.
    assert config.time_decay_rate == 0.0
    assert config.power_user_percentile == 0.99
    assert config.min_expert_rows == 100
    assert config.n_wallclock_bins == 5
    assert config.wallclock_bin_edges_hours is None


def test_empty_rows_raises() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        MoEXGBoostModel().evaluate([])
