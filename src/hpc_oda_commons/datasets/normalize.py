"""
Normalize a decoded intermediate table onto a canonical ODA schema.

A descriptor target carries an inline ``mapping`` (canonical column -> source field
rule). This module translates that into an ``oda.mapping`` spec and runs the existing
:func:`apply_mapping_spec` (single source of truth for the timestamp/duration/memory/
hash transforms, completeness filtering, and runtime derivation), then applies the
optional ``filter`` / ``sample`` / ``select`` refinements.
"""

from __future__ import annotations

import random
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from hpc_oda_commons.datasets.descriptor import Target
from hpc_oda_commons.ingest.jobs_parquet.apply import REQUIRED_FIELDS, apply_mapping_spec
from hpc_oda_commons.kernel.artifacts.mapping_spec import new_mapping_spec, write_mapping_spec

_TRANSFORM_TYPES = frozenset(
    {"timestamp", "duration", "memory", "memory_slurm", "hash_identifier", "integer", "number"}
)
_JOB_SCHEMA_PREFIX = "oda.job."
_SYNTH_PREFIX = "__synth_"


class NormalizeError(Exception):
    """Raised when a target cannot be normalized."""


def _synth_fields(target: Target) -> list[str]:
    """Canonical fields whose value is a row-index surrogate (no natural source column)."""
    return [
        canonical
        for canonical, rule in target.mapping.items()
        if isinstance(rule, Mapping) and rule.get("synthesize") == "row_index"
    ]


def target_to_mapping_spec(target: Target) -> dict[str, Any]:
    """Translate a target's inline mapping into an ``oda.mapping.v0.1.0`` spec."""
    fields: dict[str, Any] = {}
    for canonical, rule in target.mapping.items():
        if rule.get("synthesize") == "row_index":
            # Surrogate column injected into the intermediate by normalize_target.
            fields[canonical] = {"source": f"{_SYNTH_PREFIX}{canonical}"}
            continue
        spec: dict[str, Any] = {"source": rule.get("from")}
        if rule.get("derive"):
            spec["derive"] = rule["derive"]
        ttype = rule.get("type")
        if ttype in _TRANSFORM_TYPES:
            transform: dict[str, Any] = {"type": ttype}
            if "format" in rule:
                transform["format"] = rule["format"]
            if "unit" in rule:
                transform["unit"] = rule["unit"]
            spec["transform"] = transform
        fields[canonical] = spec
    return new_mapping_spec(
        kind="public_dataset", output_schema_version=target.schema, fields=fields
    )


def _write_with_synthetic_ids(
    src: Path, fields: Sequence[str], dest: Path, *, batch_size: int
) -> None:
    """Copy ``src`` to ``dest`` adding an int64 ``__synth_<field>`` column (0..N-1)
    per synthesized field, assigned across batches so ids stay globally unique."""
    reader = pq.ParquetFile(src)
    writer: pq.ParquetWriter | None = None
    offset = 0
    try:
        for batch in reader.iter_batches(batch_size=batch_size):
            table = pa.Table.from_batches([batch])
            idx = pa.array(range(offset, offset + table.num_rows), type=pa.int64())
            for field in fields:
                table = table.append_column(f"{_SYNTH_PREFIX}{field}", idx)
            if writer is None:
                writer = pq.ParquetWriter(dest, table.schema)
            writer.write_table(table)
            offset += table.num_rows
    finally:
        if writer is not None:
            writer.close()


