from __future__ import annotations

from pathlib import Path

import pytest

from hpc_oda_commons.kernel.artifacts.mapping_spec import (
    new_mapping_spec,
    read_mapping_spec,
    write_mapping_spec,
)
from hpc_oda_commons.kernel.validate import SchemaValidationError


def test_mapping_spec_roundtrip(tmp_path: Path) -> None:
    payload = new_mapping_spec(
        kind="jobs_parquet",
        output_schema_version="oda.job.v0.1.0",
        fields={
            "job_id": {"source": "JobID"},
            "start_time": {"source": "Start"},
            "end_time": {"source": "End"},
            "runtime_seconds": {"derive": "end_time - start_time"},
        },
    )
    path = tmp_path / "mapping.yml"
    write_mapping_spec(path, payload, validate=True)
    loaded = read_mapping_spec(path, validate=True)
    assert loaded["schema_version"] == "oda.mapping.v0.1.0"
    assert loaded["kind"] == "jobs_parquet"
    assert loaded["fields"]["job_id"]["source"] == "JobID"


def test_mapping_spec_validation_fails_without_fields(tmp_path: Path) -> None:
    path = tmp_path / "mapping.yml"
    path.write_text("schema_version: oda.mapping.v0.1.0\n", encoding="utf-8")
    with pytest.raises(SchemaValidationError):
        read_mapping_spec(path, validate=True)

