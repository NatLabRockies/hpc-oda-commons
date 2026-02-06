from __future__ import annotations

import pytest

from hpc_oda_commons.models.job_runtime_baseline.model import JobRuntimeBaselineModel


def test_predict_before_fit_raises() -> None:
    model = JobRuntimeBaselineModel()
    with pytest.raises(RuntimeError):
        model.predict([{"runtime_seconds": 10.0}])


def test_fit_and_predict_are_deterministic() -> None:
    rows = [
        {"runtime_seconds": 10.0},
        {"runtime_seconds": 20.0},
        {"runtime_seconds": None},
    ]
    model = JobRuntimeBaselineModel()
    model.fit(rows)
    preds = model.predict(rows)
    assert preds == [15.0, 15.0, 15.0]
