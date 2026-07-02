from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml
from typer.testing import CliRunner

from hpc_oda_commons.datasets.descriptor import Descriptor, Target
from hpc_oda_commons.datasets.normalize import (
    NormalizeError,
    normalize_target,
    target_to_mapping_spec,
)
from hpc_oda_commons.datasets.prepare import prepare_descriptor
from hpc_oda_commons.qst.cli import app
from hpc_oda_commons.schema.validator import validate_parquet_with_quality

# Canonical column -> source-field rule, mapping a Fugaku-ish raw table to oda.job.v0.2.0.
MAPPING = {
    "job_id": {"from": "jobid", "type": "hash_identifier"},
    "start_time": {"from": "sdt", "type": "timestamp", "format": "epoch_s"},
    "end_time": {"from": "edt", "type": "timestamp", "format": "epoch_s"},
    "runtime_seconds": {"from": "duration", "type": "duration", "unit": "seconds"},
    "maxpcon": {"from": "maxpcon"},
    "user": {"from": "usr", "type": "hash_identifier"},
    "partition": {"from": "partition"},
}


def _source_table() -> pa.Table:
    return pa.table(
        {
            "jobid": [1, 2, 3, 4],
            "sdt": [1_600_000_000, 1_600_000_100, 1_600_000_200, 1_600_000_300],
            "edt": [1_600_000_060, 1_600_000_400, 1_600_000_260, 1_600_000_900],
            "duration": [60, 300, 60, 600],
            "maxpcon": [120.0, 340.0, None, 500.0],
            "usr": ["alice", "bob", "alice", "carol"],
            "jnam": ["train", "infer", "train", "bench"],
            "cnumr": [4, 8, 4, 16],
            "nnumr": [1, 2, 1, 4],
            "partition": ["p1", "p2", "p1", "p2"],
        }
    )


def _target(**overrides) -> Target:
    payload = {
        "schema": "oda.job.v0.2.0",
        "mapping": MAPPING,
        "output": {"id": "test_out", "path": "data/datasets/test_out/data.parquet"},
    }
    payload.update(overrides)
    return Target.from_dict(payload)


def _intermediate(tmp_path: Path) -> Path:
    path = tmp_path / "inter.parquet"
    pq.write_table(_source_table(), path)
    return path


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _descriptor_payload(remote: Path) -> dict:
    return {
        "dataset_id": "dataset.test.prep",
        "schema_version": "oda.dataset.v0.1.0",
        "name": "Prepare Test Dataset",
        "version": "1.0.0",
        "description": "prepare end-to-end test descriptor",
        "problem_domains": ["job-runtime-prediction", "job-power-prediction"],
        "source": {
            "kind": "http",
            "resources": [
                {
                    "filename": "fugaku.parquet",
                    "url": remote.as_uri(),
                    "sha256": _sha_file(remote),
                    "bytes": remote.stat().st_size,
                }
            ],
        },
        "decode": {"format": "parquet"},
        "targets": [
            {
                "schema": "oda.job.v0.2.0",
                "capabilities": [
                    {"problem_domain": "job-power-prediction", "target_column": "maxpcon"}
                ],
                "mapping": MAPPING,
                "output": {"id": "test_prep", "path": "data/datasets/test_prep/data.parquet"},
            }
        ],
    }


# ---- normalize -------------------------------------------------------------


def test_target_to_mapping_spec() -> None:
    spec = target_to_mapping_spec(_target())
    assert spec["schema_version"] == "oda.mapping.v0.1.0"
    assert spec["output_schema_version"] == "oda.job.v0.2.0"
    assert spec["fields"]["start_time"] == {
        "source": "sdt",
        "transform": {"type": "timestamp", "format": "epoch_s"},
    }
    # A rule without a transform type maps to a plain passthrough source.
    assert spec["fields"]["maxpcon"] == {"source": "maxpcon"}


def test_normalize_produces_canonical_schema_valid_table(tmp_path: Path) -> None:
    out = tmp_path / "out.parquet"
    summary = normalize_target(_intermediate(tmp_path), _target(), out)

    table = pq.read_table(out)
    assert {"job_id", "start_time", "end_time", "runtime_seconds", "maxpcon"}.issubset(
        table.column_names
    )
    assert table.schema.field("start_time").type == pa.timestamp("us", tz="UTC")
    assert pa.types.is_floating(table.schema.field("runtime_seconds").type)
    assert summary["rows_final"] == 4
    # strict=True raises if the table is not schema-valid.
    validate_parquet_with_quality(out, schema_id="oda.job.v0.2.0", strict=True)


