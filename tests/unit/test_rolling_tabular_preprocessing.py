from __future__ import annotations

import json
from pathlib import Path

from hpc_oda_commons.models.rolling_tabular.preprocessing import (
    analyze_one_hot_encoding,
    build_preprocessing_diagnostics,
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
