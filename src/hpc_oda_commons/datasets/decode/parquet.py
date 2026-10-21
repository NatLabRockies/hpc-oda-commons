"""Parquet decoder: concatenate the fetched parquet file(s) into one table."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from hpc_oda_commons.datasets.decode.base import DecodeError


def _unify_temporal(table: pa.Table) -> pa.Table:
    """Normalize temporal columns so heterogeneous Hive partitions concatenate cleanly.

    Partitioned exports sometimes vary the storage of the same column across partitions:
    - tz-aware timestamps written with different offsets (e.g. local ``-07:00`` vs ``UTC``);
    - durations written with different units (``us`` vs ``ns``).

    Both are re-tagged to a common representation: timestamps to ``timestamp(us, tz=UTC)``
    (an Arrow timestamp is an absolute instant regardless of tz metadata, so this is
    lossless) and durations to ``duration(us)`` (a coarse-enough unit to avoid the
    overflow that permissive concat hits when promoting a large "unlimited" walltime
    sentinel to ``ns``; sub-microsecond precision is irrelevant for job durations).
    """
    for i in range(table.num_columns):
        field = table.schema.field(i)
        t = field.type
        if pa.types.is_timestamp(t) and t.tz is not None and (t.tz != "UTC" or t.unit != "us"):
            table = table.set_column(
                i, field.name, pc.cast(table.column(i), pa.timestamp("us", tz="UTC"))
            )
        elif pa.types.is_duration(t) and t.unit != "us":
            table = table.set_column(i, field.name, pc.cast(table.column(i), pa.duration("us")))
    return table


def _unified_type(t: pa.DataType) -> pa.DataType:
    """The type :func:`_unify_temporal` gives a column of type ``t``."""
    if pa.types.is_timestamp(t) and t.tz is not None and (t.tz != "UTC" or t.unit != "us"):
        return pa.timestamp("us", tz="UTC")
    if pa.types.is_duration(t) and t.unit != "us":
        return pa.duration("us")
    return t


def decode_parquet(
    files: Sequence[Path], dest: Path, *, options: Mapping[str, Any] | None = None
) -> None:
    """Concatenate ``files`` into ``dest``, one file at a time (#249).

    The schemas are unified first, as a permissive concat would, so each file is read,
    cast and written on its own: a source of many large files (twelve months of F-DATA
    with its embeddings) never has to fit in memory at once.
    """
    if not files:
        raise DecodeError("no input files to decode")
    # ``columns`` restricts the read to the mapped source columns — decisive for datasets
    # that carry heavy per-job array columns (e.g. NLR energy time series) we never map.
    columns = list(options["columns"]) if options and options.get("columns") else None
    schemas = []
    for f in files:
        schema = pq.read_schema(f)
        if columns is not None:
            schema = pa.schema([schema.field(c) for c in columns if c in schema.names])
        schemas.append(pa.schema([fld.with_type(_unified_type(fld.type)) for fld in schema]))
    schema = pa.unify_schemas(schemas, promote_options="permissive")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with pq.ParquetWriter(dest, schema) as writer:
        for f in files:
            table = _unify_temporal(pq.read_table(f, columns=columns))
            for field in schema:
                if field.name not in table.column_names:
                    table = table.append_column(field, pa.nulls(table.num_rows, field.type))
            writer.write_table(table.select(schema.names).cast(schema))