def test_normalize_filter_require_nonnull(tmp_path: Path) -> None:
    out = tmp_path / "out.parquet"
    normalize_target(_intermediate(tmp_path), _target(filter={"require_nonnull": ["maxpcon"]}), out)

    table = pq.read_table(out)
    assert table.num_rows == 3  # the null-maxpcon row is dropped
    assert table.column("maxpcon").null_count == 0


def test_normalize_filter_unknown_raises(tmp_path: Path) -> None:
    with pytest.raises(NormalizeError, match="unsupported filter"):
        normalize_target(_intermediate(tmp_path), _target(filter={"bogus": True}), tmp_path / "o")


def test_normalize_sample_head(tmp_path: Path) -> None:
    out = tmp_path / "out.parquet"
    normalize_target(_intermediate(tmp_path), _target(sample={"rows": 2, "strategy": "head"}), out)
    assert pq.read_table(out).num_rows == 2


def test_normalize_sample_random_is_deterministic(tmp_path: Path) -> None:
    sample = {"rows": 2, "strategy": "random", "seed": 7}
    first = tmp_path / "a.parquet"
    second = tmp_path / "b.parquet"
    normalize_target(_intermediate(tmp_path), _target(sample=sample), first)
    normalize_target(_intermediate(tmp_path), _target(sample=sample), second)

    a = pq.read_table(first).column("job_id").to_pylist()
    b = pq.read_table(second).column("job_id").to_pylist()
    assert len(a) == 2
    assert a == b


def test_normalize_sample_stratified(tmp_path: Path) -> None:
    out = tmp_path / "out.parquet"
    sample = {"rows": 2, "strategy": "stratified", "by": ["partition"], "seed": 1}
    normalize_target(_intermediate(tmp_path), _target(sample=sample), out)
    assert pq.read_table(out).num_rows <= 2


def test_normalize_select_projection(tmp_path: Path) -> None:
    out = tmp_path / "out.parquet"
    keep = ["job_id", "start_time", "end_time", "runtime_seconds", "maxpcon"]
    normalize_target(_intermediate(tmp_path), _target(select=keep), out)
    assert set(pq.read_table(out).column_names) == set(keep)


def test_normalize_select_dropping_required_raises(tmp_path: Path) -> None:
    with pytest.raises(NormalizeError, match="required job fields"):
        normalize_target(
            _intermediate(tmp_path), _target(select=["job_id", "maxpcon"]), tmp_path / "o"
        )


def test_normalize_synthesize_derive_timedelta(tmp_path: Path) -> None:
    # Atlas-shaped source: no job_id column, no runtime column, walltime as a pandas
    # timedelta string, timestamps with a non-UTC offset.
    src = pa.table(
        {
            "sdt": ["2011-10-27 10:50:10-06:00", "2011-10-27 11:00:00-06:00"],
            "edt": ["2011-10-27 10:51:50-06:00", "2011-10-27 11:05:00-06:00"],
            "walltime": ["365 days 00:00:00.000000000", "0 days 01:00:00.000000000"],
        }
    )
    inter = tmp_path / "inter.parquet"
    pq.write_table(src, inter)
    target = Target.from_dict(
        {
            "schema": "oda.job.v0.2.0",
            "mapping": {
                "job_id": {"synthesize": "row_index"},
                "start_time": {"from": "sdt", "type": "timestamp", "format": "iso8601"},
                "end_time": {"from": "edt", "type": "timestamp", "format": "iso8601"},
                "runtime_seconds": {"derive": "end_time - start_time"},
                "requested_seconds": {"from": "walltime", "type": "duration", "unit": "timedelta"},
            },
            "output": {"id": "syn", "path": "data/datasets/syn/data.parquet"},
        }
    )
    out = tmp_path / "out.parquet"
    normalize_target(inter, target, out)

    rows = pq.read_table(out).to_pylist()
    assert [r["job_id"] for r in rows] == [0, 1]  # synthesized surrogate ids
    assert [r["runtime_seconds"] for r in rows] == [100.0, 300.0]  # derived end - start
    assert [r["requested_seconds"] for r in rows] == [31536000.0, 3600.0]  # timedelta -> seconds
    validate_parquet_with_quality(out, schema_id="oda.job.v0.2.0", strict=True)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("365 days 00:00:00.000000000", 31_536_000.0),
        ("0 days 01:00:00.000000000", 3600.0),
        ("2 days 03:04:05", 183_845.0),
        ("01:00:00", 3600.0),
        ("", None),
    ],
)
def test_duration_timedelta_parse(value: str, expected: float | None) -> None:
    from hpc_oda_commons.ingest.jobs_parquet.apply import _duration_to_seconds

    assert _duration_to_seconds(value, "timedelta") == expected


