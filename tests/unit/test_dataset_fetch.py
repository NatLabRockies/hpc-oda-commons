from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from hpc_oda_commons.datasets.descriptor import Descriptor
from hpc_oda_commons.datasets.fetch import (
    ChecksumMismatch,
    ManualFetchRequired,
    OfflineError,
    SizeLimitExceeded,
    UnknownSizeError,
    fetch_descriptor,
    parse_size,
)
from hpc_oda_commons.datasets.fetch.base import FetchError, select_resources
from hpc_oda_commons.qst.cli import app


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _remote(dirpath: Path, name: str, content: bytes) -> dict:
    """Write a fake 'remote' file and return a resource dict pointing at it via file://."""
    path = dirpath / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {"filename": name, "url": path.as_uri(), "sha256": _sha(content), "bytes": len(content)}


def _descriptor(source: dict, dataset_id: str = "dataset.test.x") -> Descriptor:
    return Descriptor.from_dict(
        {
            "dataset_id": dataset_id,
            "name": "Test Dataset",
            "version": "1.0.0",
            "description": "test descriptor",
            "problem_domains": ["job-runtime-prediction"],
            "source": source,
            "decode": {"format": "parquet"},
            "targets": [],
        }
    )


def test_fetch_http_file_url(tmp_path: Path) -> None:
    res = _remote(tmp_path / "remote", "data.parquet", b"hello world")
    desc = _descriptor({"kind": "http", "resources": [res]})

    result = fetch_descriptor(desc, cache_dir=tmp_path / "cache")

    assert len(result.resources) == 1
    cached = result.resources[0]
    assert cached.path.read_bytes() == b"hello world"
    assert cached.reused is False
    lock = json.loads(result.lockfile_path.read_text(encoding="utf-8"))
    assert lock["dataset_id"] == "dataset.test.x"
    assert lock["resources"][0]["sha256"] == res["sha256"]


def test_fetch_is_idempotent(tmp_path: Path) -> None:
    res = _remote(tmp_path / "remote", "a.bin", b"abc")
    desc = _descriptor({"kind": "http", "resources": [res]})
    cache = tmp_path / "cache"

    fetch_descriptor(desc, cache_dir=cache)
    second = fetch_descriptor(desc, cache_dir=cache)

    assert second.resources[0].reused is True


def test_checksum_mismatch_raises_and_cleans(tmp_path: Path) -> None:
    res = _remote(tmp_path / "remote", "a.bin", b"abc")
    res["sha256"] = "0" * 64
    desc = _descriptor({"kind": "http", "resources": [res]})
    cache = tmp_path / "cache"

    with pytest.raises(ChecksumMismatch):
        fetch_descriptor(desc, cache_dir=cache)
    assert not (cache / "dataset.test.x" / "raw" / "a.bin").exists()


def test_size_guardrail_refuses_then_allows(tmp_path: Path) -> None:
    r1 = _remote(tmp_path / "remote", "a.bin", b"x" * 100)
    r2 = _remote(tmp_path / "remote", "b.bin", b"y" * 100)
    desc = _descriptor({"kind": "http", "resources": [r1, r2]})
    cache = tmp_path / "cache"

    with pytest.raises(SizeLimitExceeded):
        fetch_descriptor(desc, cache_dir=cache, max_bytes=150)

    result = fetch_descriptor(desc, cache_dir=cache, max_bytes=150, allow_large=True)
    assert len(result.resources) == 2


def test_unknown_size_requires_confirm(tmp_path: Path) -> None:
    res = _remote(tmp_path / "remote", "a.bin", b"abc")
    del res["bytes"]
    desc = _descriptor({"kind": "http", "resources": [res]})
    cache = tmp_path / "cache"

    with pytest.raises(UnknownSizeError):
        fetch_descriptor(desc, cache_dir=cache)

    result = fetch_descriptor(desc, cache_dir=cache, assume_yes=True)
    assert result.unknown_size is True


def test_offline_uses_cache_or_errors(tmp_path: Path) -> None:
    res = _remote(tmp_path / "remote", "a.bin", b"abc")
    desc = _descriptor({"kind": "http", "resources": [res]})
    cache = tmp_path / "cache"

    with pytest.raises(OfflineError):
        fetch_descriptor(desc, cache_dir=cache, offline=True)

    fetch_descriptor(desc, cache_dir=cache)  # populate the cache
    result = fetch_descriptor(desc, cache_dir=cache, offline=True)
    assert result.resources[0].reused is True