def _apply_filter(table: pa.Table, filt: Mapping[str, Any]) -> pa.Table:
    for key, value in filt.items():
        if key == "require_nonnull":
            for column in value:
                if column in table.column_names:
                    table = table.filter(pc.is_valid(table.column(column)))
        elif key == "require_positive":
            # Drop rows where a listed field is present but <= 0 (nulls are kept).
            # or_kleene so ``True OR null`` stays True (else a null field would drop the row).
            for column in value:
                if column in table.column_names:
                    col = table.column(column)
                    table = table.filter(pc.or_kleene(pc.is_null(col), pc.greater(col, 0)))
        elif key == "require_end_after_start":
            # Drop rows whose start_time is after end_time (inverted source timestamps).
            if value and {"start_time", "end_time"} <= set(table.column_names):
                start, end = table.column("start_time"), table.column("end_time")
                keep = pc.or_kleene(pc.less_equal(start, end), pc.is_null(start))
                table = table.filter(pc.or_kleene(keep, pc.is_null(end)))
        else:
            raise NormalizeError(
                f"unsupported filter '{key}' (supported: require_nonnull, "
                "require_positive, require_end_after_start)"
            )
    return table


def _take(table: pa.Table, indices: Sequence[int]) -> pa.Table:
    return table.take(pa.array(sorted(indices), type=pa.int64()))


def _apply_sample(table: pa.Table, sample: Mapping[str, Any]) -> pa.Table:
    n = int(sample["rows"])
    if table.num_rows <= n:
        return table

    strategy = str(sample.get("strategy", "head"))
    if strategy == "head":
        return table.slice(0, n)

    rng = random.Random(int(sample.get("seed", 0)))
    if strategy == "random":
        return _take(table, rng.sample(range(table.num_rows), k=n))

    if strategy == "stratified":
        by = [c for c in (sample.get("by") or []) if c in table.column_names]
        if not by:
            return _take(table, rng.sample(range(table.num_rows), k=n))
        key_columns = [table.column(c).to_pylist() for c in by]
        row_keys = list(zip(*key_columns, strict=False))
        groups: dict[tuple, list[int]] = {}
        for i, key in enumerate(row_keys):
            groups.setdefault(key, []).append(i)
        total = table.num_rows
        chosen: list[int] = []
        for key in sorted(groups, key=str):
            members = groups[key]
            alloc = min(len(members), max(0, round(n * len(members) / total)))
            if alloc:
                chosen.extend(rng.sample(members, k=alloc))
        chosen = sorted(set(chosen))[:n]
        return _take(table, chosen)

    raise NormalizeError(f"unsupported sample strategy '{strategy}'")


def _apply_select(table: pa.Table, select: Sequence[str], schema: str) -> pa.Table:
    keep = [c for c in select if c in table.column_names]
    if schema.startswith(_JOB_SCHEMA_PREFIX):
        missing = [f for f in REQUIRED_FIELDS if f not in keep]
        if missing:
            raise NormalizeError(
                f"select drops required job fields {missing}; include them in `select`"
            )
    return table.select(keep)


def normalize_target(
    intermediate_parquet: Path,
    target: Target,
    out_path: Path,
    *,
    batch_size: int = 50_000,
) -> dict[str, Any]:
    """Map ``intermediate_parquet`` onto ``target.schema`` and write ``out_path``."""
    spec = target_to_mapping_spec(target)
    synth = _synth_fields(target)
    with tempfile.TemporaryDirectory() as tmp:
        source_parquet = intermediate_parquet
        if synth:
            source_parquet = Path(tmp) / "with_synth.parquet"
            _write_with_synthetic_ids(
                intermediate_parquet, synth, source_parquet, batch_size=batch_size
            )
        mapping_path = Path(tmp) / "mapping.yml"
        write_mapping_spec(mapping_path, spec, validate=True)
        mapped_path = Path(tmp) / "mapped.parquet"
        summary = apply_mapping_spec(
            source_parquet, mapping_path, mapped_path, batch_size=batch_size
        )
        table = pq.read_table(mapped_path)

    if target.filter:
        table = _apply_filter(table, target.filter)
    if target.sample:
        table = _apply_sample(table, target.sample)
    if target.select:
        table = _apply_select(table, target.select, target.schema)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out_path)
    summary["rows_final"] = table.num_rows
    return summary
