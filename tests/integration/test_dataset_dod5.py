from __future__ import annotations

import hashlib
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml

from tests.conftest import find_first, load_json, run_cli

REQUIRED_RESULT_FILES = ("result.json", "metrics.json", "provenance.json")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.integration
def test_dod_5_dataset_prepare_then_benchmark(tmp_project: Path) -> None:
    """DoD-5: descriptor -> `datasets prepare` -> schema-valid table -> `benchmark` -> bundle.

    Uses a local ``file://`` dataset, so it needs no network (and no offline flag for the
    prepare step, since file:// is local I/O)."""
    run_cli(["init"], cwd=tmp_project).assert_ok()

    # A tiny "remote" job table with source-named columns, served via file://.
    n = 60
    base = 1_600_000_000
    remote = tmp_project / "remote" / "jobs.parquet"
    remote.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.table(
            {
                "jobid": list(range(1, n + 1)),
                "sdt": [base + i * 120 for i in range(n)],
                "edt": [base + i * 120 + (30 + (i % 7) * 15) for i in range(n)],
                "dur": [30 + (i % 7) * 15 for i in range(n)],
                "part": ["short" if i % 2 else "standard" for i in range(n)],
                "usr": [f"user{i % 5}" for i in range(n)],
            }
        ),
        remote,
    )

    descriptor = {
        "dataset_id": "dataset.test.dod5",
        "schema_version": "oda.dataset.v0.1.0",
        "name": "DoD5 Fixture Dataset",
        "version": "1.0.0",
        "description": "Tiny fixture proving datasets prepare -> benchmark end to end.",
        "problem_domains": ["job-runtime-prediction"],
        "source": {
            "kind": "http",
            "resources": [
                {
                    "filename": "jobs.parquet",
                    "url": remote.as_uri(),
                    "sha256": _sha(remote),
                    "bytes": remote.stat().st_size,
                }
            ],
        },
        "decode": {"format": "parquet"},
        "targets": [
            {
                "schema": "oda.job.v0.2.0",
                "capabilities": [
                    {"problem_domain": "job-runtime-prediction", "target_column": "runtime_seconds"}
                ],
                "mapping": {
                    "job_id": {"from": "jobid"},
                    "start_time": {"from": "sdt", "type": "timestamp", "format": "epoch_s"},
                    "end_time": {"from": "edt", "type": "timestamp", "format": "epoch_s"},
                    "runtime_seconds": {"from": "dur", "type": "duration", "unit": "seconds"},
                    "partition": {"from": "part"},
                    "user": {"from": "usr", "type": "hash_identifier"},
                },
                "output": {"id": "dod5", "path": "data/datasets/dod5/data.parquet"},
            }
        ],
    }
    desc_path = tmp_project / "dod5.yml"
    desc_path.write_text(yaml.safe_dump(descriptor), encoding="utf-8")

    run_cli(
        [
            "datasets",
            "prepare",
            str(desc_path),
            "--out",
            str(tmp_project),
            "--cache",
            str(tmp_project / ".cache"),
        ],
        cwd=tmp_project,
        env={"HPC_ODA_OFFLINE": "0"},
        timeout_s=180,
    ).assert_ok()

    table_path = tmp_project / "data" / "datasets" / "dod5" / "data.parquet"
    assert table_path.exists(), f"prepare did not produce {table_path}"
    prepared = pq.read_table(table_path)
    assert {"job_id", "start_time", "end_time", "runtime_seconds"}.issubset(prepared.column_names)
    assert prepared.schema.field("start_time").type == pa.timestamp("us", tz="UTC")

    recipe = {
        "recipe_id": "recipe.job_runtime.dod5",
        "problem_domain": ["job-runtime-prediction"],
        "schema_version": "oda.job.v0.2.0",
        "dataset": {"id": "dod5", "table_path": "data/datasets/dod5/data.parquet"},
        "model": {"id": "model.job_runtime_baseline", "version": "0.1.0"},
        "metrics": [
            {"name": "mae", "target": "runtime_seconds"},
            {"name": "rmse", "target": "runtime_seconds"},
        ],
        "split": {"method": "fixed", "train_fraction": 0.8, "seed": 42},
    }
    recipe_path = tmp_project / "dod5_recipe.yml"
    recipe_path.write_text(yaml.safe_dump(recipe), encoding="utf-8")

    run_cli(
        ["benchmark", str(recipe_path)],
        cwd=tmp_project,
        env={"HPC_ODA_OFFLINE": "1"},
        timeout_s=300,
    ).assert_ok()

    bundle = find_first(tmp_project / "runs", "result.json").parent
    for fname in REQUIRED_RESULT_FILES:
        assert (bundle / fname).exists(), f"missing {fname}"
    result = load_json(bundle / "result.json")
    assert result["model"]["id"] == "model.job_runtime_baseline"
    assert result.get("dataset", {}).get("hash")
