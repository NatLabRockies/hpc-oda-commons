from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from scipy.linalg import LinAlgError
from sklearn.decomposition import TruncatedSVD

from hpc_oda_commons.models.job_runtime_xgboost.model import JobRuntimeXGBoostModel
from hpc_oda_commons.models.rolling_tabular.preprocessing import (
    _SVD_N_OVERSAMPLES,
    analyze_one_hot_encoding,
    build_preprocessing_diagnostics,
    fit_truncated_svd,
    profile_categorical_features,
    select_one_hot_config,
    select_svd_components,
    write_preprocessing_diagnostics,
)


def _sample_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for i in range(240):
        row: dict[str, object] = {
            "job_id": i,
            "user": f"user_{i % 120}",
            "account": f"acct_{i % 8}",
            "partition": "debug" if i % 2 == 0 else "compute",
            "qos": "high" if i % 7 == 0 else "normal",
            "state": "FAILED" if i % 11 == 0 else "COMPLETED",
            "runtime_seconds": float(30 + (i % 300)),
        }
        if i % 17 == 0:
            row["user"] = None
        rows.append(row)
    return rows


def test_profile_categorical_features_basic() -> None:
    rows = _sample_rows()
    profiles = profile_categorical_features(rows)

    for required in ("user", "account", "partition", "qos", "state"):
        assert required in profiles

    assert profiles["user"].cardinality > profiles["account"].cardinality
    assert profiles["user"].null_rate > 0.0
    assert profiles["partition"].cardinality == 2


def test_select_one_hot_config_controls_estimated_width() -> None:
    rows = _sample_rows()
    profiles = profile_categorical_features(rows)
    config = select_one_hot_config(
        profiles,
        infrequent_fraction=0.02,
        min_frequency_floor=2,
        target_max_one_hot_width=40,
    )

    assert config.min_frequency_count >= 2
    assert config.estimated_width <= 40
    assert config.columns


def test_select_svd_components_for_target_coverage() -> None:
    rows = _sample_rows()
    profiles = profile_categorical_features(rows)
    config = select_one_hot_config(
        profiles,
        infrequent_fraction=0.02,
        min_frequency_floor=2,
        target_max_one_hot_width=128,
    )
    one_hot_analysis, encoded = analyze_one_hot_encoding(rows, config)
    assert one_hot_analysis.encoded_feature_count > 0

    plan = select_svd_components(
        encoded,
        target_coverage=0.90,
        max_svd_components=64,
        random_state=7,
    )

    assert plan.method == "truncated_svd"
    assert plan.evaluated_components > 0
    assert 1 <= plan.selected_components <= plan.evaluated_components
    assert plan.achieved_coverage >= 0.90 or plan.selected_components == plan.evaluated_components


def test_svd_oversamples_beyond_the_sklearn_default() -> None:
    """The default conditioning fails outright on some BLAS builds (#159).

    The instability is not portably reproducible -- it depends on the compiled BLAS -- so
    this pins the request rather than the symptom: if the default ever comes back, a
    130k-row one-hot matrix starts raising ``LinAlgError: SVD did not converge`` on the
    cluster again and three models lose the affected dataset.
    """
    rows = _sample_rows()
    profiles = profile_categorical_features(rows)
    config = select_one_hot_config(
        profiles,
        infrequent_fraction=0.02,
        min_frequency_floor=2,
        target_max_one_hot_width=128,
    )
    _analysis, encoded = analyze_one_hot_encoding(rows, config)

    with patch("sklearn.decomposition.TruncatedSVD", wraps=TruncatedSVD) as spy:
        select_svd_components(encoded, target_coverage=0.90, max_svd_components=64)

    assert spy.call_args.kwargs["n_oversamples"] == _SVD_N_OVERSAMPLES
    assert _SVD_N_OVERSAMPLES > 10  # sklearn's default, which is what fails


def test_daily_artifacts_fit_the_svd_with_the_same_conditioning() -> None:
    """The component count and the fitted transform must agree on the numerics (#159)."""
    rows = _sample_rows()
    model = JobRuntimeXGBoostModel()
    artifacts = model._build_daily_preprocessing_artifacts(rows)

    assert artifacts.svd is not None
    assert artifacts.svd.n_oversamples == _SVD_N_OVERSAMPLES


def test_svd_parameters_are_accepted_by_the_installed_sklearn() -> None:
    """Guard the #162 class of bug: a value this sklearn's constraints reject.

    ``power_iteration_normalizer="QR"`` passed on a developer machine and broke CI, because
    older supported sklearn releases carry an upstream typo in the constraint. Constructing
    and fitting through the real code path is what catches that, on whatever version is
    installed.
    """
    rows = _sample_rows()
    profiles = profile_categorical_features(rows)
    config = select_one_hot_config(
        profiles,
        infrequent_fraction=0.02,
        min_frequency_floor=2,
        target_max_one_hot_width=128,
    )
    _analysis, encoded = analyze_one_hot_encoding(rows, config)

    plan = select_svd_components(encoded, target_coverage=0.90, max_svd_components=64)

    assert plan.selected_components > 0


