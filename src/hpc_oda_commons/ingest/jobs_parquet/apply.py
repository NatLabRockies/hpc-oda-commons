from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from hpc_oda_commons.kernel.artifacts.mapping_spec import read_mapping_spec
from hpc_oda_commons.kernel.transformations import hash_identifier


def _parse_timestamp(value: Any, fmt: str) -> str | None:
    if value is None:
        return None
    if fmt == "iso8601":
        text = str(value).strip()
        if not text:
            return None

        # Accept strict ISO-8601 (including trailing Z) as-is.
        if text.endswith("Z"):
            return text

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
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    if fmt == "epoch_s":
        dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    if fmt == "epoch_ms":
        dt = datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    if fmt == "epoch_us":
        dt = datetime.fromtimestamp(float(value) / 1_000_000.0, tz=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
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
    if not start or not end:
        return None
    sdt = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
    edt = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
    runtime = (edt - sdt).total_seconds()
    return max(0.0, float(runtime))


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
    """
    mapping = read_mapping_spec(mapping_path, validate=True)
    fields: dict[str, Any] = mapping.get("fields", {})
    required = {"job_id", "start_time", "end_time", "runtime_seconds"}

    out_rows: list[dict[str, Any]] = []
    total = 0
    kept = 0
    skipped = 0
    skipped_state_filter = 0

    parquet = pq.ParquetFile(input_path)
    for batch in parquet.iter_batches(batch_size=batch_size):
        table = pa.Table.from_batches([batch])
        for row in table.to_pylist():
            total += 1
            out_row: dict[str, Any] = {}
            for field, spec in fields.items():
                source = spec.get("source")
                if source:
                    value = row.get(source)
                else:
                    value = None
                value = _apply_transform(value, spec.get("transform"))
                out_row[field] = value

            if out_row.get("runtime_seconds") in (None, ""):
                if fields.get("runtime_seconds", {}).get("derive") == "end_time - start_time":
                    out_row["runtime_seconds"] = _derive_runtime(out_row)

            if state_allowlist is not None:
                state_value = out_row.get("state")
                if state_value is None or str(state_value) not in state_allowlist:
                    skipped_state_filter += 1
                    continue

            if skip_incomplete and any(out_row.get(field) in (None, "") for field in required):
                skipped += 1
                continue

            # Drop empty optional fields. Because the table is written via
            # from_pylist (which unions keys across rows), this only fully removes
            # an optional column when it is empty in *every* row -- which is the
            # case that matters: an all-null optional column is typed without
            # "null" in the job schema, so emitting it would fail strict validation.
            # Optional columns populated in some rows still emit null for the empty
            # rows (see follow-up F-1).
            for key in list(out_row.keys()):
                if key in required:
                    continue
                if out_row.get(key) in (None, ""):
                    out_row.pop(key, None)

            kept += 1
            out_rows.append(out_row)

    if not out_rows:
        raise ValueError("No rows produced after applying mapping spec.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(out_rows), out_path)

    return {
        "rows_total": total,
        "rows_kept": kept,
        "rows_skipped": skipped,
        "rows_skipped_state_filter": skipped_state_filter,
        "state_filter_values": sorted(state_allowlist) if state_allowlist is not None else [],
    }
