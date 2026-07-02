from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from hpc_oda_commons.kernel.artifacts.mapping_spec import read_mapping_spec
from hpc_oda_commons.kernel.transformations import hash_identifier


def _parse_timestamp(value: Any, fmt: str) -> datetime | None:
    """Parse a raw timestamp value into a tz-aware UTC datetime (v0.2 canonical
    job tables store timestamps as Arrow timestamp(us, tz=UTC), not ISO strings)."""
    if value is None:
        return None
    if fmt == "iso8601":
        text = str(value).strip()
        if not text:
            return None

        # Be permissive for common upstream exports:
        # - "YYYY-MM-DD HH:MM:SS+09"  (space separator, short offset)
        # - "YYYY-MM-DD HH:MM:SS+09:00"
        # - "YYYY-MM-DDTHH:MM:SS+09"  (short offset)
        #
        # Normalize to something datetime.fromisoformat can parse.
        normalized = text.replace(" ", "T")
        m = re.match(r"^(.*)([+-]\d{2})$", normalized)
        if m:
            normalized = f"{m.group(1)}{m.group(2)}:00"

        dt = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    if fmt == "epoch_s":
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if fmt == "epoch_ms":
        return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
    if fmt == "epoch_us":
        return datetime.fromtimestamp(float(value) / 1_000_000.0, tz=timezone.utc)
    raise ValueError(f"Unsupported timestamp format: {fmt}")


def _duration_to_seconds(value: Any, unit: str) -> float | None:
    if value is None:
        return None
    if unit == "seconds":
        return float(value)
    if unit == "minutes":
        return float(value) * 60.0
    if unit == "hours":
        return float(value) * 3600.0
    if unit == "hh:mm:ss":
        parts = str(value).split(":")
        if len(parts) != 3:
            raise ValueError(f"Invalid duration format: {value}")
        hours, minutes, seconds = [float(p) for p in parts]
        return hours * 3600.0 + minutes * 60.0 + seconds
    if unit == "timedelta":
        # pandas/numpy timedelta string: "N days HH:MM:SS[.ffffff]" or "HH:MM:SS[.ffffff]".
        text = str(value).strip()
        if not text:
            return None
        m = re.match(r"^(?:(\d+)\s+days?\s+)?(\d+):(\d+):(\d+(?:\.\d+)?)$", text)
        if not m:
            raise ValueError(f"Invalid timedelta duration: {value}")
        days = float(m.group(1) or 0)
        hours, minutes, seconds = float(m.group(2)), float(m.group(3)), float(m.group(4))
        return days * 86400.0 + hours * 3600.0 + minutes * 60.0 + seconds
    raise ValueError(f"Unsupported duration unit: {unit}")


def _memory_to_mb(value: Any, unit: str) -> float | None:
    if value is None:
        return None
    base = float(value)
    if unit == "bytes":
        return base / (1024.0 * 1024.0)
    if unit == "kb":
        return base / 1024.0
    if unit == "mb":
        return base
    if unit == "gb":
        return base * 1024.0
    if unit == "kib":
        return base / 1024.0
    if unit == "mib":
        return base
    if unit == "gib":
        return base * 1024.0
    raise ValueError(f"Unsupported memory unit: {unit}")


_SLURM_MEM_UNIT_TO_MIB: dict[str, float] = {
    "K": 1 / 1024,
    "k": 1 / 1024,
    "M": 1,
    "m": 1,
    "G": 1024,
    "g": 1024,
    "T": 1024**2,
    "t": 1024**2,
    "P": 1024**3,
    "p": 1024**3,
    "": 1,
}


