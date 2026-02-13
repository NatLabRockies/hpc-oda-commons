"""
Unit tests for registry snapshot loading and filtering/search.
"""

from __future__ import annotations

import pytest

from hpc_oda_commons.registry.index import RegistryIndex
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
    assert slurm_ids == job_runtime_ids


def test_index_filters_by_entry_type() -> None:
    snapshot = load_registry_snapshot()
    index = RegistryIndex.from_entries(snapshot.entries)

    models = index.filter(entry_type="model")
    assert [entry.id for entry in models] == [
        "model.job_runtime_baseline",
        "model.job_runtime_xgboost",
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
