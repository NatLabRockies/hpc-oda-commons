from __future__ import annotations

from hpc_oda_commons.kernel.transformations import hash_identifier


def test_hash_identifier_is_deterministic() -> None:
    h1 = hash_identifier("user123")
    h2 = hash_identifier("user123")
    assert h1 == h2


def test_hash_identifier_with_salt_changes_output() -> None:
    base = hash_identifier("user123")
    salted = hash_identifier("user123", salt="pepper")
    assert base != salted
