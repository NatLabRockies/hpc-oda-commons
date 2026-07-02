"""CSV decoder: read the fetched CSV file(s) into one table via pyarrow."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from hpc_oda_commons.datasets.decode.base import DecodeError


def decode_csv(
    files: Sequence[Path], dest: Path, *, options: Mapping[str, Any] | None = None
) -> None:
    if not files:
        raise DecodeError("no input files to decode")
    options = dict(options or {})
    parse_options = pacsv.ParseOptions(delimiter=str(options.get("delimiter", ",")))
    # ``columns`` restricts the read to the mapped source columns -- skips heavy unmapped
    # columns and avoids concat failures when an unmapped column's inferred type varies
    # across files (e.g. FRESCO Conte's Resource_List.neednodes: string vs int64).
    convert_options = None
    if options.get("columns"):
        convert_options = pacsv.ConvertOptions(include_columns=list(options["columns"]))
    tables = [
        pacsv.read_csv(f, parse_options=parse_options, convert_options=convert_options)
        for f in files
    ]
    table = (
        tables[0] if len(tables) == 1 else pa.concat_tables(tables, promote_options="permissive")
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, dest)
