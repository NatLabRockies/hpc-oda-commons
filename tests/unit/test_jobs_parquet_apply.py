from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hpc_oda_commons.ingest.jobs_parquet.apply import apply_mapping_spec
from hpc_oda_commons.kernel.artifacts.mapping_spec import new_mapping_spec, write_mapping_spec


def _write_parquet(path: Path) -> None:
    rows = [
        {
            "JobID": 1,
            "StartTime": "2026-01-01T00:00:00Z",
            "EndTime": "2026-01-01T00:05:00Z",
            "SubmitTime": "2026-01-01T00:00:00Z",
            "State": "COMPLETED",
            "User": "alice",
            "Elapsed": 300.0,
        },
        {
            "JobID": 2,
            "StartTime": "2026-01-01T01:00:00Z",
            "EndTime": None,
            "SubmitTime": "2026-01-01T01:00:00Z",
            "State": "RUNNING",
            "User": "bob",
            "Elapsed": None,
        },
    ]
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)


def test_apply_mapping_spec_derives_runtime(tmp_path: Path) -> None:
    input_path = tmp_path / "jobs.parquet"
    _write_parquet(input_path)

    mapping = new_mapping_spec(
        kind="jobs_parquet",
        output_schema_version="oda.job.v0.1.0",
        fields={
            "job_id": {"source": "JobID"},
            "start_time": {
                "source": "StartTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "end_time": {
                "source": "EndTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "runtime_seconds": {"derive": "end_time - start_time"},
            "submit_time": {
                "source": "SubmitTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "state": {"source": "State"},
            "user": {"source": "User", "transform": {"type": "hash_identifier"}},
        },
    )
    mapping_path = tmp_path / "mapping.yml"
    write_mapping_spec(mapping_path, mapping, validate=True)

    out_path = tmp_path / "out.parquet"
    summary = apply_mapping_spec(input_path, mapping_path, out_path)
    assert summary["rows_kept"] == 1
    assert summary["rows_skipped"] == 1

    table = pq.read_table(out_path)
    rows = table.to_pylist()
    assert rows[0]["job_id"] == 1
    assert rows[0]["runtime_seconds"] == 300.0
    assert rows[0]["submit_time"] == datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert rows[0]["user"] != "alice"


def test_apply_mapping_spec_filters_by_state_allowlist(tmp_path: Path) -> None:
    input_path = tmp_path / "jobs.parquet"
    rows = [
        {
            "JobID": 1,
            "StartTime": "2026-01-01T00:00:00Z",
            "EndTime": "2026-01-01T00:05:00Z",
            "SubmitTime": "2026-01-01T00:00:00Z",
            "State": "COMPLETED",
            "Elapsed": 300.0,
        },
        {
            "JobID": 2,
            "StartTime": "2026-01-01T01:00:00Z",
            "EndTime": "2026-01-01T01:04:00Z",
            "SubmitTime": "2026-01-01T01:00:00Z",
            "State": "FAILED",
            "Elapsed": 240.0,
        },
        {
            "JobID": 3,
            "StartTime": "2026-01-01T02:00:00Z",
            "EndTime": "2026-01-01T02:03:00Z",
            "SubmitTime": "2026-01-01T02:00:00Z",
            "State": "RUNNING",
            "Elapsed": 180.0,
        },
    ]
    pq.write_table(pa.Table.from_pylist(rows), input_path)

    mapping = new_mapping_spec(
        kind="jobs_parquet",
        output_schema_version="oda.job.v0.1.0",
        fields={
            "job_id": {"source": "JobID"},
            "start_time": {
                "source": "StartTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "end_time": {
                "source": "EndTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "runtime_seconds": {
                "source": "Elapsed",
                "transform": {"type": "duration", "unit": "seconds"},
            },
            "submit_time": {
                "source": "SubmitTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "state": {"source": "State"},
        },
    )
    mapping_path = tmp_path / "mapping.yml"
    write_mapping_spec(mapping_path, mapping, validate=True)

    out_path = tmp_path / "out.parquet"
    summary = apply_mapping_spec(
        input_path,
        mapping_path,
        out_path,
        state_allowlist={"COMPLETED", "FAILED"},
    )

    table = pq.read_table(out_path)
    out_rows = table.to_pylist()
    assert len(out_rows) == 2
    assert {row["state"] for row in out_rows} == {"COMPLETED", "FAILED"}
    assert summary["rows_total"] == 3
    assert summary["rows_kept"] == 2
    assert summary["rows_skipped_state_filter"] == 1
    assert summary["state_filter_values"] == ["COMPLETED", "FAILED"]


def test_apply_mapping_spec_accepts_space_separated_timestamp_with_short_tz(tmp_path: Path) -> None:
    input_path = tmp_path / "jobs.parquet"
    rows = [
        {
            "JobID": 1,
            "StartTime": "2024-04-07 02:28:25+09",
            "EndTime": "2024-04-07 02:33:25+09",
            "SubmitTime": "2024-04-07 02:20:00+09",
            "Elapsed": 300.0,
            "State": "COMPLETED",
        }
    ]
    pq.write_table(pa.Table.from_pylist(rows), input_path)

    mapping = new_mapping_spec(
        kind="jobs_parquet",
        output_schema_version="oda.job.v0.1.0",
        fields={
            "job_id": {"source": "JobID"},
            "start_time": {
                "source": "StartTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "end_time": {
                "source": "EndTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "runtime_seconds": {
                "source": "Elapsed",
                "transform": {"type": "duration", "unit": "seconds"},
            },
            "submit_time": {
                "source": "SubmitTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "state": {"source": "State"},
        },
    )
    mapping_path = tmp_path / "mapping.yml"
    write_mapping_spec(mapping_path, mapping, validate=True)

    out_path = tmp_path / "out.parquet"
    _summary = apply_mapping_spec(input_path, mapping_path, out_path)

    table = pq.read_table(out_path)
    out_rows = table.to_pylist()
    assert out_rows[0]["start_time"] == datetime(2024, 4, 6, 17, 28, 25, tzinfo=timezone.utc)
    assert out_rows[0]["end_time"] == datetime(2024, 4, 6, 17, 33, 25, tzinfo=timezone.utc)


def test_apply_mapping_spec_omits_optional_null_fields(tmp_path: Path) -> None:
    input_path = tmp_path / "jobs.parquet"
    rows = [
        {
            "JobID": 1,
            "StartTime": "2026-01-01T00:00:00Z",
            "EndTime": "2026-01-01T00:05:00Z",
            "SubmitTime": "2026-01-01T00:00:00Z",
            "State": "COMPLETED",
            "Partition": None,
            "QOS": None,
            "Elapsed": 300.0,
        }
    ]
    pq.write_table(pa.Table.from_pylist(rows), input_path)

    mapping = new_mapping_spec(
        kind="jobs_parquet",
        output_schema_version="oda.job.v0.1.0",
        fields={
            "job_id": {"source": "JobID"},
            "start_time": {
                "source": "StartTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "end_time": {
                "source": "EndTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "runtime_seconds": {
                "source": "Elapsed",
                "transform": {"type": "duration", "unit": "seconds"},
            },
            "submit_time": {
                "source": "SubmitTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "state": {"source": "State"},
            "partition": {"source": "Partition"},
            "qos": {"source": "QOS"},
        },
    )
    mapping_path = tmp_path / "mapping.yml"
    write_mapping_spec(mapping_path, mapping, validate=True)

    out_path = tmp_path / "out.parquet"
    apply_mapping_spec(input_path, mapping_path, out_path)
    out_rows = pq.read_table(out_path).to_pylist()
    assert "partition" not in out_rows[0]
    assert "qos" not in out_rows[0]


# --------------------------------------------------------------------------- #
# Parity: the column-wise implementation must match the prior row-at-a-time
# logic's *intended* contract. We keep an independent row-based reference here
# (reusing the same element-wise transform helpers) and compare across edge
# cases + randomized multi-batch input.
#
# Note: the original code wrote via pa.Table.from_pylist, which infers the
# schema from the FIRST row's keys only -- so an optional column empty in the
# first kept row was silently dropped even when later rows populated it (a
# latent data-loss bug; see test_apply_keeps_optional_populated_in_later_rows).
# The reference below normalizes keys to the union before writing, encoding the
# documented intent ("drop an optional column only when empty in every row"),
# which the vectorized implementation now matches.
# --------------------------------------------------------------------------- #


def _reference_row_based(
    input_path: Path,
    mapping_path: Path,
    out_path: Path,
    *,
    batch_size: int = 50_000,
    skip_incomplete: bool = True,
    state_allowlist: set[str] | None = None,
) -> dict:
    """The original row-at-a-time algorithm, kept as a parity oracle."""
    from hpc_oda_commons.ingest.jobs_parquet.apply import _apply_transform, _derive_runtime
    from hpc_oda_commons.kernel.artifacts.mapping_spec import read_mapping_spec

    mapping = read_mapping_spec(mapping_path, validate=True)
    fields = mapping.get("fields", {})
    required = {"job_id", "start_time", "end_time", "runtime_seconds"}
    out_rows: list[dict] = []
    total = kept = skipped = skipped_state = 0

    parquet = pq.ParquetFile(input_path)
    for batch in parquet.iter_batches(batch_size=batch_size):
        table = pa.Table.from_batches([batch])
        for row in table.to_pylist():
            total += 1
            out_row: dict = {}
            for field, spec in fields.items():
                source = spec.get("source")
                value = row.get(source) if source else None
                out_row[field] = _apply_transform(value, spec.get("transform"))
            if out_row.get("runtime_seconds") in (None, ""):
                if fields.get("runtime_seconds", {}).get("derive") == "end_time - start_time":
                    out_row["runtime_seconds"] = _derive_runtime(out_row)
            if state_allowlist is not None:
                sv = out_row.get("state")
                if sv is None or str(sv) not in state_allowlist:
                    skipped_state += 1
                    continue
            if skip_incomplete and any(out_row.get(f) in (None, "") for f in required):
                skipped += 1
                continue
            for key in list(out_row.keys()):
                if key in required:
                    continue
                if out_row.get(key) in (None, ""):
                    out_row.pop(key, None)
            kept += 1
            out_rows.append(out_row)

    if not out_rows:
        raise ValueError("No rows produced after applying mapping spec.")
    # Normalize to the union of keys so an optional column populated in any kept
    # row survives (documented intent), rather than depending on the first row.
    all_keys: list[str] = []
    seen: set[str] = set()
    for r in out_rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                all_keys.append(k)
    normalized = [{k: r.get(k) for k in all_keys} for r in out_rows]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(normalized), out_path)
    return {
        "rows_total": total,
        "rows_kept": kept,
        "rows_skipped": skipped,
        "rows_skipped_state_filter": skipped_state,
        "state_filter_values": sorted(state_allowlist) if state_allowlist is not None else [],
    }


def _full_mapping():
    return new_mapping_spec(
        kind="jobs_parquet",
        output_schema_version="oda.job.v0.1.0",
        fields={
            "job_id": {"source": "JobID"},
            "submit_time": {
                "source": "SubmitTime",
                "transform": {"type": "timestamp", "format": "epoch_s"},
            },
            "start_time": {
                "source": "StartTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "end_time": {
                "source": "EndTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "runtime_seconds": {"derive": "end_time - start_time"},
            "state": {"source": "State"},
            "user": {"source": "User", "transform": {"type": "hash_identifier"}},
            "allocated_cpus": {"source": "NCPUS"},
            "memory_mb": {"source": "ReqMem", "transform": {"type": "memory_slurm"}},
            "partition": {"source": "Partition"},
        },
    )


def _run_both(tmp_path: Path, rows: list[dict], mapping, **kwargs):
    inp = tmp_path / "in.parquet"
    pq.write_table(pa.Table.from_pylist(rows), inp)
    mp = tmp_path / "map.yml"
    write_mapping_spec(mp, mapping, validate=True)

    ref_out = tmp_path / "ref.parquet"
    new_out = tmp_path / "new.parquet"
    ref_summary = _reference_row_based(inp, mp, ref_out, **kwargs)
    new_summary = apply_mapping_spec(inp, mp, new_out, **kwargs)
    return (
        ref_summary,
        new_summary,
        pq.read_table(ref_out).to_pylist(),
        pq.read_table(new_out).to_pylist(),
    )


def test_apply_parity_edge_cases(tmp_path: Path) -> None:
    rows = [
        # complete row
        {
            "JobID": 1,
            "SubmitTime": 1_700_000_000,
            "StartTime": "2026-01-01T00:00:00Z",
            "EndTime": "2026-01-01T00:05:00Z",
            "State": "COMPLETED",
            "User": "alice",
            "NCPUS": 4,
            "ReqMem": "2G",
            "Partition": "debug",
        },
        # empty-string required (StartTime "") -> must be skipped as incomplete
        {
            "JobID": 2,
            "SubmitTime": 1_700_000_100,
            "StartTime": "",
            "EndTime": "2026-01-01T01:00:00Z",
            "State": "COMPLETED",
            "User": "bob",
            "NCPUS": 2,
            "ReqMem": "1G",
            "Partition": "",
        },
        # missing end -> runtime derive fails -> incomplete -> skipped
        {
            "JobID": 3,
            "SubmitTime": 1_700_000_200,
            "StartTime": "2026-01-01T02:00:00Z",
            "EndTime": None,
            "State": "FAILED",
            "User": "alice",
            "NCPUS": 1,
            "ReqMem": "512M",
            "Partition": "compute",
        },
        # complete row, empty optional partition -> column kept (null here, value above)
        {
            "JobID": 4,
            "SubmitTime": 1_700_000_300,
            "StartTime": "2026-01-01T03:00:00Z",
            "EndTime": "2026-01-01T03:10:00Z",
            "State": "COMPLETED",
            "User": "carol",
            "NCPUS": 8,
            "ReqMem": "4G",
            "Partition": "",
        },
    ]
    ref_s, new_s, ref_rows, new_rows = _run_both(tmp_path, rows, _full_mapping())
    assert new_s == ref_s
    assert new_rows == ref_rows
    # sanity: row 1 kept, partition present (some rows non-empty), row 2/3 skipped
    assert new_s["rows_kept"] == 2
    assert new_s["rows_skipped"] == 2
    assert "partition" in new_rows[0]


def test_apply_parity_all_null_optional_dropped(tmp_path: Path) -> None:
    rows = [
        {
            "JobID": 1,
            "SubmitTime": 1_700_000_000,
            "StartTime": "2026-01-01T00:00:00Z",
            "EndTime": "2026-01-01T00:05:00Z",
            "State": "COMPLETED",
            "User": "a",
            "NCPUS": 1,
            "ReqMem": "1G",
            "Partition": "",
        },
        {
            "JobID": 2,
            "SubmitTime": 1_700_000_100,
            "StartTime": "2026-01-01T01:00:00Z",
            "EndTime": "2026-01-01T01:05:00Z",
            "State": "COMPLETED",
            "User": "b",
            "NCPUS": 2,
            "ReqMem": "2G",
            "Partition": None,
        },
    ]
    _, new_s, ref_rows, new_rows = _run_both(tmp_path, rows, _full_mapping())
    assert new_rows == ref_rows
    assert "partition" not in new_rows[0]  # empty in every kept row -> dropped


def test_apply_parity_state_filter_and_multibatch(tmp_path: Path) -> None:
    import random

    rng = random.Random(1234)
    states = ["COMPLETED", "FAILED", "RUNNING", "CANCELLED"]
    rows = []
    for i in range(60):
        complete = rng.random() > 0.2
        rows.append(
            {
                "JobID": i,
                "SubmitTime": 1_700_000_000 + i,
                "StartTime": f"2026-01-01T{i % 24:02d}:00:00Z" if complete else None,
                "EndTime": f"2026-01-01T{i % 24:02d}:30:00Z",
                "State": states[i % 4],
                "User": f"user{i % 7}",
                "NCPUS": 1 + (i % 16),
                "ReqMem": f"{1 + (i % 8)}G",
                "Partition": "debug" if i % 3 else "",
            }
        )
    ref_s, new_s, ref_rows, new_rows = _run_both(
        tmp_path, rows, _full_mapping(), batch_size=7, state_allowlist={"COMPLETED", "FAILED"}
    )
    assert new_s == ref_s
    assert new_rows == ref_rows


def test_apply_keeps_optional_populated_in_later_rows(tmp_path: Path) -> None:
    """Regression: an optional column empty in the FIRST kept row but populated
    later must survive. The prior from_pylist-based code dropped it (data loss);
    the vectorized code keeps it with nulls for the empty rows."""
    rows = [
        {
            "JobID": 1,
            "SubmitTime": 1_700_000_000,
            "StartTime": "2026-01-01T00:00:00Z",
            "EndTime": "2026-01-01T00:05:00Z",
            "State": "COMPLETED",
            "User": "a",
            "NCPUS": 1,
            "ReqMem": "1G",
            "Partition": "",
        },  # first kept row: empty partition
        {
            "JobID": 2,
            "SubmitTime": 1_700_000_100,
            "StartTime": "2026-01-01T01:00:00Z",
            "EndTime": "2026-01-01T01:05:00Z",
            "State": "COMPLETED",
            "User": "b",
            "NCPUS": 2,
            "ReqMem": "2G",
            "Partition": "compute",
        },  # later row: populated
    ]
    inp = tmp_path / "in.parquet"
    pq.write_table(pa.Table.from_pylist(rows), inp)
    mp = tmp_path / "map.yml"
    write_mapping_spec(mp, _full_mapping(), validate=True)

    apply_mapping_spec(inp, mp, tmp_path / "out.parquet")
    out = pq.read_table(tmp_path / "out.parquet").to_pylist()
    assert "partition" in out[0]
    assert out[0]["partition"] is None  # empty "" emitted as null
    assert out[1]["partition"] == "compute"


def _memory_slurm_mapping():
    return new_mapping_spec(
        kind="jobs_parquet",
        output_schema_version="oda.job.v0.1.0",
        fields={
            "job_id": {"source": "JobID"},
            "start_time": {
                "source": "StartTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "end_time": {
                "source": "EndTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "runtime_seconds": {"derive": "end_time - start_time"},
            "memory_mb": {"source": "ReqMem", "transform": {"type": "memory_slurm"}},
        },
    )


def _row(job_id: int, hour: int, reqmem) -> dict:
    return {
        "JobID": job_id,
        "StartTime": f"2026-01-01T{hour:02d}:00:00Z",
        "EndTime": f"2026-01-01T{hour:02d}:05:00Z",
        "ReqMem": reqmem,
    }


def test_apply_memory_slurm_vectorized_values(tmp_path: Path) -> None:
    rows = [_row(1, 0, "160G"), _row(2, 1, "  2g  "), _row(3, 2, "512K"), _row(4, 3, "4096")]
    inp = tmp_path / "in.parquet"
    pq.write_table(pa.Table.from_pylist(rows), inp)
    mp = tmp_path / "map.yml"
    write_mapping_spec(mp, _memory_slurm_mapping(), validate=True)

    apply_mapping_spec(inp, mp, tmp_path / "out.parquet")
    out = pq.read_table(tmp_path / "out.parquet").to_pylist()
    assert [r["memory_mb"] for r in out] == [163840.0, 2048.0, 0.5, 4096.0]


def test_apply_memory_slurm_malformed_becomes_null_not_crash(tmp_path: Path) -> None:
    """Behavior change vs prior code: a malformed multi-dot SLURM memory value
    becomes null instead of crashing the whole ingest with ValueError."""
    rows = [_row(1, 0, "1.2.3G"), _row(2, 1, "8G")]
    inp = tmp_path / "in.parquet"
    pq.write_table(pa.Table.from_pylist(rows), inp)
    mp = tmp_path / "map.yml"
    write_mapping_spec(mp, _memory_slurm_mapping(), validate=True)

    apply_mapping_spec(inp, mp, tmp_path / "out.parquet")  # must not raise
    out = pq.read_table(tmp_path / "out.parquet").to_pylist()
    assert out[0]["memory_mb"] is None
    assert out[1]["memory_mb"] == 8192.0


def test_apply_epoch_s_yields_correct_utc_instant(tmp_path: Path) -> None:
    """The epoch_s transform must produce the correct tz-aware datetime instant,
    stored as an Arrow timestamp column (not an ISO string)."""
    epoch = 1_700_000_000
    rows = [
        {
            "JobID": 1,
            "Sub": epoch,
            "StartTime": "2026-01-01T00:00:00Z",
            "EndTime": "2026-01-01T00:05:00Z",
        }
    ]
    inp = tmp_path / "in.parquet"
    pq.write_table(pa.Table.from_pylist(rows), inp)
    mapping = new_mapping_spec(
        kind="jobs_parquet",
        output_schema_version="oda.job.v0.2.0",
        fields={
            "job_id": {"source": "JobID"},
            "submit_time": {
                "source": "Sub",
                "transform": {"type": "timestamp", "format": "epoch_s"},
            },
            "start_time": {
                "source": "StartTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "end_time": {
                "source": "EndTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "runtime_seconds": {"derive": "end_time - start_time"},
        },
    )
    mp = tmp_path / "map.yml"
    write_mapping_spec(mp, mapping, validate=True)

    apply_mapping_spec(inp, mp, tmp_path / "out.parquet")
    table = pq.read_table(tmp_path / "out.parquet")
    assert pa.types.is_timestamp(table.schema.field("submit_time").type)
    out = table.to_pylist()
    assert out[0]["submit_time"] == datetime.fromtimestamp(epoch, tz=timezone.utc)
    assert out[0]["runtime_seconds"] == 300.0
