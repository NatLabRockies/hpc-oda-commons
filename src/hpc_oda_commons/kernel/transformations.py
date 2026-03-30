from __future__ import annotations

import hashlib


def hash_identifier(value: str, *, salt: str | None = None) -> str:
    """
    Hash a sensitive identifier (e.g., user_id) using SHA-256.
    """
    payload = value if salt is None else f"{salt}:{value}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
