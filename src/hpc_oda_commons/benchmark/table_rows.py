"""Turn a job table into benchmark rows without exploding dense vector columns.

``pyarrow.Table.to_pylist()`` is the natural way to get the ``list[dict]`` the models
consume, but it materializes every value as a Python object. That is fine for scalars and
ruinous for the dense ``embedding`` column: a 1024-dim vector costs ~4 KB as float32 and
~33 KB as a Python list of Python floats, so a 4.5M-row embedded table needs ~147 GB of
objects to carry ~18 GB of numbers. One cell of the fleet run was OOM-killed at 231 GB on a
240 GB node for exactly this reason (#164).

So: lift float-list columns out of the table into compact float32 matrices first, let
``to_pylist()`` handle everything else, and hand each row a **view** into its matrix row.
The row still looks like a sequence of floats to callers -- ``len()``, indexing and
``np.asarray`` all behave -- but costs ~112 bytes of Python object instead of ~33 KB.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pyarrow as pa


def _is_float_vector_column(field: pa.Field) -> bool:
    """True for ``list<float>`` / ``fixed_size_list<float>`` columns."""
    t = field.type
    if not (pa.types.is_list(t) or pa.types.is_fixed_size_list(t) or pa.types.is_large_list(t)):
        return False
    return pa.types.is_floating(t.value_type)


def _vector_matrix(column: pa.ChunkedArray) -> np.ndarray | None:
    """Dense ``(n_rows, dim)`` float32 matrix, or None if the column is not uniform.

    Returns None -- rather than raising -- when the column has nulls or ragged rows, so the
    caller can fall back to the ordinary path and let the model raise its own error with the
    row index. This function's job is the memory optimisation, not validation.
    """
    array = column.combine_chunks()
    if array.null_count:
        return None

    if pa.types.is_fixed_size_list(array.type):
        dim = array.type.list_size
    else:
        offsets = np.asarray(array.offsets)
        widths = np.diff(offsets)
        if len(widths) == 0 or not np.all(widths == widths[0]):
            return None
        dim = int(widths[0])
    if dim <= 0:
        return None

    values = array.flatten()
    if values.null_count:
        return None
    flat = values.to_numpy(zero_copy_only=False).astype(np.float32, copy=False)
    if flat.size != len(array) * dim:
        return None
    return flat.reshape(len(array), dim)


def table_to_rows(table: pa.Table) -> list[dict[str, Any]]:
    """``table.to_pylist()``, with dense float-vector columns kept as numpy views."""
    vectors: dict[str, np.ndarray] = {}
    for field in table.schema:
        if not _is_float_vector_column(field):
            continue
        matrix = _vector_matrix(table.column(field.name))
        if matrix is not None:
            vectors[field.name] = matrix

    if not vectors:
        return table.to_pylist()

    # Drop the heavy columns before to_pylist(), then reattach as views. Order is what makes
    # this worth doing: converting first and discarding after would still pay the peak.
    lean = table.drop_columns(list(vectors))
    rows = lean.to_pylist()
    for name, matrix in vectors.items():
        for i, row in enumerate(rows):
            row[name] = matrix[i]
    return rows