def test_slice_selection(tmp_path: Path) -> None:
    a = _remote(tmp_path / "remote", "23_04.parquet", b"a")
    b = _remote(tmp_path / "remote", "21_04.parquet", b"bb")
    source = {
        "kind": "http",
        "resources": [a, b],
        "slices": {
            "default": "recent",
            "available": {
                "recent": {"include": ["23_*.parquet"]},
                "full": {"include": ["*.parquet"]},
            },
        },
    }

    selected, name = select_resources(source, slice_name=None, select_all=False)
    assert name == "recent"
    assert [r["filename"] for r in selected] == ["23_04.parquet"]

    full, _ = select_resources(source, slice_name="full", select_all=False)
    assert len(full) == 2

    everything, all_name = select_resources(source, slice_name=None, select_all=True)
    assert all_name == "all"
    assert len(everything) == 2

    with pytest.raises(FetchError):
        select_resources(source, slice_name="nope", select_all=False)

    result = fetch_descriptor(_descriptor(source), cache_dir=tmp_path / "cache")
    assert [r.filename for r in result.resources] == ["23_04.parquet"]
    assert result.slice == "recent"


def test_manual_requires_file_then_from_dir(tmp_path: Path) -> None:
    content = b"gated-bytes"
    source = {
        "kind": "manual",
        "instructions": "Register at the portal to download.",
        "resources": [
            {"filename": "gated.parquet", "sha256": _sha(content), "bytes": len(content)}
        ],
    }
    desc = _descriptor(source)
    cache = tmp_path / "cache"

    with pytest.raises(ManualFetchRequired):
        fetch_descriptor(desc, cache_dir=cache)

    supplied = tmp_path / "supplied"
    supplied.mkdir()
    (supplied / "gated.parquet").write_bytes(content)
    result = fetch_descriptor(desc, cache_dir=cache, source_dir=supplied)
    assert result.resources[0].path.read_bytes() == content


def test_manual_supplied_file_bad_checksum(tmp_path: Path) -> None:
    content = b"gated-bytes"
    source = {
        "kind": "manual",
        "instructions": "...",
        "resources": [{"filename": "g.parquet", "sha256": _sha(content), "bytes": len(content)}],
    }
    supplied = tmp_path / "supplied"
    supplied.mkdir()
    (supplied / "g.parquet").write_bytes(b"WRONG")

    with pytest.raises(ChecksumMismatch):
        fetch_descriptor(_descriptor(source), cache_dir=tmp_path / "cache", source_dir=supplied)


def test_parse_size() -> None:
    assert parse_size(1024) == 1024
    assert parse_size("500") == 500
    assert parse_size("5GB") == 5 * 10**9
    assert parse_size("500MB") == 5 * 10**8
    assert parse_size("2GiB") == 2 * 2**30
    assert parse_size("1KB") == 1000


def _cli_descriptor_payload(res: dict, dataset_id: str, with_capability: bool) -> dict:
    target: dict = {
        "schema": "oda.job.v0.2.0",
        "mapping": {"runtime_seconds": {"from": "duration", "type": "duration", "unit": "seconds"}},
        "output": {"id": "out", "path": "data/datasets/out/data.parquet"},
    }
    if with_capability:
        target["capabilities"] = [
            {"problem_domain": "job-runtime-prediction", "target_column": "runtime_seconds"}
        ]
    return {
        "dataset_id": dataset_id,
        "schema_version": "oda.dataset.v0.1.0",
        "name": "CLI Test Dataset",
        "version": "1.0.0",
        "description": "cli test descriptor",
        "problem_domains": ["job-runtime-prediction"],
        "source": {"kind": "http", "resources": [res]},
        "decode": {"format": "parquet"},
        "targets": [target],
    }


def test_cli_datasets_fetch(tmp_path: Path) -> None:
    res = _remote(tmp_path / "remote", "data.parquet", b"payload-bytes")
    payload = _cli_descriptor_payload(res, "dataset.test.cli", with_capability=True)
    desc_path = tmp_path / "desc.yml"
    desc_path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    cache = tmp_path / "cache"

    result = CliRunner().invoke(app, ["datasets", "fetch", str(desc_path), "--cache", str(cache)])

    assert result.exit_code == 0, result.output
    assert "downloaded" in result.output
    assert (cache / "dataset.test.cli" / "raw" / "data.parquet").exists()


def test_cli_size_guardrail_exit_code(tmp_path: Path) -> None:
    res = _remote(tmp_path / "remote", "big.parquet", b"x" * 5000)
    payload = _cli_descriptor_payload(res, "dataset.test.big", with_capability=False)
    desc_path = tmp_path / "big.yml"
    desc_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["datasets", "fetch", str(desc_path), "--cache", str(tmp_path / "c"), "--max-size", "1KB"],
    )

    assert result.exit_code == 2
    assert "Refusing to download" in result.output
