from __future__ import annotations

import pytest

from hpc_oda_commons.ingest.jobs_parquet.wizard import (
    normalize_duration_unit,
    normalize_memory_unit,
    normalize_timestamp_format,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("seconds", "seconds"),
        ("sec", "seconds"),
        ("minutes", "minutes"),
        ("min", "minutes"),
        ("hours", "hours"),
        ("hr", "hours"),
        ("HH:MM:SS", "hh:mm:ss"),
    ],
)
def test_normalize_duration_unit(value: str, expected: str) -> None:
    assert normalize_duration_unit(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("iso8601", "iso8601"),
        ("ISO", "iso8601"),
        ("epoch_s", "epoch_s"),
        ("epoch_ms", "epoch_ms"),
        ("epoch_us", "epoch_us"),
    ],
)
def test_normalize_timestamp_format(value: str, expected: str) -> None:
    assert normalize_timestamp_format(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("bytes", "bytes"),
        ("KB", "kb"),
        ("MB", "mb"),
        ("GB", "gb"),
        ("KiB", "kib"),
        ("MiB", "mib"),
        ("GiB", "gib"),
    ],
)
def test_normalize_memory_unit(value: str, expected: str) -> None:
    assert normalize_memory_unit(value) == expected


def test_normalize_duration_unit_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        normalize_duration_unit("weeks")


def test_normalize_timestamp_format_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        normalize_timestamp_format("excel")


def test_normalize_memory_unit_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        normalize_memory_unit("tb")