def _memory_slurm_to_mb(value: Any) -> float | None:
    """Parse a SLURM memory string like '160G', '2366M', '4096' → MiB (float)."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    m = re.match(r"^([\d.]+)([KMGTPkmgtp]?)$", raw)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2)
    return num * _SLURM_MEM_UNIT_TO_MIB.get(unit, 1.0)


def _apply_transform(value: Any, transform: dict[str, Any] | None) -> Any:
    if transform is None:
        return value
    ttype = transform.get("type")
    if ttype == "timestamp":
        return _parse_timestamp(value, str(transform.get("format", "iso8601")))
    if ttype == "duration":
        return _duration_to_seconds(value, str(transform.get("unit", "seconds")))
    if ttype == "memory":
        return _memory_to_mb(value, str(transform.get("unit", "mb")))
    if ttype == "memory_slurm":
        return _memory_slurm_to_mb(value)
    if ttype == "hash_identifier":
        salt_env = transform.get("salt_env")
        salt = None
        if salt_env:
            import os

            salt = os.environ.get(str(salt_env))
        if value is None:
            return None
        return hash_identifier(str(value), salt=salt)
    return value


def _derive_runtime(row: dict[str, Any]) -> float | None:
    start = row.get("start_time")
    end = row.get("end_time")
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        return None
    runtime = (end - start).total_seconds()
    return max(0.0, float(runtime))


REQUIRED_FIELDS = ("job_id", "start_time", "end_time", "runtime_seconds")

_MEMORY_FACTORS: dict[str, float] = {
    "bytes": 1.0 / (1024.0 * 1024.0),
    "kb": 1.0 / 1024.0,
    "mb": 1.0,
    "gb": 1024.0,
    "kib": 1.0 / 1024.0,
    "mib": 1.0,
    "gib": 1024.0,
}


# Upper-cased SLURM memory unit factors (MiB), mirroring _SLURM_MEM_UNIT_TO_MIB.
_SLURM_VEC_FACTORS: dict[str, float] = {
    "K": 1.0 / 1024.0,
    "M": 1.0,
    "G": 1024.0,
    "T": 1024.0**2,
    "P": 1024.0**3,
    "": 1.0,
}


def _is_numeric(arrow_type: pa.DataType) -> bool:
    return pa.types.is_integer(arrow_type) or pa.types.is_floating(arrow_type)


def _memory_slurm_column(col: pa.Array) -> pa.Array:
    """Vectorized equivalent of ``_memory_slurm_to_mb`` over a whole string column.

    Matches the element-wise helper on every well-formed input (incl. leading/
    trailing dots, lowercase units, surrounding whitespace, and empty/non-matching
    values → null). The one intentional difference: a malformed multi-dot value
    like ``"1.2.3G"`` becomes null here, whereas the element-wise helper crashes
    with ValueError on it (a latent bug this path also fixes).
    """
    text = pc.utf8_trim_whitespace(pc.cast(col, pa.string()))
    parts = pc.extract_regex(text, pattern=r"^(?P<num>[\d.]+)(?P<unit>[KMGTPkmgtp]?)$")
    num = pc.struct_field(parts, "num")
    unit = pc.utf8_upper(pc.fill_null(pc.struct_field(parts, "unit"), ""))
    # float() accepts only values with <=1 dot and >=1 digit; null the rest so the
    # subsequent cast cannot raise (these are exactly the inputs the helper crashes on).
    parseable = pc.and_(
        pc.less_equal(pc.count_substring(num, "."), 1),
        pc.match_substring_regex(num, "[0-9]"),
    )
    num_f = pc.cast(pc.if_else(parseable, num, pa.scalar(None, pa.string())), pa.float64())
    factor: Any = None
    for key, val in _SLURM_VEC_FACTORS.items():
        cond = pc.equal(unit, key)
        factor = pc.if_else(cond, val, factor) if factor is not None else pc.if_else(cond, val, 1.0)
    return pc.multiply(num_f, factor)


def _transform_out_type(transform: dict[str, Any] | None) -> pa.DataType | None:
    """Explicit output type for the element-wise fallback, so columns built from
    all-null batches still concat with their typed siblings."""
    if transform is None:
        return None
    ttype = transform.get("type")
    if ttype in ("duration", "memory", "memory_slurm"):
        return pa.float64()
    if ttype == "timestamp":
        return pa.timestamp("us", tz="UTC")
    if ttype == "hash_identifier":
        return pa.string()
    return None


def _transform_column(col: pa.Array, transform: dict[str, Any] | None) -> pa.Array:
    """Apply a transform to a whole column.

    Uses native pyarrow.compute where it is both cheap and bit-for-bit identical
    to the per-element helper; otherwise falls back to the element-wise helper
    (column-at-a-time, no per-row dicts) to preserve exact behavior.
    """
    if transform is None:
        return col

    ttype = transform.get("type")
    if ttype == "duration":
        if pa.types.is_duration(col.type):
            # Native Arrow duration -> seconds (int64 gives ticks in the column's unit).
            unit_seconds = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9}[col.type.unit]
            return pc.multiply(pc.cast(pc.cast(col, pa.int64()), pa.float64()), unit_seconds)
        factor = {"seconds": 1.0, "minutes": 60.0, "hours": 3600.0}.get(
            str(transform.get("unit", "seconds"))
        )
        if factor is not None and _is_numeric(col.type):
            return pc.multiply(pc.cast(col, pa.float64()), factor)
    elif ttype == "memory":
        factor = _MEMORY_FACTORS.get(str(transform.get("unit", "mb")))
        if factor is not None and _is_numeric(col.type):
            return pc.multiply(pc.cast(col, pa.float64()), factor)
    elif ttype == "timestamp" and str(transform.get("format", "iso8601")) == "epoch_s":
        # Integer epoch seconds cast directly to the canonical timestamp type.
        # Non-integer epoch (or ms/us) falls through to the element-wise helper.
        if pa.types.is_integer(col.type):
            return pc.cast(pc.cast(col, pa.timestamp("s", tz="UTC")), pa.timestamp("us", tz="UTC"))
    elif ttype == "memory_slurm" and pa.types.is_string(col.type):
        return _memory_slurm_column(col)
    elif ttype == "integer":
        # Coerce numeric-as-string (e.g. IC2 "24") or float sources to int64 (via float64
        # so "24.0" works too); already-integer columns pass through unchanged.
        if pa.types.is_integer(col.type):
            return col
        return pc.cast(pc.cast(col, pa.float64()), pa.int64())
    elif ttype == "number":
        if pa.types.is_floating(col.type):
            return col
        return pc.cast(col, pa.float64())

    # Element-wise fallback: iso8601, hh:mm:ss, epoch_ms/us,
    # hash_identifier, non-numeric sources, or unrecognized transforms.
    values = [_apply_transform(v, transform) for v in col.to_pylist()]
    return pa.array(values, type=_transform_out_type(transform) or col.type)


def _completeness_mask(table: pa.Table) -> Any:
    """Boolean mask: True where every required field is present and non-empty."""
    masks: list[Any] = []
    for field in REQUIRED_FIELDS:
        if field not in table.column_names:
            return pa.array([False] * table.num_rows)
        col = table.column(field)
        valid = pc.is_valid(col)
        if pa.types.is_string(col.type):
            valid = pc.and_(valid, pc.not_equal(col, ""))
        masks.append(pc.fill_null(valid, False))
    mask = masks[0]
    for other in masks[1:]:
        mask = pc.and_(mask, other)
    return mask


def apply_mapping_spec(
    input_path: Path,
    mapping_path: Path,
    out_path: Path,
    *,
    batch_size: int = 50_000,
    skip_incomplete: bool = True,
    state_allowlist: set[str] | None = None,
) -> dict[str, Any]:
    """
    Apply a mapping spec to a jobs Parquet export and write canonical ODA job Parquet.
    Returns a summary dict with counts.

    Transforms run column-wise (vectorized where possible, else element-wise on a
    single column) rather than row-at-a-time; output is identical to the prior
    row-based implementation.
    """
    mapping = read_mapping_spec(mapping_path, validate=True)
    fields: dict[str, Any] = mapping.get("fields", {})
    derives_runtime = fields.get("runtime_seconds", {}).get("derive") == "end_time - start_time"

    # Fixed output column order, identical across batches so filtered tables concat.
    out_order = list(fields.keys()) + [f for f in REQUIRED_FIELDS if f not in fields]
    optional_fields = [f for f in out_order if f not in REQUIRED_FIELDS]

    total = 0
    kept = 0
    skipped = 0
    skipped_state_filter = 0
    kept_tables: list[pa.Table] = []

    parquet = pq.ParquetFile(input_path)
    for batch in parquet.iter_batches(batch_size=batch_size):
        table = pa.Table.from_batches([batch])
        n = table.num_rows
        total += n

        columns: dict[str, pa.Array] = {}
        for field in out_order:
            spec = fields.get(field, {})
            source = spec.get("source")
            if source and source in table.column_names:
                columns[field] = _transform_column(
                    table.column(source).combine_chunks(), spec.get("transform")
                )
            else:
                columns[field] = pa.nulls(n)

        # Derive runtime where it is missing (null/empty) and a derive is configured.
        if derives_runtime:
            runtime = columns["runtime_seconds"]
            need = pc.is_null(runtime)
            if pa.types.is_string(runtime.type):
                need = pc.or_(need, pc.equal(runtime, ""))
            if pc.any(need).as_py():
                starts = columns["start_time"].to_pylist()
                ends = columns["end_time"].to_pylist()
                filled = [
                    _derive_runtime({"start_time": s, "end_time": e}) if nd else r
                    for nd, s, e, r in zip(
                        need.to_pylist(), starts, ends, runtime.to_pylist(), strict=False
                    )
                ]
                columns["runtime_seconds"] = pa.array(filled, type=pa.float64())

        batch_table = pa.table({field: columns[field] for field in out_order})

        # State-allowlist filter runs first; rows it drops are not also counted
        # as "incomplete" (matches the prior continue-before-skip ordering).
        if state_allowlist is not None:
            if "state" in batch_table.column_names:
                state_col = pc.cast(batch_table.column("state"), pa.string())
                allowed = pa.array(sorted(state_allowlist), type=pa.string())
                state_mask = pc.fill_null(pc.is_in(state_col, value_set=allowed), False)
            else:
                state_mask = pa.array([False] * batch_table.num_rows)
            skipped_state_filter += (
                batch_table.num_rows - pc.sum(pc.cast(state_mask, pa.int64())).as_py()
            )
            batch_table = batch_table.filter(state_mask)

        if skip_incomplete:
            complete = _completeness_mask(batch_table)
            kept_count = pc.sum(pc.cast(complete, pa.int64())).as_py()
            skipped += batch_table.num_rows - kept_count
            batch_table = batch_table.filter(complete)

        kept += batch_table.num_rows
        if batch_table.num_rows:
            kept_tables.append(batch_table)

    if not kept_tables:
        raise ValueError("No rows produced after applying mapping spec.")

    result = pa.concat_tables(kept_tables)

    # Optional fields: convert "" to null, then drop columns that are empty in
    # every kept row (an all-null optional column is typed without "null" in the
    # job schema and would fail strict validation). Partially-populated columns
    # stay, emitting null for the empty rows.
    for field in optional_fields:
        col = result.column(field)
        if pa.types.is_string(col.type):
            col = pc.if_else(pc.equal(col, ""), pa.scalar(None, pa.string()), col)
            result = result.set_column(result.schema.get_field_index(field), field, col)
        if result.column(field).null_count == result.num_rows:
            result = result.drop([field])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(result, out_path)

    return {
        "rows_total": total,
        "rows_kept": kept,
        "rows_skipped": skipped,
        "rows_skipped_state_filter": skipped_state_filter,
        "state_filter_values": sorted(state_allowlist) if state_allowlist is not None else [],
    }
