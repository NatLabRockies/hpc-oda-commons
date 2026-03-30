"""
Canonical JSON serialization utilities for HPC ODA Commons.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def to_jsonable(value: Any) -> Any:
    """Recursively convert a value to a JSON-serializable form."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.isoformat()
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
