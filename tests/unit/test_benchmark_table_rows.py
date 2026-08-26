"""Dense vector columns must not become Python objects on the way to benchmark rows."""

from __future__ import annotations

import numpy as np
import pyarrow as pa
import pytest

from hpc_oda_commons.benchmark.table_rows import table_to_rows


def _table(embeddings: list[list[float] | None], *, fixed: bool = False) -> pa.Table:
    dim = len(next(e for e in embeddings if e is not None))
    kind = pa.list_(pa.float32(), dim) if fixed else pa.list_(pa.float32())
    return pa.table(
        {
            "job_id": pa.array([f"j{i}" for i in range(len(embeddings))]),
            "runtime_seconds": pa.array([float(i) for i in range(len(embeddings))]),
            "embedding": pa.array(embeddings, type=kind),
        }
    )


def test_scalar_columns_match_to_pylist() -> None:
    table = _table([[1.0, 2.0], [3.0, 4.0]])

    rows = table_to_rows(table)
    reference = table.to_pylist()

    assert [r["job_id"] for r in rows] == [r["job_id"] for r in reference]
    assert [r["runtime_seconds"] for r in rows] == [r["runtime_seconds"] for r in reference]


def test_a_table_without_vectors_is_unchanged() -> None:
    table = pa.table({"job_id": pa.array(["a", "b"]), "runtime_seconds": pa.array([1.0, 2.0])})

    assert table_to_rows(table) == table.to_pylist()


@pytest.mark.parametrize("fixed", [False, True])
def test_vector_columns_arrive_as_numpy_views(fixed: bool) -> None:
    """A view, not a copy: the point is that the row costs ~112 bytes, not ~33 KB (#164)."""
    table = _table([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], fixed=fixed)

    rows = table_to_rows(table)

    for row in rows:
        assert isinstance(row["embedding"], np.ndarray)
        assert row["embedding"].dtype == np.float32
    assert rows[0]["embedding"].base is rows[1]["embedding"].base  # slices of one matrix
    np.testing.assert_array_equal(rows[1]["embedding"], np.float32([4.0, 5.0, 6.0]))


def test_vector_rows_still_behave_like_sequences() -> None:
    """Models index and len() these, and _stack_embeddings assigns them into a matrix."""
    table = _table([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])

    rows = table_to_rows(table)

    assert len(rows[0]["embedding"]) == 3
    assert float(rows[0]["embedding"][1]) == 2.0
    matrix = np.empty((2, 3), dtype=np.float32)
    for i, row in enumerate(rows):
        matrix[i] = row["embedding"]
    np.testing.assert_array_equal(matrix, np.float32([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]))


def test_a_null_vector_falls_back_to_the_ordinary_path() -> None:
    """Validation belongs to the model, which reports the offending row index."""
    table = _table([[1.0, 2.0], None])

    rows = table_to_rows(table)

    assert rows[1]["embedding"] is None
    assert rows[0]["embedding"] == [1.0, 2.0]


def test_ragged_vectors_fall_back_to_the_ordinary_path() -> None:
    table = _table([[1.0, 2.0], [3.0]])

    rows = table_to_rows(table)

    assert rows[0]["embedding"] == [1.0, 2.0]
    assert rows[1]["embedding"] == [3.0]
