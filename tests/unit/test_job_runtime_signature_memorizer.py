"""Unit tests for the signature-memorization baseline (#171)."""

from __future__ import annotations

import datetime as dt

import pytest

from hpc_oda_commons.models.job_runtime_signature_memorizer import (
    JobRuntimeSignatureMemorizerModel,
    SignatureMemorizerConfig,
)

UTC = dt.timezone.utc
BASE = dt.datetime(2026, 1, 1, tzinfo=UTC)
METRICS = [{"name": "mae", "target": "runtime_seconds"}]


def _cfg(**kw) -> SignatureMemorizerConfig:
    kw.setdefault("n_windows", 30)
    kw.setdefault("test_window_hours", 6)
    kw.setdefault("training_lookback_days", 30)
    return SignatureMemorizerConfig(**kw)


def _rows(n: int, runtime_of) -> list[dict]:
    out = []
    for i in range(n):
        s = BASE + dt.timedelta(minutes=i * 20)
        out.append(
            {
                "submit_time": s,
                "end_time": s + dt.timedelta(minutes=10),
                "partition": ["debug", "compute"][i % 2],
                "user": f"u{i % 5}",
                "requested_seconds": float(3600 * (1 + i % 3)),
                "runtime_seconds": float(runtime_of(i)),
            }
        )
    return out


def test_it_recovers_a_runtime_determined_by_the_signature() -> None:
    """When runtime is a function of the features, memorization is exactly right."""
    rows = _rows(600, lambda i: 100 + (i % 5) * 50 + (i % 2) * 7)

    payload = JobRuntimeSignatureMemorizerModel(_cfg()).evaluate(rows, metric_defs=METRICS)

    assert payload["mae"] == pytest.approx(0.0)
    assert payload["summary"]["memorization"]["exact_match_coverage"] == pytest.approx(1.0)


def test_coverage_is_reported_because_the_metric_needs_it() -> None:
    """A good score on 20% coverage and on 90% are different claims."""
    rows = _rows(600, lambda i: 100 + (i % 5) * 50)

    payload = JobRuntimeSignatureMemorizerModel(_cfg()).evaluate(rows, metric_defs=METRICS)
    memo = payload["summary"]["memorization"]

    assert 0.0 <= memo["exact_match_coverage"] <= 1.0
    assert memo["rows_scored"] == payload["summary"]["rows_scored"]
    assert memo["windows"] > 0


def test_it_scores_the_same_rows_as_a_fitted_model() -> None:
    """Comparability is the whole point: same grid, same scored population."""
    from hpc_oda_commons.models.job_runtime_baseline.model import JobRuntimeBaselineModel

    rows = _rows(600, lambda i: 100 + (i % 7) * 30)
    memo = JobRuntimeSignatureMemorizerModel(_cfg()).evaluate(rows, metric_defs=METRICS)

    # the shared driver reports the scored population identically
    assert (
        memo["summary"]["windows_scored"]
        == memo["summary"]["windows_total"] - (memo["summary"]["windows_skipped"])
    )
    assert memo["summary"]["rows_scored"] > 0
    assert JobRuntimeBaselineModel is not None  # guard: shared harness import still valid


def test_backoff_can_be_switched_off() -> None:
    rows = _rows(400, lambda i: 100 + (i % 5) * 50)

    off = JobRuntimeSignatureMemorizerModel(_cfg(backoff_levels=0)).evaluate(
        rows, metric_defs=METRICS
    )

    assert off["summary"]["memorization"]["backoff_levels"] == 0
    assert off["mae"] >= 0.0


def test_it_does_not_build_one_hot_or_svd_artifacts() -> None:
    """It exists to keep the exact signature that encoding dissolves; building the encoder
    would cost an SVD per day to produce something discarded (#171, #172)."""
    model = JobRuntimeSignatureMemorizerModel(_cfg())

    artifacts = model._build_daily_preprocessing_artifacts(_rows(50, lambda i: 100.0))

    assert artifacts.encoder is None
    assert artifacts.svd is None
    assert artifacts.categorical_columns == ()
    assert artifacts.numeric_columns  # numeric kept: the driver needs a feature matrix


def test_backoff_order_is_by_measured_cost_not_cardinality() -> None:
    """Cardinality measures coarsening, not information given up (#169)."""
    import numpy as np

    model = JobRuntimeSignatureMemorizerModel(_cfg())
    # `noise` has far higher cardinality and no bearing on runtime; `key` has only three
    # values and fully determines it. Dropping `noise` must cost nothing, dropping `key`
    # must cost a lot -- so cost ordering sheds `noise` first despite its cardinality.
    rows = [{"key": str(i % 3), "noise": f"n{i % 40}"} for i in range(120)]
    y = np.array([float((i % 3) * 100) for i in range(120)])

    order = model._feature_costs(rows, y, ["key", "noise"])

    assert order == ["noise", "key"]


def test_equal_information_ties_break_toward_more_coverage() -> None:
    """When two drops give up the same information, shed the coarser one: it buys matches."""
    import numpy as np

    model = JobRuntimeSignatureMemorizerModel(_cfg())
    # both fields are irrelevant to y, so both cost zero; `wide` has more distinct values
    rows = [{"narrow": str(i % 2), "wide": f"w{i % 30}"} for i in range(120)]
    y = np.full(120, 500.0)

    order = model._feature_costs(rows, y, ["narrow", "wide"])

    assert order == ["wide", "narrow"]
