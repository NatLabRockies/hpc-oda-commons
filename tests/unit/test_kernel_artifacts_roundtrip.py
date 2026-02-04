from __future__ import annotations

from pathlib import Path

from hpc_oda_commons.kernel.artifacts.manifest import new_manifest, read_manifest, write_manifest
from hpc_oda_commons.kernel.artifacts.oda_table import (
    peek_columns,
    read_table_parquet,
    write_table_parquet,
)
from hpc_oda_commons.kernel.artifacts.result_bundle import (
    write_result_bundle,
)
from hpc_oda_commons.kernel.provenance import build_provenance


def test_oda_table_roundtrip(tmp_path: Path) -> None:
    rows = [
        {
            "job_id": 1,
            "start_time": "2026-01-01T00:00:00Z",
            "end_time": "2026-01-01T00:01:00Z",
            "runtime_seconds": 60.0,
        }
    ]
    p = tmp_path / "t.parquet"
    write_table_parquet(rows, p)
    got = read_table_parquet(p)
    assert got[0]["job_id"] == 1
    assert set(peek_columns(p)) >= {"job_id", "runtime_seconds"}


def test_manifest_roundtrip(tmp_path: Path) -> None:
    in_file = tmp_path / "input.log"
    in_file.write_text("x", encoding="utf-8")

    prov = build_provenance(
        input_schema="oda.job.v0.1.0",
        result_schema="oda.result.v0.1.0",
        inputs=[in_file],
        capture_packages=False,
    )

    manifest = new_manifest(
        input_schema_version="oda.job.v0.1.0",
        adapter={"id": "adapter.slurmctld", "version": "0.1.0"},
        inputs=[{"path": str(in_file)}],
        artifact={
            "type": "ingest",
            "paths": {"table": "data.parquet", "manifest": "manifest.json"},
        },
        provenance=prov,
        transformations=[],
    )
    mp = tmp_path / "manifest.json"
    write_manifest(mp, manifest, validate=True)
    got = read_manifest(mp, validate=True)
    assert got["schema_version"] == "oda.manifest.v0.1.0"


def test_result_bundle_roundtrip(tmp_path: Path) -> None:
    bundle = tmp_path / "runs" / "r1"

    # Minimal-but-valid provenance according to v0.1 schema
    in_file = tmp_path / "input.txt"
    in_file.write_text("x", encoding="utf-8")

    prov = build_provenance(
        input_schema="oda.job.v0.1.0",
        result_schema="oda.result.v0.1.0",
        inputs=[in_file],
        capture_packages=False,
    )

    metrics = {"mae": 1.0, "rmse": 2.0}

    # Use realistic identifiers and a SHA-256-shaped hash
    result = {
        "schema_version": "oda.result.v0.1.0",
        "recipe_id": "recipe.test_runtime_roundtrip",
        "problem_domain": ["job-runtime-prediction"],
        "created_at": "2026-01-01T00:00:00Z",
        "metrics": metrics,
        "provenance": prov,
        "model": {"id": "model.job_runtime_baseline", "version": "0.1.0"},
        "dataset": {
            "id": "synthetic",
            "schema_version": "oda.job.v0.1.0",
            "hash": "a" * 64,  # looks like sha256
        },
    }

    write_result_bundle(bundle, result=result, metrics=metrics, provenance=prov, validate=True)
