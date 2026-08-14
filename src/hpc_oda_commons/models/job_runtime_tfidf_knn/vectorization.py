"""Text processing primitives for TF-IDF + kNN runtime prediction."""

from __future__ import annotations

from typing import Any

from hpc_oda_commons.models.feature_policy import RUNTIME_PREDICTION_FEATURE_FIELDS


def detect_text_columns(
    rows: list[dict[str, Any]],
    *,
    extra_fields: frozenset[str] | None = None,
) -> list[str]:
    """Find the string-valued columns this model may vectorize.

    Restricted to the shared submission-time allowlist (plus ``extra_fields``).
    The previous blocklist named ``state``, but canonical tables spell it
    ``job_state``, so the job's final outcome was going straight into the
    document — ``TIMEOUT`` is close to a statement of the target.
    """
    if not rows:
        return []
    allowed = RUNTIME_PREDICTION_FEATURE_FIELDS | frozenset(extra_fields or ())
    text_cols: list[str] = []
    for key in rows[0]:
        if key not in allowed:
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
