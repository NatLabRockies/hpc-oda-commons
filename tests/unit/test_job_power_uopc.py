from __future__ import annotations

import math
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hpc_oda_commons.models.job_power_uopc.model import (
    JobPowerUopcModel,
    _classifier_prediction_from_neighbor_targets,
    _nearest_neighbor_indices_and_distances,
    _regressor_prediction_from_neighbor_targets,
)


def _write_uopc_dataset(path) -> None:
    rows = []
    for idx in range(30):
        user = "alice" if idx < 20 else "bob"
        rows.append(
            {
                "usr": user,
                "jnam": f"job_{idx % 3}",
                "cnumr": 64 + (idx % 4) * 8,
                "nnumr": 1 + (idx % 2),
                "edt": f"2024-04-01T{idx % 24:02d}:00:00+09:00",
                "maxpcon": 1000.0 + idx * 10.0 + (idx % 3) * 5.0,
            }
        )
    pq.write_table(pa.Table.from_pylist(rows), path)


def test_uopc_fixed_predicts_with_user_history(tmp_path) -> None:
    table_path = tmp_path / "uopc.parquet"
    _write_uopc_dataset(table_path)
    rows = pq.read_table(table_path).to_pylist()

    result = JobPowerUopcModel().evaluate_fixed(
        rows,
        split={"train_fraction": 0.7, "seed": 1},
        metric_defs=[
            {"name": "mae", "target": "maxpcon"},
            {"name": "rmse", "target": "maxpcon"},
        ],
    )

    assert math.isfinite(result["mae"]) and result["mae"] >= 0.0
    assert math.isfinite(result["rmse"]) and result["rmse"] >= 0.0
    assert result["summary"]["rows_scored"] > 0
    assert result["summary"]["theta"] == 50
    assert result["summary"]["k"] == 5


def test_uopc_requires_finite_target() -> None:
    rows = [
        {"usr": "alice", "jnam": "x", "cnumr": 1, "nnumr": 1, "edt": "2024-04-01T00:00:00+09:00"}
    ]
    with pytest.raises(ValueError, match="No rows with a finite target"):
        JobPowerUopcModel().evaluate_fixed(rows, split={"train_fraction": 0.8, "seed": 1})


def test_uopc_datetime_end_time_matches_string_representation() -> None:
    """v0.2 canonical end_time is a tz-aware datetime; the _end_time_sort_key
    datetime fast-path must order (and therefore score) identically to the
    equivalent ISO-string representation."""
    from datetime import datetime, timezone

    base = []
    for idx in range(30):
        dt = datetime(2024, 4, 1, idx % 24, (idx * 7) % 60, tzinfo=timezone.utc)
        base.append(
            {
                "usr": "alice" if idx < 20 else "bob",
                "jnam": f"job_{idx % 3}",
                "cnumr": 64 + (idx % 4) * 8,
                "nnumr": 1 + (idx % 2),
                "maxpcon": 1000.0 + idx * 10.0 + (idx % 3) * 5.0,
                "_dt": dt,
            }
        )
    dt_rows = [{k: v for k, v in r.items() if k != "_dt"} | {"edt": r["_dt"]} for r in base]
    str_rows = [
        {k: v for k, v in r.items() if k != "_dt"}
        | {"edt": r["_dt"].isoformat().replace("+00:00", "Z")}
        for r in base
    ]
    md = [{"name": "mae", "target": "maxpcon"}, {"name": "rmse", "target": "maxpcon"}]
    split = {"train_fraction": 0.7, "seed": 1}

    r_dt = JobPowerUopcModel().evaluate_fixed(dt_rows, split=split, metric_defs=md)
    r_str = JobPowerUopcModel().evaluate_fixed(str_rows, split=split, metric_defs=md)

    assert r_dt["summary"]["rows_scored"] > 0
    assert r_dt["mae"] == r_str["mae"]
    assert r_dt["rmse"] == r_str["rmse"]
    assert r_dt["summary"]["rows_scored"] == r_str["summary"]["rows_scored"]


