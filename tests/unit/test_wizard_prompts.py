from __future__ import annotations

from typing import Any

import pytest

from hpc_oda_commons.ingest.jobs_parquet.wizard import (
    _prompt_column,
    _prompt_duration_unit,
    _prompt_fields_to_hash,
)


def test_prompt_column_retries_on_unknown_column(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter(["bad_column", "JobID"])
    errors: list[str] = []

    monkeypatch.setattr("typer.prompt", lambda *a, **kw: next(responses))
    monkeypatch.setattr(
        "hpc_oda_commons.ingest.jobs_parquet.wizard._echo_prompt_error",
        lambda message: errors.append(message),
    )

    result = _prompt_column(
        "job_id",
        [{"column": "JobID"}],
        ["JobID", "StartTime"],
    )

    assert result == "JobID"
    assert len(errors) == 1
    assert "Unknown column 'bad_column'" in errors[0]


def test_prompt_duration_unit_retries_on_invalid_unit(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter(["weeks", "minutes"])
    errors: list[str] = []

    monkeypatch.setattr("typer.prompt", lambda *a, **kw: next(responses))
    monkeypatch.setattr(
        "hpc_oda_commons.ingest.jobs_parquet.wizard._echo_prompt_error",
        lambda message: errors.append(message),
    )

    result = _prompt_duration_unit("runtime_seconds")

    assert result == "minutes"
    assert len(errors) == 1
    assert "Unsupported duration unit" in errors[0]


def test_prompt_fields_to_hash_retries_on_unknown_field(monkeypatch: pytest.MonkeyPatch) -> None:
    fields: dict[str, dict[str, Any]] = {
        "user": {"source": "User", "role": "optional"},
        "partition": {"source": "Partition", "role": "optional"},
    }
    responses = iter(["bogus, user", "user"])
    errors: list[str] = []

    monkeypatch.setattr("typer.prompt", lambda *a, **kw: next(responses))
    monkeypatch.setattr("typer.echo", lambda *a, **kw: None)
    monkeypatch.setattr(
        "hpc_oda_commons.ingest.jobs_parquet.wizard._echo_prompt_error",
        lambda message: errors.append(message),
    )

    _prompt_fields_to_hash(fields, default_hash_identifiers=False)

    assert fields["user"]["transform"]["type"] == "hash_identifier"
    assert "transform" not in fields["partition"]
    assert len(errors) == 1
    assert "Unknown fields: bogus" in errors[0]
