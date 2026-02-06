from __future__ import annotations

from hpc_oda_commons.kernel.transformations import bin_timestamp, hash_identifier, redact_value


def test_hash_identifier_is_deterministic() -> None:
    h1 = hash_identifier("user123")
    h2 = hash_identifier("user123")
    assert h1 == h2


def test_hash_identifier_with_salt_changes_output() -> None:
    base = hash_identifier("user123")
    salted = hash_identifier("user123", salt="pepper")
    assert base != salted


def test_bin_timestamp() -> None:
    ts = "2026-01-01T00:00:59Z"
    assert bin_timestamp(ts, interval_seconds=60) == "2026-01-01T00:00:00Z"


def test_redact_value_defaults_to_none() -> None:
    assert redact_value("secret") is None
    assert redact_value("secret", replacement="REDACTED") == "REDACTED"
