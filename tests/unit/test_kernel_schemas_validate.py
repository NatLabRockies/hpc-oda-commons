from __future__ import annotations

import pytest

from hpc_oda_commons.kernel.schemas import load_schema
from hpc_oda_commons.kernel.validate import SchemaValidationError, validate_json


def test_load_schema_known_ids() -> None:
    assert load_schema("oda.job.v0.1.0")["type"] == "object"
    assert load_schema("oda.result.v0.1.0")["type"] == "object"
    assert load_schema("oda.manifest.v0.1.0")["type"] == "object"


def test_validate_json_happy_and_error_message() -> None:
    payload = {
        "schema_version": "oda.manifest.v0.1.0",
        "created_at": "2026-01-01T00:00:00Z",
        "input_schema_version": "oda.job.v0.1.0",
        "artifact": {"type": "ingest"},
        "provenance": {
            "schema_versions": {"input": "oda.job.v0.1.0", "result": "oda.result.v0.1.0"}
        },
    }
    validate_json(payload, "oda.manifest.v0.1.0")

    bad = dict(payload)
    bad.pop("created_at")
    with pytest.raises(SchemaValidationError) as e:
        validate_json(bad, "oda.manifest.v0.1.0")
    assert "validation failed" in str(e.value).lower()
