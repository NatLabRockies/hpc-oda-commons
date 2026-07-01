"""Parquet decoder: concatenate the fetched parquet file(s) into one table."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hpc_oda_commons.datasets.decode.base import DecodeError


def decode_parquet(files: Sequence[Path], dest: Path) -> None:
    if not files:
        raise DecodeError("no input files to decode")
    tables = [pq.read_table(f) for f in files]
    table = (
        tables[0] if len(tables) == 1 else pa.concat_tables(tables, promote_options="permissive")
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, dest)
