from __future__ import annotations

from hpc_oda_commons.models.job_runtime_tfidf_knn.vectorization import (
    build_text_column,
    detect_text_columns,
)


def test_detect_text_columns_finds_strings_and_excludes_defaults() -> None:
    rows = [
        {
            "job_id": 1,
            "runtime_seconds": 100.0,
            "start_time": "2026-01-01T00:00:00Z",
            "end_time": "2026-01-01T01:00:00Z",
            "submit_time": "2026-01-01T00:00:00Z",
            "state": "COMPLETED",
            "user": "alice",
            "partition": "compute",
            "name": "my_job",
            "nodes_requested": 4,
        }
    ]
    cols = detect_text_columns(rows)
    assert "user" in cols
    assert "partition" in cols
    assert "name" in cols
    assert "job_id" not in cols
    assert "runtime_seconds" not in cols
    assert "start_time" not in cols
    assert "state" not in cols
    assert "nodes_requested" not in cols


def test_detect_text_columns_empty_rows() -> None:
    assert detect_text_columns([]) == []


def test_build_text_column_concatenates() -> None:
    rows = [
        {"user": "alice", "partition": "gpu", "name": "train"},
        {"user": "bob", "partition": "cpu", "name": "test"},
    ]
    texts = build_text_column(rows, ["user", "partition", "name"])
    assert texts == ["alice gpu train", "bob cpu test"]


def test_build_text_column_handles_missing_values() -> None:
    rows = [{"user": "alice"}]
    texts = build_text_column(rows, ["user", "partition"])
    assert texts == ["alice "]
