"""The daily preprocessing store (#213): built once, reused, and never changes a result.

A rolling-tabular run builds one OHE + SVD artifact per day before it fits anything, and every
model on the same rows builds the same ones. The store keeps them between runs. These tests
pin what makes that safe: a warm store returns exactly what a cold build produces, entries are
shared only where the build provably reads the same inputs, and anything it cannot read is
rebuilt rather than trusted.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from hpc_oda_commons.models.job_runtime_mlp.model import JobRuntimeMlpConfig, JobRuntimeMlpModel
from hpc_oda_commons.models.job_runtime_random_forest.model import (
    JobRuntimeRandomForestConfig,
    JobRuntimeRandomForestModel,
)
from hpc_oda_commons.models.rolling_tabular.artifact_store import (
    CACHE_ENV,
    DailyArtifactStore,
    _column_bytes,
    daily_artifacts_key,
    default_artifact_store,
)
from hpc_oda_commons.models.rolling_tabular.preprocessing import (
    _plan_and_fit_svd,
    fit_truncated_svd,
)

pytest.importorskip("sklearn")

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
_PARTITIONS = ("debug", "compute", "gpu", "bigmem")
_USERS = ("u1", "u2", "u3", "u4", "u5")

_SHARED = {
    "n_windows": 6,
    "test_window_hours": 12,
    "training_lookback_days": 2,
    "max_svd_components": 4,
    "target_max_one_hot_width": 16,
}


def _rows(n_hours: int = 96) -> list[dict]:
    rows = []
    for i in range(n_hours):
        submit = _BASE + timedelta(hours=i)
        cores = (2, 4, 8)[i % 3]
        rows.append(
            {
                "job_id": i,
                "submit_time": submit,
                "end_time": submit + timedelta(minutes=30),
                "runtime_seconds": 600.0 + 100.0 * cores + 37.0 * (i % 5),
                "power_watts": 40.0 + 3.0 * cores + (i % 7),
                "partition": _PARTITIONS[i % len(_PARTITIONS)],
                "user": _USERS[(i // 2) % len(_USERS)],
                "num_cores_req": cores,
                "requested_seconds": 3600.0 * (1 + i % 4),
            }
        )
    return rows


def _mlp(**overrides) -> JobRuntimeMlpModel:
    config = {**_SHARED, "hidden_layer_sizes": (8,), "max_iter": 40, **overrides}
    return JobRuntimeMlpModel(JobRuntimeMlpConfig(**config))


def _rf(**overrides) -> JobRuntimeRandomForestModel:
    config = {**_SHARED, "n_estimators": 5, "n_jobs": 1, **overrides}
    return JobRuntimeRandomForestModel(JobRuntimeRandomForestConfig(**config))


def _without_store_counts(payload: dict) -> dict:
    out = dict(payload)
    out["summary"] = {k: v for k, v in payload["summary"].items() if k != "preprocessing_store"}
    return out


def test_selection_svd_is_the_fit_a_second_call_would_make():
    rng = np.random.default_rng(0)
    matrix = (rng.random((200, 30)) > 0.8).astype(float)
    plan, fitted = _plan_and_fit_svd(matrix, target_coverage=1.0, max_svd_components=8)
    assert plan.selected_components == plan.evaluated_components == 8
    refit, _ = fit_truncated_svd(matrix, plan.selected_components, 42)
    assert np.array_equal(fitted.components_, refit.components_)
    assert np.array_equal(fitted.transform(matrix), refit.transform(matrix))


def test_cold_warm_and_no_store_give_identical_payloads(tmp_path):
    rows = _rows()
    plain = _mlp().evaluate(rows)
    assert "preprocessing_store" not in plain["summary"]

    cold_model = _mlp()
    cold_model.artifact_store = DailyArtifactStore(tmp_path)
    cold = cold_model.evaluate(rows)
    built = cold["summary"]["preprocessing_refits"]
    assert built > 0
    assert cold["summary"]["preprocessing_store"] == {"hits": 0, "misses": built}

    warm_model = _mlp()
    warm_model.artifact_store = DailyArtifactStore(tmp_path)
    warm = warm_model.evaluate(rows)
    assert warm["summary"]["preprocessing_store"] == {"hits": built, "misses": 0}

    assert _without_store_counts(cold) == plain
    assert _without_store_counts(warm) == plain


def test_models_and_targets_share_entries_when_the_build_reads_the_same_inputs(tmp_path):
    rows = _rows()
    first = _mlp()
    first.artifact_store = DailyArtifactStore(tmp_path)
    built = first.evaluate(rows)["summary"]["preprocessing_refits"]

    other_model = _rf()
    other_model.artifact_store = DailyArtifactStore(tmp_path)
    shared = other_model.evaluate(rows)["summary"]["preprocessing_store"]
    assert shared == {"hits": built, "misses": 0}

    reference = _rf()
    assert _without_store_counts(other_model.evaluate(rows)) == reference.evaluate(rows)


def test_the_key_follows_the_feature_values_and_settings_and_nothing_else():
    model = _mlp()
    rows = _rows(48)
    key = model._daily_artifacts_key(rows)

    changed_feature = [dict(r) for r in rows]
    changed_feature[3]["partition"] = "other"
    assert model._daily_artifacts_key(changed_feature) != key

    reordered = [rows[1], rows[0], *rows[2:]]
    assert model._daily_artifacts_key(reordered) != key

    # A column outside the allowlist cannot reach the artifacts, so it cannot split the key.
    changed_other = [dict(r) for r in rows]
    changed_other[3]["job_id"] = 10_000
    assert model._daily_artifacts_key(changed_other) == key

    assert _mlp(max_svd_components=3)._daily_artifacts_key(rows) != key
    # Regressor hyperparameters do not touch the preprocessing.
    assert _mlp(max_iter=7)._daily_artifacts_key(rows) == key


def test_the_target_joins_the_key_only_when_target_encoding_reads_it():
    rows = _rows(48)
    model = _mlp()
    other_target = [dict(r, runtime_seconds=r["runtime_seconds"] + 1.0) for r in rows]
    assert model._daily_artifacts_key(other_target) == model._daily_artifacts_key(rows)

    encoding = _mlp(target_encode_min_cardinality=2)
    assert encoding._daily_artifacts_key(other_target) != encoding._daily_artifacts_key(rows)


def test_a_subclass_that_changes_the_build_gets_entries_of_its_own():
    class Different(JobRuntimeMlpModel):
        def _detect_numeric_columns(self, rows, *, exclude):
            return []

    rows = _rows(48)
    config = dataclasses.replace(_mlp().config)
    assert Different(config)._daily_artifacts_key(rows) != _mlp()._daily_artifacts_key(rows)


def test_an_unreadable_entry_is_rebuilt_not_trusted(tmp_path):
    rows = _rows()
    first = _mlp()
    first.artifact_store = DailyArtifactStore(tmp_path)
    expected = _without_store_counts(first.evaluate(rows))

    entries = sorted(tmp_path.rglob("*.pkl"))
    assert entries
    entries[0].write_bytes(b"not a pickle")

    again = _mlp()
    again.artifact_store = DailyArtifactStore(tmp_path)
    with pytest.warns(RuntimeWarning, match="unreadable preprocessing cache entry"):
        payload = again.evaluate(rows)
    assert payload["summary"]["preprocessing_store"]["misses"] == 1
    assert _without_store_counts(payload) == expected


def test_long_arrays_are_hashed_by_their_contents():
    # numpy's repr elides long arrays with "...", so two that differ in the middle would print
    # the same. The key must still tell them apart.
    a = np.zeros(5000, dtype=np.float32)
    b = a.copy()
    b[2500] = 1.0
    assert repr(a) == repr(b)
    assert _column_bytes([a]) != _column_bytes([b])
    settings = {"s": 1}
    key_a = daily_artifacts_key([{"v": a}], columns=["v"], settings=settings)
    key_b = daily_artifacts_key([{"v": b}], columns=["v"], settings=settings)
    assert key_a != key_b


def test_types_that_the_column_detection_tells_apart_change_the_key():
    settings = {"s": 1}
    keys = {
        daily_artifacts_key([{"v": v}], columns=["v"], settings=settings) for v in (1, 1.0, True)
    }
    assert len(keys) == 3


def test_default_store_location_and_switch(monkeypatch, tmp_path):
    monkeypatch.delenv(CACHE_ENV, raising=False)
    store = default_artifact_store(cwd=tmp_path)
    assert store is not None
    assert store.root == tmp_path / ".hpc_oda" / "cache" / "preprocessing"

    monkeypatch.setenv(CACHE_ENV, str(tmp_path / "elsewhere"))
    assert default_artifact_store().root == tmp_path / "elsewhere"

    for off in ("off", "OFF", "0", "false"):
        monkeypatch.setenv(CACHE_ENV, off)
        assert default_artifact_store() is None


def test_the_store_is_not_part_of_the_run_config(tmp_path):
    from hpc_oda_commons.benchmark.runner import resolved_run_config

    model = _mlp()
    before = resolved_run_config(model)
    model.artifact_store = DailyArtifactStore(tmp_path)
    assert resolved_run_config(model) == before


def test_the_moe_builds_its_routing_on_shared_entries(tmp_path):
    pytest.importorskip("xgboost")
    from hpc_oda_commons.models.job_runtime_moe_xgboost.model import (
        MoEXGBoostConfig,
        MoEXGBoostModel,
    )

    def moe() -> MoEXGBoostModel:
        return MoEXGBoostModel(MoEXGBoostConfig(**_SHARED, n_estimators=5, min_expert_rows=4))

    rows = _rows()
    first = _mlp()
    first.artifact_store = DailyArtifactStore(tmp_path)
    built = first.evaluate(rows)["summary"]["preprocessing_refits"]

    stored = moe()
    stored.artifact_store = DailyArtifactStore(tmp_path)
    payload = stored.evaluate(rows)
    assert payload["summary"]["preprocessing_store"] == {"hits": built, "misses": 0}
    assert _without_store_counts(payload) == moe().evaluate(rows)
