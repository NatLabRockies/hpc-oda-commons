from __future__ import annotations

import copy
from pathlib import Path

import pytest

from hpc_oda_commons.datasets.descriptor import (
    Descriptor,
    load_descriptor,
    validate_descriptor,
)
from hpc_oda_commons.kernel.validate import SchemaValidationError


def _valid_descriptor() -> dict:
    return {
        "dataset_id": "dataset.job_power.fdata_fugaku",
        "schema_version": "oda.dataset.v0.1.0",
        "name": "F-DATA (Fugaku Job Records)",
        "version": "1.0.0",
        "description": "Fugaku job records with per-job power for runtime and power prediction.",
        "problem_domains": ["job-runtime-prediction", "job-power-prediction"],
        "systems": ["Fugaku"],
        "providers": ["RIKEN R-CCS", "Univ. Bologna"],
        "license": {"spdx": "CC-BY-4.0", "gated": False},
        "tags": ["fugaku", "power", "parquet"],
        "size": {
            "default_bytes": 3200000000,
            "full_bytes": 480000000000,
            "rows_hint": "~24M jobs",
        },
        "source": {
            "kind": "zenodo",
            "record": "11467483",
            "resources": [
                {
                    "filename": "23_04.parquet",
                    "url": "https://zenodo.org/records/11467483/files/23_04.parquet",
                    "sha256": "a" * 64,
                    "bytes": 280000000,
                }
            ],
            "slices": {
                "default": "recent",
                "available": {
                    "recent": {"description": "most recent full year", "include": ["23_*.parquet"]},
                    "full": {"include": ["*.parquet"]},
                },
            },
        },
        "decode": {"format": "parquet", "options": {}},
        "targets": [
            {
                "schema": "oda.job.v0.2.0",
                "capabilities": [
                    {
                        "problem_domain": "job-runtime-prediction",
                        "target_column": "runtime_seconds",
                    },
                    {"problem_domain": "job-power-prediction", "target_column": "maxpcon"},
                ],
                "suitable_models": ["model.job_runtime_xgboost", "model.job_power_uopc"],
                "mapping": {
                    "job_id": {"from": "jobid", "type": "hash_identifier"},
                    "start_time": {"from": "sdt", "type": "timestamp", "format": "epoch_s"},
                    "end_time": {"from": "edt", "type": "timestamp", "format": "epoch_s"},
                    "runtime_seconds": {"from": "duration", "type": "duration", "unit": "seconds"},
                    "maxpcon": {"from": "maxpcon"},
                    "user": {"from": "usr", "type": "hash_identifier"},
                    "name": {"from": "jnam"},
                    "processors_requested": {"from": "cnumr", "type": "integer"},
                    "nodes_requested": {"from": "nnumr", "type": "integer"},
                },
                "select": ["job_id", "start_time", "end_time", "runtime_seconds", "maxpcon"],
                "filter": {"completed_only": True},
                "sample": {
                    "rows": 500000,
                    "strategy": "stratified",
                    "by": ["partition"],
                    "seed": 42,
                },
                "output": {"id": "fdata_fugaku", "path": "data/datasets/fdata_fugaku/data.parquet"},
            }
        ],
    }


def test_validate_descriptor_ok() -> None:
    validate_descriptor(_valid_descriptor())


def test_from_dict_exposes_identity_and_capabilities() -> None:
    desc = Descriptor.from_dict(_valid_descriptor())
    assert desc.dataset_id == "dataset.job_power.fdata_fugaku"
    assert desc.supports_domain("job-power-prediction")
    assert not desc.supports_domain("failure-analysis")
    assert desc.supports_model("model.job_power_uopc")
    assert not desc.supports_model("model.does_not_exist")
    caps = {(c.problem_domain, c.target_column) for c in desc.capabilities()}
    assert ("job-power-prediction", "maxpcon") in caps
    assert "maxpcon" in desc.targets[0].produced_columns


def test_missing_required_field_fails() -> None:
    payload = _valid_descriptor()
    del payload["targets"]
    with pytest.raises(SchemaValidationError):
        validate_descriptor(payload)


def test_wrong_schema_version_const_fails() -> None:
    payload = _valid_descriptor()
    payload["schema_version"] = "oda.dataset.v0.2.0"
    with pytest.raises(SchemaValidationError):
        validate_descriptor(payload)


def test_capability_target_column_must_be_produced_by_mapping() -> None:
    payload = _valid_descriptor()
    # Claim a power capability but drop maxpcon from the mapping.
    del payload["targets"][0]["mapping"]["maxpcon"]
    with pytest.raises(SchemaValidationError, match="maxpcon"):
        validate_descriptor(payload)


def test_capability_domain_must_be_declared() -> None:
    payload = _valid_descriptor()
    payload["targets"][0]["capabilities"].append(
        {"problem_domain": "anomaly-detection", "target_column": "maxpcon"}
    )
    with pytest.raises(SchemaValidationError, match="problem_domains"):
        validate_descriptor(payload)


def test_non_manual_resource_requires_url() -> None:
    payload = _valid_descriptor()
    del payload["source"]["resources"][0]["url"]
    with pytest.raises(SchemaValidationError, match="url"):
        validate_descriptor(payload)


def test_manual_source_may_omit_url() -> None:
    payload = _valid_descriptor()
    payload["source"]["kind"] = "manual"
    payload["source"]["instructions"] = "Register at the portal, then supply the file."
    del payload["source"]["resources"][0]["url"]
    del payload["source"]["slices"]  # slices reference monthly files; irrelevant here
    validate_descriptor(payload)


def test_slices_default_must_exist() -> None:
    payload = _valid_descriptor()
    payload["source"]["slices"]["default"] = "nonexistent"
    with pytest.raises(SchemaValidationError, match="slices"):
        validate_descriptor(payload)


def test_stratified_sample_requires_by() -> None:
    payload = _valid_descriptor()
    del payload["targets"][0]["sample"]["by"]
    with pytest.raises(SchemaValidationError, match="stratified"):
        validate_descriptor(payload)


def test_load_descriptor_from_file(tmp_path: Path) -> None:
    import yaml

    payload = _valid_descriptor()
    descriptor_path = tmp_path / "fdata.yml"
    descriptor_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    desc = load_descriptor(descriptor_path)
    assert desc.dataset_id == payload["dataset_id"]
    assert desc.targets[0].schema == "oda.job.v0.2.0"


def test_load_descriptor_rejects_non_mapping(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yml"
    bad.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(SchemaValidationError):
        load_descriptor(bad)


def test_valid_descriptor_deepcopy_isolation() -> None:
    # Guard: builder returns independent payloads so mutation in one test can't leak.
    a = _valid_descriptor()
    b = copy.deepcopy(_valid_descriptor())
    a["targets"][0]["mapping"].pop("maxpcon")
    assert "maxpcon" in b["targets"][0]["mapping"]
