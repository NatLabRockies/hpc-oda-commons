"""Text processing primitives for TF-IDF + kNN runtime prediction."""

from __future__ import annotations

from typing import Any

_DEFAULT_EXCLUDE = frozenset(
    {
        "job_id",
        "runtime_seconds",
        "start_time",
        "end_time",
        "submit_time",
        "state",
    }
)


def detect_text_columns(
    rows: list[dict[str, Any]],
    *,
    exclude: frozenset[str] | None = None,
) -> list[str]:
    """Find string-valued columns in rows, excluding known non-text fields."""
    if not rows:
        return []
    excl = exclude if exclude is not None else _DEFAULT_EXCLUDE
    text_cols: list[str] = []
    for key in rows[0]:
        if key in excl:
            continue
        for row in rows:
            val = row.get(key)
            if val is not None and val != "":
                if isinstance(val, str):
                    text_cols.append(key)
                break
    return sorted(text_cols)


def build_text_column(
    rows: list[dict[str, Any]],
    text_columns: list[str],
) -> list[str]:
    """Concatenate text column values per row into space-separated strings."""
    result: list[str] = []
    for row in rows:
        parts = [str(row.get(col, "")) for col in text_columns]
        result.append(" ".join(parts))
    return result
