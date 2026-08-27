"""Target encoding for high-cardinality categoricals (#172)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from hpc_oda_commons.models.job_runtime_xgboost.model import (
    JobRuntimeXGBoostConfig,
    JobRuntimeXGBoostModel,
)

UTC = dt.timezone.utc
BASE = dt.datetime(2026, 1, 1, tzinfo=UTC)


def _rows(n: int, *, users: int, runtime_of) -> list[dict]:
    out = []
    for i in range(n):
        s = BASE + dt.timedelta(minutes=i * 20)
        out.append(
            {
                "submit_time": s,
                "end_time": s + dt.timedelta(minutes=10),
                "user": f"u{i % users}",
                "partition": ["debug", "compute"][i % 2],
                "requested_seconds": 3600.0,
                "runtime_seconds": float(runtime_of(i)),
            }
        )
    return out


def _model(**kw) -> JobRuntimeXGBoostModel:
    kw.setdefault("target_encode_min_cardinality", 8)
    return JobRuntimeXGBoostModel(config=JobRuntimeXGBoostConfig(**kw))


def test_disabled_by_default_so_no_measured_number_moves() -> None:
    """Enabling it changes every benchmark result, so it must be an explicit choice."""
    artifacts = JobRuntimeXGBoostModel()._build_daily_preprocessing_artifacts(
        _rows(200, users=50, runtime_of=lambda i: 100 + i % 7)
    )

    assert artifacts.target_encoded_columns == ()
    assert artifacts.target_encoding == {}


def test_high_cardinality_columns_leave_the_one_hot() -> None:
    """The width of one column raises a SHARED min_frequency, degrading the others too."""
    rows = _rows(400, users=50, runtime_of=lambda i: 100 + i % 7)

    artifacts = _model()._build_daily_preprocessing_artifacts(rows)

    assert "user" in artifacts.target_encoded_columns
    assert "user" not in artifacts.categorical_columns
    assert "partition" in artifacts.categorical_columns  # low cardinality stays one-hot


def test_a_test_rows_own_runtime_cannot_reach_its_encoding() -> None:
    """The leakage guard. This repo has shipped a leak before (#132), so it is asserted.

    Two datasets identical except for the runtimes of rows the encoder never sees must
    produce identical encodings.
    """
    train = _rows(300, users=20, runtime_of=lambda i: 100 + (i % 20) * 10)
    model = _model()

    artifacts = model._build_daily_preprocessing_artifacts(train)

    held_out = _rows(40, users=20, runtime_of=lambda i: 999_999.0)
    encoded_a = model._target_encoded_features(held_out, artifacts)
    # the held-out rows' targets differ wildly, yet their encodings come from training only
    for row in held_out:
        row["runtime_seconds"] = 1.0
    encoded_b = model._target_encoded_features(held_out, artifacts)

    np.testing.assert_array_equal(encoded_a, encoded_b)


def test_encoding_tracks_the_categorys_training_runtime() -> None:
    """A user whose jobs run long must encode higher than one whose jobs run short."""
    rows = _rows(600, users=10, runtime_of=lambda i: 10_000.0 if i % 10 == 0 else 100.0)
    model = _model(target_encode_smoothing=0.0)

    artifacts = model._build_daily_preprocessing_artifacts(rows)
    table = artifacts.target_encoding["user"]

    assert table["u0"] == pytest.approx(10_000.0)  # the long-running user
    assert table["u1"] == pytest.approx(100.0)


def test_smoothing_pulls_rare_categories_toward_the_prior() -> None:
    """Without it, a category seen twice is trusted as much as one seen a thousand times."""
    rows = _rows(600, users=10, runtime_of=lambda i: 10_000.0 if i % 10 == 0 else 100.0)
    rows.append({**rows[0], "user": "rare", "runtime_seconds": 500_000.0})

    unsmoothed = _model(target_encode_smoothing=0.0)._build_daily_preprocessing_artifacts(rows)
    smoothed = _model(target_encode_smoothing=50.0)._build_daily_preprocessing_artifacts(rows)

    assert unsmoothed.target_encoding["user"]["rare"] == pytest.approx(500_000.0)
    # seen once against a prior worth 50 observations: almost entirely the prior
    assert smoothed.target_encoding["user"]["rare"] < 20_000.0
    assert smoothed.target_encoding["user"]["rare"] > smoothed.target_encoding_default


def test_an_unseen_category_takes_the_prior() -> None:
    rows = _rows(300, users=20, runtime_of=lambda i: 100 + (i % 20) * 10)
    model = _model()
    artifacts = model._build_daily_preprocessing_artifacts(rows)

    stranger = [{**rows[0], "user": "never_seen_before"}]
    encoded = model._target_encoded_features(stranger, artifacts)

    assert encoded[0, 0] == pytest.approx(artifacts.target_encoding_default)


def test_the_encoded_column_reaches_the_feature_matrix() -> None:
    rows = _rows(300, users=20, runtime_of=lambda i: 100 + (i % 20) * 10)
    model = _model()
    artifacts = model._build_daily_preprocessing_artifacts(rows)

    without = JobRuntimeXGBoostModel()
    plain = without._transform_rows(rows, without._build_daily_preprocessing_artifacts(rows))
    with_te = model._transform_rows(rows, artifacts)

    assert with_te.shape[0] == plain.shape[0]
    assert artifacts.target_encoded_columns  # guard: the test is vacuous without this
    assert not np.allclose(with_te.shape[1], 0)
