"""Parquet decoder: concatenate the fetched parquet file(s) into one table."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

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


def decode_parquet(files: Sequence[Path], dest: Path) -> None:
    if not files:
        raise DecodeError("no input files to decode")
    tables = [_unify_temporal(pq.read_table(f)) for f in files]
    table = (
        tables[0] if len(tables) == 1 else pa.concat_tables(tables, promote_options="permissive")
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, dest)
