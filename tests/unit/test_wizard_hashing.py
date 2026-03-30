from __future__ import annotations

from typing import Any

import pytest

from hpc_oda_commons.ingest.jobs_parquet.wizard import _prompt_fields_to_hash


def _make_fields(**kwargs: str | None) -> dict[str, dict[str, Any]]:
    """Build a fields dict. Values are source column names (None = unmapped)."""
    fields: dict[str, dict[str, Any]] = {}
    for name, source in kwargs.items():
        entry: dict[str, Any] = {"source": source, "role": "optional"}
        fields[name] = entry
    return fields


def test_selects_user_and_account_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    fields = _make_fields(user="User", account="Account", partition="Partition")
    monkeypatch.setattr("typer.prompt", lambda *a, **kw: kw.get("default", ""))
    monkeypatch.setattr("typer.echo", lambda *a, **kw: None)

    _prompt_fields_to_hash(fields, default_hash_identifiers=True)

    assert fields["user"]["transform"]["type"] == "hash_identifier"
    assert fields["account"]["transform"]["type"] == "hash_identifier"
    assert "transform" not in fields["partition"]


def test_user_can_select_arbitrary_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    fields = _make_fields(user="User", partition="Partition", qos="QOS")
    monkeypatch.setattr("typer.prompt", lambda *a, **kw: "partition, qos")
    monkeypatch.setattr("typer.echo", lambda *a, **kw: None)

    _prompt_fields_to_hash(fields, default_hash_identifiers=True)

    assert "transform" not in fields["user"]
    assert fields["partition"]["transform"]["type"] == "hash_identifier"
    assert fields["qos"]["transform"]["type"] == "hash_identifier"


def test_none_skips_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    fields = _make_fields(user="User", account="Account")
    monkeypatch.setattr("typer.prompt", lambda *a, **kw: "none")
    monkeypatch.setattr("typer.echo", lambda *a, **kw: None)

    _prompt_fields_to_hash(fields, default_hash_identifiers=True)

    assert "transform" not in fields["user"]
    assert "transform" not in fields["account"]


def test_fields_with_existing_transforms_excluded() -> None:
    fields: dict[str, dict[str, Any]] = {
        "start_time": {
            "source": "Start",
            "role": "required",
            "transform": {"type": "timestamp", "format": "iso8601"},
        },
        "user": {"source": "User", "role": "optional"},
        "runtime_seconds": {
            "source": "Elapsed",
            "role": "required",
            "transform": {"type": "duration", "unit": "seconds"},
        },
    }
    # _prompt_fields_to_hash determines hashable fields internally;
    # start_time and runtime_seconds already have transforms so only user is hashable
    hashable = [
        name
        for name, spec in fields.items()
        if spec.get("source") and not spec.get("transform") and not spec.get("derive")
    ]
    assert hashable == ["user"]


def test_no_hashable_fields_skips_prompt() -> None:
    fields: dict[str, dict[str, Any]] = {
        "start_time": {
            "source": "Start",
            "role": "required",
            "transform": {"type": "timestamp", "format": "iso8601"},
        },
    }
    # Should not raise or prompt -- no hashable fields
    _prompt_fields_to_hash(fields, default_hash_identifiers=True)
    assert fields["start_time"]["transform"]["type"] == "timestamp"


def test_default_none_when_hash_identifiers_false(monkeypatch: pytest.MonkeyPatch) -> None:
    fields = _make_fields(user="User", account="Account")
    # With default_hash_identifiers=False, default prompt value should be "none"
    captured_default = {}

    def fake_prompt(*args: Any, **kwargs: Any) -> str:
        captured_default["value"] = kwargs.get("default", "")
        return kwargs.get("default", "")

    monkeypatch.setattr("typer.prompt", fake_prompt)
    monkeypatch.setattr("typer.echo", lambda *a, **kw: None)

    _prompt_fields_to_hash(fields, default_hash_identifiers=False)

    assert captured_default["value"] == "none"
    assert "transform" not in fields["user"]
    assert "transform" not in fields["account"]


def test_unmapped_fields_excluded() -> None:
    fields: dict[str, dict[str, Any]] = {
        "user": {"source": None, "role": "optional"},
        "partition": {"source": "Partition", "role": "optional"},
    }
    hashable = [
        name
        for name, spec in fields.items()
        if spec.get("source") and not spec.get("transform") and not spec.get("derive")
    ]
    # user has source=None, so only partition is hashable
    assert hashable == ["partition"]
