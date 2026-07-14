"""
Unit tests for registry snapshot loading and filtering/search.
"""

from __future__ import annotations

import pytest

from hpc_oda_commons.kernel.validate import SchemaValidationError, validate_json
from hpc_oda_commons.registry.index import RegistryIndex
from hpc_oda_commons.registry.models import RegistryEntry
from hpc_oda_commons.registry.snapshot import load_registry_snapshot

pytest.importorskip("typer")
from hpc_oda_commons.qst.commands.browse import browse
from hpc_oda_commons.qst.commands.info import info


def test_snapshot_loads_expected_entries() -> None:
    snapshot = load_registry_snapshot()
    ids = {entry.id for entry in snapshot.entries}
    assert "adapter.slurmctld" in ids
    assert "model.job_runtime_baseline" in ids
    assert "model.job_runtime_xgboost" in ids
    assert "recipe.job_runtime.baseline_tiny" in ids
    assert "recipe.job_runtime.xgb_hourly_recent" in ids


def test_index_filters_by_tag_and_source() -> None:
    snapshot = load_registry_snapshot()
    index = RegistryIndex.from_entries(snapshot.entries)

    job_runtime = index.filter(tag="job-runtime-prediction")
    job_runtime_ids = {entry.id for entry in job_runtime}
    assert "adapter.slurmctld" in job_runtime_ids
    assert "model.job_runtime_baseline" in job_runtime_ids
    assert "model.job_runtime_xgboost" in job_runtime_ids
    assert "recipe.job_runtime.baseline_tiny" in job_runtime_ids
    assert "recipe.job_runtime.xgb_hourly_recent" in job_runtime_ids

    slurm = index.filter(source="slurmctld")
    slurm_ids = {entry.id for entry in slurm}
    # The v0.1 slurm-sourced adapter/model/recipe entries are all present. Dataset
    # entries carry no `supported_sources` (a dataset isn't a source), so they are
    # intentionally excluded from the source filter even when tagged job-runtime.
    slurm_sourced = {
        "adapter.slurmctld",
        "model.job_runtime_baseline",
        "model.job_runtime_xgboost",
        "recipe.job_runtime.baseline_tiny",
        "recipe.job_runtime.xgb_hourly_recent",
    }
    assert slurm_sourced.issubset(slurm_ids)


def test_index_filters_by_entry_type() -> None:
    snapshot = load_registry_snapshot()
    index = RegistryIndex.from_entries(snapshot.entries)

    models = index.filter(entry_type="model")
    assert [entry.id for entry in models] == [
        "model.job_runtime_baseline",
        "model.job_runtime_xgboost",
        "model.job_runtime_tfidf_knn",
        "model.job_runtime_embedding_knn",
        "model.job_runtime_random_forest",
        "model.job_runtime_mlp",
        "model.job_power_uopc",
    ]


def test_browse_command_outputs_entries(capsys: pytest.CaptureFixture[str]) -> None:
    browse(
        tag="job-runtime-prediction",
        entry_type=None,
        source=None,
        input_schema=None,
        output_schema=None,
        snapshot=None,
    )
    captured = capsys.readouterr().out
    assert "adapter.slurmctld" in captured
    assert "model.job_runtime_baseline" in captured
    assert "model.job_runtime_xgboost" in captured


def test_info_command_outputs_details(capsys: pytest.CaptureFixture[str]) -> None:
    info("model.job_runtime_baseline", snapshot=None)
    captured = capsys.readouterr().out
    assert "Job Runtime Baseline" in captured


def test_dataset_entry_type_supported() -> None:
    entry = RegistryEntry.from_dict(
        {
            "id": "dataset.job_runtime.example",
            "entry_type": "dataset",
            "name": "Example Dataset",
            "version": "0.1.0",
            "description": "An example registered dataset.",
            "problem_domain": ["job-runtime-prediction"],
            "output_schema_version": "oda.job.v0.2.0",
            "reference": {
                "kind": "path",
                "path": "hpc_oda_commons/datasets/descriptors/example.yml",
            },
        }
    )
    assert entry.entry_type == "dataset"
    index = RegistryIndex.from_entries([entry])
    assert [e.id for e in index.filter(entry_type="dataset")] == ["dataset.job_runtime.example"]


def test_browse_accepts_dataset_type() -> None:
    # No dataset entries in the bundled snapshot yet; --type dataset must be accepted
    # (not rejected as invalid) and simply match nothing.
    browse(
        tag=None,
        entry_type="dataset",
        source=None,
        input_schema=None,
        output_schema=None,
        snapshot=None,
    )


def _snapshot_with_dataset(extra: dict) -> dict:
    entry = {
        "id": "dataset.job_runtime.example",
        "entry_type": "dataset",
        "name": "Example Dataset",
        "version": "0.1.0",
        "description": "An example registered dataset.",
        "problem_domain": ["job-runtime-prediction"],
    }
    entry.update(extra)
    return {
        "schema_version": "oda.registry.v0.2.0",
        "generated_at": "2026-07-02T00:00:00Z",
        "entries": [entry],
    }


def test_registry_schema_v0_2_0_accepts_dataset_entry() -> None:
    payload = _snapshot_with_dataset(
        {
            "output_schema_version": "oda.job.v0.2.0",
            "reference": {
                "kind": "path",
                "path": "hpc_oda_commons/datasets/descriptors/example.yml",
            },
        }
    )
    validate_json(payload, "oda.registry.v0.2.0")


def test_registry_schema_v0_2_0_dataset_requires_reference() -> None:
    payload = _snapshot_with_dataset({"output_schema_version": "oda.job.v0.2.0"})
    with pytest.raises(SchemaValidationError):
        validate_json(payload, "oda.registry.v0.2.0")
