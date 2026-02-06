from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    normalized: str
    dtype: str
    inferred_kind: str
    null_rate: float
    sample_values: list[Any]


def _normalize_name(name: str) -> str:
    lowered = name.strip().lower()
    out = []
    prev_underscore = False
    for ch in lowered:
        if ch.isalnum():
            out.append(ch)
            prev_underscore = False
        else:
            if not prev_underscore:
                out.append("_")
                prev_underscore = True
    normalized = "".join(out).strip("_")
    return normalized


def _infer_kind(dtype: pa.DataType) -> str:
    if pa.types.is_timestamp(dtype):
        return "timestamp"
    if pa.types.is_integer(dtype) or pa.types.is_floating(dtype) or pa.types.is_decimal(dtype):
        return "numeric"
    if pa.types.is_dictionary(dtype):
        return "categorical"
    if pa.types.is_string(dtype) or pa.types.is_large_string(dtype):
        return "categorical"
    if pa.types.is_boolean(dtype):
        return "categorical"
    return "unknown"


def _sample_table(path: Path, sample_rows: int) -> pa.Table:
    table = pq.read_table(path)
    if sample_rows <= 0:
        return table
    return table.slice(0, min(sample_rows, table.num_rows))


def profile_parquet(path: Path, *, sample_rows: int = 200) -> list[ColumnProfile]:
    """
    Profile a jobs Parquet export for mapping suggestions.
    Uses a small head sample to estimate null rates and sample values.
    """
    path = Path(path)
    table = _sample_table(path, sample_rows)
    if table.num_rows == 0:
        raise ValueError("Parquet file has no rows to profile.")

    profiles: list[ColumnProfile] = []
    for field in table.schema:
        col = table.column(field.name)
        dtype = field.type
        inferred_kind = _infer_kind(dtype)
        total = table.num_rows
        nulls = col.null_count
        null_rate = float(nulls) / float(total) if total else 0.0

        sample_values: list[Any] = []
        for val in col.to_pylist():
            if val is None:
                continue
            sample_values.append(val)
            if len(sample_values) >= 5:
                break

        profiles.append(
            ColumnProfile(
                name=field.name,
                normalized=_normalize_name(field.name),
                dtype=str(dtype),
                inferred_kind=inferred_kind,
                null_rate=null_rate,
                sample_values=sample_values,
            )
        )

    return profiles