def test_uopc_paper_reproduction_smoke() -> None:
    """Paper-reproduction mode uses date split, per-node target, and user history."""
    rows = []

    for idx in range(20):
        month = 1 if idx < 10 else 2
        day = (idx % 10) + 1

        rows.append(
            {
                "user": "alice",
                "submit_time": f"2024-{month:02d}-{day:02d}T12:00:00Z",
                "end_time": f"2024-{month:02d}-{day:02d}T11:00:00Z",
                "avgpcon": 100.0 + idx,
                "maxpcon": 120.0 + idx,
                "nnuma": 2,
                "num_cores_req": 64 + idx,
                "num_nodes_req": 2,
                "freq_req": 2000,
                "embedding": [float(idx), float(idx % 3)],
            }
        )

    model = JobPowerUopcModel()

    result = model.evaluate_paper_reproduction(
        rows,
        test_start="2024-02-01",
        theta=5,
        k=2,
        metric_defs=[
            {"name": "mae", "target": "avgpcon_per_node"},
            {"name": "rmse", "target": "avgpcon_per_node"},
            {"name": "mape", "target": "avgpcon_per_node"},
            {"name": "r2", "target": "avgpcon_per_node"},
        ],
    )

    assert result["summary"]["rows_test"] == 10
    assert result["summary"]["rows_scored"] > 0
    assert result["summary"]["theta"] == 5
    assert result["summary"]["k"] == 2
    assert result["summary"]["targets"] == [
        "avgpcon/nnuma",
        "maxpcon/nnuma",
    ]

    assert result["summary"]["predictor"] == "KNeighborsClassifier"

    for target in ("avgpcon_per_node", "maxpcon_per_node"):
        for metric in ("mae", "rmse", "mape", "r2"):
            assert math.isfinite(result[target][metric])

    for baseline in ("per_user_mean", "global_mean"):
        assert baseline in result["baselines"]

        for target in ("avgpcon_per_node", "maxpcon_per_node"):
            for metric in ("mae", "rmse", "mape", "r2"):
                assert math.isfinite(
                    result["baselines"][baseline][target][metric]
                )


def test_classifier_prediction_from_neighbor_targets_matches_knn() -> None:
    from sklearn.neighbors import KNeighborsClassifier

    x_train = np.asarray([[0.0], [1.0], [2.0], [3.0], [4.0]])
    targets = np.asarray([10.2, 10.4, 20.1, 10.3, 30.2])
    query = np.asarray([[0.5]])

    model = KNeighborsClassifier(n_neighbors=5)
    model.fit(x_train, np.rint(targets).astype(np.int64))

    _, indices = model.kneighbors(query, n_neighbors=5)

    expected = float(model.predict(query)[0])
    actual = _classifier_prediction_from_neighbor_targets(
        targets[indices[0]],
        5,
    )

    assert actual == expected


def test_classifier_prediction_neighbor_tie_matches_knn() -> None:
    from sklearn.neighbors import KNeighborsClassifier

    x_train = np.asarray([[0.0], [1.0], [2.0], [3.0]])
    targets = np.asarray([10.0, 20.0, 10.0, 20.0])
    query = np.asarray([[1.5]])

    model = KNeighborsClassifier(n_neighbors=4)
    model.fit(x_train, targets.astype(np.int64))

    _, indices = model.kneighbors(query, n_neighbors=4)

    expected = float(model.predict(query)[0])
    actual = _classifier_prediction_from_neighbor_targets(
        targets[indices[0]],
        4,
    )

    assert actual == expected


def test_regressor_prediction_from_neighbor_targets_matches_knn() -> None:
    from sklearn.neighbors import KNeighborsRegressor

    x_train = np.asarray([[0.0], [1.0], [2.0], [3.0], [4.0]])
    targets = np.asarray([10.0, 20.0, 30.0, 40.0, 50.0])
    query = np.asarray([[1.5]])

    model = KNeighborsRegressor(n_neighbors=5)
    model.fit(x_train, targets)

    _, indices = model.kneighbors(query, n_neighbors=5)

    expected = float(model.predict(query)[0])
    actual = _regressor_prediction_from_neighbor_targets(
        targets[indices[0]],
        5,
    )

    assert actual == pytest.approx(expected)


def test_nearest_neighbor_retrieval_matches_sklearn() -> None:
    from sklearn.neighbors import KNeighborsClassifier

    x_train = np.asarray(
        [[0.0], [1.0], [2.0], [3.0], [4.0]],
        dtype=np.float64,
    )
    query = np.asarray([[1.2]], dtype=np.float64)

    reference = KNeighborsClassifier(n_neighbors=3)
    reference.fit(
        x_train,
        np.asarray([10, 20, 30, 40, 50]),
    )

    expected_distances, expected_indices = reference.kneighbors(
        query,
        n_neighbors=3,
        return_distance=True,
    )

    actual_indices, actual_distances = (
        _nearest_neighbor_indices_and_distances(
            x_train,
            query,
            max_neighbors=3,
        )
    )

    assert np.array_equal(actual_indices, expected_indices[0])
    assert np.allclose(actual_distances, expected_distances[0])


def test_nearest_neighbor_retrieval_caps_at_available_history() -> None:
    x_train = np.asarray(
        [[0.0], [1.0], [2.0]],
        dtype=np.float64,
    )
    query = np.asarray([[1.1]], dtype=np.float64)

    indices, distances = _nearest_neighbor_indices_and_distances(
        x_train,
        query,
        max_neighbors=50,
    )

    assert len(indices) == 3
    assert len(distances) == 3


