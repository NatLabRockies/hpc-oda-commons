from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


def hash_identifier(value: str, *, salt: str | None = None) -> str:
    """
    Hash a sensitive identifier (e.g., user_id) using SHA-256.
    """
    payload = value if salt is None else f"{salt}:{value}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def bin_timestamp(value: str, *, interval_seconds: int) -> str:
    """
    Bin a timestamp down to a fixed interval (in seconds).
    """
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    epoch = int(dt.timestamp())
    binned = (epoch // interval_seconds) * interval_seconds
    return datetime.fromtimestamp(binned, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def redact_value(value: Any, *, replacement: Any | None = None) -> Any:
    """
    Redact a sensitive value by replacing it with None or a provided replacement.
    """
    _ = value
    return replacement
