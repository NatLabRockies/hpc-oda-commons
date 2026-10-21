"""The UoPC paper protocol's variants (#222): divide by requested nodes, and drop the jobs
whose allocated count is padded far past their request, from history and test alike."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from hpc_oda_commons.benchmark.recipes import load_recipe, validate_recipe
from hpc_oda_commons.kernel.validate import SchemaValidationError
from hpc_oda_commons.models.uopc.model import UopcModel

_START = "2024-02-01"


def _rows(n: int = 120, users: int = 3) -> list[dict]:
    """Every fifth job is padded 48x (1 node requested, 48 allocated), as on F-DATA."""
    rng = np.random.default_rng(11)
    base = datetime(2024, 1, 15, tzinfo=timezone.utc)
    rows = []
    for idx in range(n):
        submit = base + timedelta(hours=8 * idx)
        padded = idx % 5 == 0
        requested = 1 if padded else int(rng.integers(1, 4))
        rows.append(
            {
                "job_id": idx,
                "user": f"u{idx % users}",
                "submit_time": submit,
                "end_time": submit + timedelta(hours=float(rng.integers(1, 30))),
                "avgpcon": float(rng.integers(80, 300)),
                "maxpcon": float(rng.integers(300, 600)),
                "num_nodes_req": requested,
                "num_nodes_alloc": 48 if padded else requested + int(rng.integers(0, 2)),
                "num_cores_req": 48 * requested,
                "freq_req": 2000,
                "embedding": rng.random(4).tolist(),
            }
        )
    return rows


def test_requested_node_count_divides_by_requested_nodes() -> None:
    rows = _rows()
    by_id = {r["job_id"]: r for r in rows}
    prepared = UopcModel()._prepare_paper_data(rows, test_start=_START, node_count="requested")

    expected = [by_id[j]["avgpcon"] / by_id[j]["num_nodes_req"] for j in prepared.job_id_arr]
    assert prepared.avg_target_arr.tolist() == pytest.approx(expected)
    assert prepared.node_count == "requested"


def test_requested_node_count_is_the_default() -> None:
    """Allocated counts can be padded, so the default is what we can defend (#228)."""
    rows = _rows()
    by_id = {r["job_id"]: r for r in rows}
    prepared = UopcModel()._prepare_paper_data(rows, test_start=_START)
    assert prepared.node_count == "requested"
    expected = [by_id[j]["maxpcon"] / by_id[j]["num_nodes_req"] for j in prepared.job_id_arr]
    assert prepared.max_target_arr.tolist() == pytest.approx(expected)


def test_allocated_node_count_divides_by_allocated_nodes() -> None:
    rows = _rows()
    by_id = {r["job_id"]: r for r in rows}
    prepared = UopcModel()._prepare_paper_data(rows, test_start=_START, node_count="allocated")

    expected = [by_id[j]["maxpcon"] / by_id[j]["num_nodes_alloc"] for j in prepared.job_id_arr]
    assert prepared.max_target_arr.tolist() == pytest.approx(expected)


def test_max_alloc_ratio_drops_padded_jobs_from_history_and_test() -> None:
    rows = _rows()
    padded_ids = {r["job_id"] for r in rows if r["num_nodes_alloc"] / r["num_nodes_req"] > 12}
    prepared = UopcModel()._prepare_paper_data(rows, test_start=_START, max_alloc_ratio=12)

    kept = set(prepared.job_id_arr.tolist())
    assert padded_ids and not kept & padded_ids
    assert len(kept) == len(rows) - len(padded_ids)
    assert prepared.rows_dropped_alloc_ratio == len(padded_ids)
    # Dropped jobs are gone from every user's history, not just from the scored set.
    history_ids = {int(prepared.job_id_arr[i]) for idx in prepared.user_rows.values() for i in idx}
    assert not history_ids & padded_ids


def test_variants_reach_both_paper_modes_summaries() -> None:
    model = UopcModel()
    rows = _rows()
    variant = {"node_count": "requested", "max_alloc_ratio": 12.0}
    reproduction = model.evaluate_paper_reproduction(
        rows, test_start=_START, theta=10, k=3, **variant
    )
    sweep = model.evaluate_paper_sensitivity(
        rows, test_start=_START, theta_values=(10,), k_values=(3,), **variant
    )

    for summary in (reproduction["summary"], sweep["summary"]):
        assert summary["node_count"] == "requested"
        assert summary["max_alloc_ratio"] == 12.0
        assert summary["rows_dropped_alloc_ratio"] == 24
        assert summary["targets"] == ["avgpcon/num_nodes_req", "maxpcon/num_nodes_req"]


@pytest.mark.parametrize(
    ("node_count", "max_alloc_ratio"), [("used", None), ("allocated", 0.0), ("allocated", -1.0)]
)
def test_bad_variant_values_are_errors(node_count: str, max_alloc_ratio: float | None) -> None:
    with pytest.raises(ValueError):
        UopcModel()._prepare_paper_data(
            _rows(), test_start=_START, node_count=node_count, max_alloc_ratio=max_alloc_ratio
        )


def _cutoff_recipe(**split: object) -> dict:
    return {
        "recipe_id": "recipe.job_power.uopc_variant_test",
        "problem_domain": ["job-power-prediction"],
        "schema_version": "oda.job.v0.2.0",
        "dataset": {"id": "fdata_fugaku_uopc", "table_path": "data.parquet"},
        "model": {"id": "model.uopc", "version": "0.1.0"},
        "metrics": [
            {"name": "mae", "target": "avgpcon_per_node"},
            {"name": "rmse", "target": "avgpcon_per_node"},
        ],
        "split": {"method": "cutoff", "test_start": _START, **split},
    }


def test_recipe_accepts_the_variants_under_cutoff() -> None:
    validate_recipe(_cutoff_recipe(node_count="requested", max_alloc_ratio=12))


@pytest.mark.parametrize("split", [{"node_count": "used"}, {"max_alloc_ratio": 0}])
def test_recipe_rejects_bad_variant_values(split: dict) -> None:
    with pytest.raises(SchemaValidationError):
        validate_recipe(_cutoff_recipe(**split))


@pytest.mark.parametrize("key", ["node_count", "max_alloc_ratio"])
def test_variant_keys_are_errors_outside_cutoff(key: str) -> None:
    payload = _cutoff_recipe()
    payload["split"] = {
        "method": "rolling",
        "n_windows": 3,
        key: "requested" if key == "node_count" else 12,
    }
    with pytest.raises(SchemaValidationError, match="only apply to split.method: cutoff"):
        validate_recipe(payload)


def _bundled_split(name: str) -> dict:
    from pathlib import Path

    import hpc_oda_commons

    root = Path(hpc_oda_commons.__file__).parent / "recipes" / "job-power"
    return load_recipe(root / name)["split"]


def test_headline_reproduction_uses_our_settings() -> None:
    """Per requested node, balanced features, k = 20, all jobs (#228)."""
    split = _bundled_split("uopc_paper_reproduction.yml")
    assert split["k"] == 20
    assert split["node_count"] == "requested"
    assert split["uopc_features"] == "balanced"
    assert "max_alloc_ratio" not in split


@pytest.mark.parametrize(
    ("recipe", "expected"),
    [
        (
            "uopc_paper_reproduction_paper_setup.yml",
            {"node_count": "allocated", "uopc_features": "zscore", "k": 5, "predictor": "vote"},
        ),
        (
            "uopc_paper_reproduction_unpadded.yml",
            {
                "node_count": "allocated",
                "uopc_features": "zscore",
                "k": 5,
                "predictor": "vote",
                "max_alloc_ratio": 12,
            },
        ),
    ],
)
def test_paper_comparison_recipes_differ_from_the_headline_only_as_stated(
    recipe: str, expected: dict
) -> None:
    assert _bundled_split(recipe) == {**_bundled_split("uopc_paper_reproduction.yml"), **expected}
