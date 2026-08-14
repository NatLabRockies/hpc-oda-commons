"""The submission-time feature policy shared by the runtime-prediction models."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from hpc_oda_commons.embeddings.serialize import FORBIDDEN_FIELDS
from hpc_oda_commons.models.feature_policy import (
    RUNTIME_PREDICTION_FEATURE_FIELDS,
    partition_feature_fields,
)
from hpc_oda_commons.models.job_runtime_random_forest.model import (
    JobRuntimeRandomForestConfig,
    JobRuntimeRandomForestModel,
)
from hpc_oda_commons.models.job_runtime_tfidf_knn.vectorization import detect_text_columns

pytest.importorskip("sklearn")

# Columns only known once a job has been dispatched or has finished. Every one of
# these is mapped by at least one shipped dataset descriptor, so they really do
# reach the models -- `job_state` in 21 of the 22 prepared tables.
POST_HOC_COLUMNS = (
    "job_state",
    "exit_code",
    "allocated_cpus",
    "num_cores_alloc",
    "num_nodes_alloc",
    "allocgpus",
)


def _rows(*, extra_column: str | None = None) -> list[dict[str, object]]:
    """Jobs carrying both submission-time and post-hoc columns."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows: list[dict[str, object]] = []
    for i in range(24):
        submit = base + timedelta(minutes=15 * i)
        runtime = 600.0 + 60.0 * (i % 5)
        row: dict[str, object] = {
            "job_id": i,
            "submit_time": submit,
            "start_time": submit + timedelta(seconds=30),
            "end_time": submit + timedelta(seconds=30 + runtime),
            "runtime_seconds": runtime,
            # submission-time
            "partition": "debug" if i % 2 else "compute",
            "user": f"user_{i % 3}",
            "account": "phys",
            "num_cores_req": 2 + (i % 4),
            "requested_seconds": 3600.0,
            # post-hoc
            "job_state": "TIMEOUT" if runtime > 800 else "COMPLETED",
            "exit_code": 0,
            "allocated_cpus": 4 + (i % 4),
            "num_cores_alloc": 4 + (i % 4),
            "num_nodes_alloc": 1,
            "allocgpus": i % 2,
        }
        if extra_column is not None:
            row[extra_column] = f"class_{i % 2}"
        rows.append(row)
    return rows


def _model(**config_kwargs: object) -> JobRuntimeRandomForestModel:
    return JobRuntimeRandomForestModel(
        config=JobRuntimeRandomForestConfig(
            n_windows=4,
            test_window_hours=1,
            training_lookback_days=1,
            n_estimators=8,
            max_depth=3,
            max_svd_components=8,
            target_max_one_hot_width=64,
            **config_kwargs,  # type: ignore[arg-type]
        )
    )


def _feature_columns(payload: dict) -> set[str]:
    columns: set[str] = set()
    for window in payload["windows"]:
        info = window.get("feature_info")
        if info:
            columns.update(info["numeric_columns"])
            columns.update(info["categorical_columns"])
    return columns


def test_post_hoc_columns_never_become_features() -> None:
    """The leak this policy exists to close: a column present is not a column used."""
    payload = _model().evaluate(_rows())
    used = _feature_columns(payload)

    assert used, "expected the model to select at least one feature column"
    for column in POST_HOC_COLUMNS:
        assert column not in used
    # ... while the submission-time columns are still selected.
    assert {"partition", "user", "num_cores_req", "requested_seconds"} <= used
    # Identifiers and the target/time fields stay out, as before.
    assert not ({"job_id", "runtime_seconds", "submit_time", "end_time", "start_time"} & used)


def test_extra_feature_fields_admits_a_dataset_specific_column() -> None:
    """Datasets carry fields the shared allowlist cannot know about."""
    rows = _rows(extra_column="pclass")

    without = _feature_columns(_model().evaluate(rows))
    assert "pclass" not in without

    with_extra = _feature_columns(_model(extra_feature_fields=frozenset({"pclass"})).evaluate(rows))
    assert "pclass" in with_extra


def test_evaluate_fails_fast_when_nothing_is_eligible() -> None:
    """A table with no submission-time columns must say so, not score nothing."""
    rows = [
        {
            "job_id": i,
            "submit_time": datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15 * i),
            "end_time": datetime(2026, 1, 1, tzinfo=timezone.utc)
            + timedelta(minutes=15 * i, seconds=600),
            "runtime_seconds": 600.0,
            "job_state": "COMPLETED",
            "allocated_cpus": 4,
        }
        for i in range(8)
    ]

    with pytest.raises(ValueError, match="no submission-time feature columns"):
        _model().evaluate(rows)


def test_tfidf_text_columns_exclude_the_final_state() -> None:
    """The old blocklist named `state`; canonical tables spell it `job_state`."""
    rows = [
        {
            "job_id": 1,
            "runtime_seconds": 100.0,
            "job_state": "TIMEOUT",
            "user": "alice",
            "partition": "compute",
            "name": "vasp_relax",
            "pclass": "small",
        }
    ]

    columns = detect_text_columns(rows)
    assert "job_state" not in columns
    assert "pclass" not in columns
    assert {"user", "partition", "name"} <= set(columns)

    admitted = detect_text_columns(rows, extra_fields=frozenset({"pclass"}))
    assert "pclass" in admitted
    assert "job_state" not in admitted


def test_policy_agrees_with_the_embedding_serializer() -> None:
    """One notion of "post-hoc" across the toolkit, not two that can drift apart."""
    assert not (RUNTIME_PREDICTION_FEATURE_FIELDS & FORBIDDEN_FIELDS)


def test_partition_feature_fields_reports_both_sides() -> None:
    usable, ignored = partition_feature_fields(
        ["partition", "job_state", "user", "zzz_custom"], extra=["zzz_custom"]
    )
    assert usable == ["partition", "user", "zzz_custom"]
    assert ignored == ["job_state"]