def test_uopc_paper_sensitivity_matches_reproduction() -> None:
    rows = []

    for idx in range(20):
        month = 1 if idx < 10 else 2
        day = (idx % 10) + 1

        rows.append(
            {
                "user": "alice",
                "submit_time": f"2024-{month:02d}-{day:02d}T12:00:00Z",
                "end_time": f"2024-{month:02d}-{day:02d}T11:00:00Z",
                "avgpcon": 100.0 + idx,
                "maxpcon": 120.0 + idx,
                "nnuma": 2,
                "num_cores_req": 64 + idx,
                "num_nodes_req": 2,
                "freq_req": 2000,
                "embedding": [float(idx), float(idx % 3)],
            }
        )

    metric_defs = [
        {"name": "mae", "target": "avgpcon_per_node"},
        {"name": "rmse", "target": "avgpcon_per_node"},
        {"name": "mape", "target": "avgpcon_per_node"},
        {"name": "r2", "target": "avgpcon_per_node"},
    ]

    model = JobPowerUopcModel()

    reproduction = model.evaluate_paper_reproduction(
        rows,
        test_start="2024-02-01",
        theta=5,
        k=2,
        metric_defs=metric_defs,
    )

    sensitivity = model.evaluate_paper_sensitivity(
        rows,
        test_start="2024-02-01",
        theta_values=(5,),
        k_values=(2,),
        metric_defs=metric_defs,
    )

    classifier = sensitivity["results"]["5"]["2"]["classifier"]

    assert classifier["rows_scored"] == reproduction["summary"]["rows_scored"]

    for target in ("avgpcon_per_node", "maxpcon_per_node"):
        for metric in ("mae", "rmse", "mape", "r2"):
            assert classifier[target][metric] == pytest.approx(
                reproduction[target][metric]
            )

def test_prepare_paper_data_matches_reproduction_protocol() -> None:
    rows = []

    for idx in range(20):
        month = 1 if idx < 10 else 2
        day = (idx % 10) + 1

        rows.append(
            {
                "user": "alice",
                "submit_time": f"2024-{month:02d}-{day:02d}T12:00:00Z",
                "end_time": f"2024-{month:02d}-{day:02d}T11:00:00Z",
                "avgpcon": 100.0 + idx,
                "maxpcon": 120.0 + idx,
                "nnuma": 2,
                "num_cores_req": 64 + idx,
                "num_nodes_req": 2,
                "freq_req": 2000,
                "embedding": [float(idx), float(idx % 3)],
            }
        )

    prepared = JobPowerUopcModel()._prepare_paper_data(
        rows,
        test_start="2024-02-01",
    )

    assert len(prepared.user_arr) == 20
    assert len(prepared.submit_arr) == 20
    assert len(prepared.end_arr) == 20
    assert len(prepared.avg_target_arr) == 20
    assert len(prepared.max_target_arr) == 20

    # 2 embedding dimensions + 3 standardized numeric features.
    assert prepared.features.shape == (20, 5)

    # February jobs are the test set.
    assert len(prepared.test_idx) == 10

    # All rows belong to the same user.
    assert set(prepared.user_rows) == {"alice"}
    assert len(prepared.user_rows["alice"]) == 20

    # Per-node targets.
    assert prepared.avg_target_arr[0] == pytest.approx(50.0)
    assert prepared.max_target_arr[0] == pytest.approx(60.0)


def test_uopc_sensitivity_reuses_neighbors_for_multiple_k() -> None:
    rows = []

    # 30 January history jobs + 10 February test jobs.
    for idx in range(40):
        if idx < 30:
            month = 1
            day = idx + 1
        else:
            month = 2
            day = idx - 29

        rows.append(
            {
                "user": "alice",
                "submit_time": f"2024-{month:02d}-{day:02d}T12:00:00Z",
                "end_time": f"2024-{month:02d}-{day:02d}T11:00:00Z",
                "avgpcon": 100.0 + idx * 3.0,
                "maxpcon": 140.0 + idx * 4.0,
                "nnuma": 2,
                "num_cores_req": 64 + idx,
                "num_nodes_req": 2 + (idx % 3),
                "freq_req": 2000 + (idx % 4) * 100,
                "embedding": [
                    float(idx),
                    float(idx % 5),
                ],
            }
        )

    metric_defs = [
        {"name": "mae", "target": "avgpcon_per_node"},
        {"name": "rmse", "target": "avgpcon_per_node"},
        {"name": "mape", "target": "avgpcon_per_node"},
        {"name": "r2", "target": "avgpcon_per_node"},
    ]

    model = JobPowerUopcModel()

    sensitivity = model.evaluate_paper_sensitivity(
        rows,
        test_start="2024-02-01",
        theta_values=(20,),
        k_values=(5, 10, 20),
        metric_defs=metric_defs,
    )

    # Each k result from the single sensitivity call must match an
    # independent faithful reproduction run at the same theta/k.
    for k in (5, 10, 20):
        reproduction = model.evaluate_paper_reproduction(
            rows,
            test_start="2024-02-01",
            theta=20,
            k=k,
            metric_defs=metric_defs,
        )

        classifier = sensitivity["results"]["20"][str(k)]["classifier"]

        assert (
            classifier["rows_scored"]
            == reproduction["summary"]["rows_scored"]
        )

        for target in (
            "avgpcon_per_node",
            "maxpcon_per_node",
        ):
            for metric in ("mae", "rmse", "mape", "r2"):
                assert classifier[target][metric] == pytest.approx(
                    reproduction[target][metric]
                )