def test_duration_timedelta_invalid_raises() -> None:
    from hpc_oda_commons.ingest.jobs_parquet.apply import _duration_to_seconds

    with pytest.raises(ValueError, match="Invalid timedelta"):
        _duration_to_seconds("not-a-duration", "timedelta")


def test_normalize_arrow_duration_column_to_seconds(tmp_path: Path) -> None:
    # A native Arrow duration column (as in NLR Kestrel's wallclock_req) -> seconds.
    src = pa.table(
        {
            "id": ["a", "b"],
            "s": pa.array([1_600_000_000, 1_600_000_100], pa.int64()),
            "e": pa.array([1_600_000_060, 1_600_000_400], pa.int64()),
            "req": pa.array([3_600_000_000_000, 7_200_000_000_000], pa.duration("ns")),  # 1h, 2h
        }
    )
    inter = tmp_path / "inter.parquet"
    pq.write_table(src, inter)
    target = Target.from_dict(
        {
            "schema": "oda.job.v0.2.0",
            "mapping": {
                "job_id": {"from": "id"},
                "start_time": {"from": "s", "type": "timestamp", "format": "epoch_s"},
                "end_time": {"from": "e", "type": "timestamp", "format": "epoch_s"},
                "runtime_seconds": {"derive": "end_time - start_time"},
                "requested_seconds": {"from": "req", "type": "duration"},
            },
            "output": {"id": "dur", "path": "data/datasets/dur/data.parquet"},
        }
    )
    out = tmp_path / "out.parquet"
    normalize_target(inter, target, out)

    rows = pq.read_table(out).to_pylist()
    assert [r["requested_seconds"] for r in rows] == [3600.0, 7200.0]
    assert [r["runtime_seconds"] for r in rows] == [60.0, 300.0]


# ---- prepare (end to end) --------------------------------------------------


def test_prepare_descriptor_end_to_end(tmp_path: Path) -> None:
    remote = tmp_path / "remote" / "fugaku.parquet"
    remote.parent.mkdir(parents=True)
    pq.write_table(_source_table(), remote)

    descriptor = Descriptor.from_dict(_descriptor_payload(remote))
    results = prepare_descriptor(
        descriptor, cache_dir=tmp_path / "cache", out_root=tmp_path / "out"
    )

    assert len(results) == 1
    result = results[0]
    assert result.table_path.exists()
    assert result.manifest_path.exists()
    assert result.quality_path.exists()
    validate_parquet_with_quality(result.table_path, schema_id="oda.job.v0.2.0", strict=True)

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifact"]["dataset_id"] == "dataset.test.prep"
    assert manifest["input_schema_version"] == "oda.job.v0.2.0"


def test_prepare_unknown_target_schema_raises(tmp_path: Path) -> None:
    remote = tmp_path / "remote" / "fugaku.parquet"
    remote.parent.mkdir(parents=True)
    pq.write_table(_source_table(), remote)
    descriptor = Descriptor.from_dict(_descriptor_payload(remote))

    with pytest.raises(ValueError, match="no target matches"):
        prepare_descriptor(
            descriptor,
            cache_dir=tmp_path / "cache",
            out_root=tmp_path / "out",
            target_schema="oda.telemetry.v0.1.0",
        )


def test_cli_datasets_prepare(tmp_path: Path) -> None:
    remote = tmp_path / "remote" / "fugaku.parquet"
    remote.parent.mkdir(parents=True)
    pq.write_table(_source_table(), remote)

    desc_path = tmp_path / "desc.yml"
    desc_path.write_text(yaml.safe_dump(_descriptor_payload(remote)), encoding="utf-8")
    out_root = tmp_path / "out"

    result = CliRunner().invoke(
        app,
        [
            "datasets",
            "prepare",
            str(desc_path),
            "--cache",
            str(tmp_path / "cache"),
            "--out",
            str(out_root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (out_root / "data" / "datasets" / "test_prep" / "data.parquet").exists()
    assert (out_root / "data" / "datasets" / "test_prep" / "manifest.json").exists()