def test_build_and_write_preprocessing_diagnostics(tmp_path: Path) -> None:
    rows = _sample_rows()
    payload = build_preprocessing_diagnostics(
        rows,
        explained_variance_target=0.92,
        infrequent_fraction=0.02,
        min_frequency_floor=2,
        target_max_one_hot_width=128,
        max_svd_components=64,
        random_state=9,
    )

    assert payload["analysis_version"] == "rolling_tabular.preprocessing.v0.1.0"
    assert payload["row_count"] == len(rows)
    assert payload["categorical_profiles"]
    assert payload["one_hot_config"]["min_frequency_count"] >= 2
    assert payload["one_hot_analysis"]["encoded_feature_count"] > 0
    assert payload["dimensionality_reduction"]["selected_components"] >= 1

    out_path = tmp_path / "diagnostics" / "xgb_preprocessing.json"
    write_preprocessing_diagnostics(out_path, payload)
    loaded = json.loads(out_path.read_text(encoding="utf-8"))

    assert loaded["analysis_version"] == payload["analysis_version"]
    assert (
        loaded["one_hot_config"]["min_frequency_count"]
        == payload["one_hot_config"]["min_frequency_count"]
    )


# --- solver escalation (#185) ---------------------------------------------------------


class _FlakySVD:
    """A TruncatedSVD stand-in that fails to converge until a given rung is reached."""

    calls: list[dict] = []

    def __init__(self, fail_until: int):
        self.fail_until = fail_until

    def __call__(self, **kwargs):
        _FlakySVD.calls.append(kwargs)
        outer = self

        class _Fitted:
            explained_variance_ratio_ = np.array([0.7, 0.3])

            def fit(self, _matrix):
                if len(_FlakySVD.calls) <= outer.fail_until:
                    raise LinAlgError("SVD did not converge")
                return self

        return _Fitted()


def _encoded_fixture():
    rows = _sample_rows()
    profiles = profile_categorical_features(rows)
    config = select_one_hot_config(
        profiles, infrequent_fraction=0.02, min_frequency_floor=2, target_max_one_hot_width=128
    )
    return analyze_one_hot_encoding(rows, config)[1]


def test_a_convergence_failure_escalates_instead_of_killing_the_run() -> None:
    """The failure is not a property of the matrix, so no static setting can prevent it (#185).

    lassen's failing case ran clean three times over all 30 training days on a debug node,
    with the same code and data that failed in production.
    """
    _FlakySVD.calls = []
    encoded = _encoded_fixture()

    with patch(
        "hpc_oda_commons.models.rolling_tabular.preprocessing._require_sklearn",
        return_value=(None, _FlakySVD(fail_until=1)),
    ):
        svd, solver = fit_truncated_svd(encoded, 2, random_state=42)

    assert svd is not None
    assert solver == "randomized_oversampled"  # escalated one rung
    assert _FlakySVD.calls[0]["n_oversamples"] == _SVD_N_OVERSAMPLES
    assert _FlakySVD.calls[1]["n_oversamples"] == 100


def test_escalation_reaches_a_different_algorithm_when_needed() -> None:
    _FlakySVD.calls = []
    encoded = _encoded_fixture()

    with patch(
        "hpc_oda_commons.models.rolling_tabular.preprocessing._require_sklearn",
        return_value=(None, _FlakySVD(fail_until=2)),
    ):
        _svd, solver = fit_truncated_svd(encoded, 2, random_state=42)

    assert solver == "arpack"
    assert _FlakySVD.calls[-1]["algorithm"] == "arpack"


def test_a_genuinely_broken_input_still_raises() -> None:
    """Escalation must not paper over an input that no solver can handle."""
    _FlakySVD.calls = []
    encoded = _encoded_fixture()

    with (
        patch(
            "hpc_oda_commons.models.rolling_tabular.preprocessing._require_sklearn",
            return_value=(None, _FlakySVD(fail_until=99)),
        ),
        pytest.raises(LinAlgError),
    ):
        fit_truncated_svd(encoded, 2, random_state=42)


def test_the_happy_path_does_not_escalate_and_says_so() -> None:
    plan = select_svd_components(_encoded_fixture(), target_coverage=0.90, max_svd_components=64)

    assert plan.solver == "randomized"
    assert plan.to_dict()["solver"] == "randomized"
