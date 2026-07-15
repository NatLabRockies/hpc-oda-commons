from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq
import pytest
import yaml

from hpc_oda_commons.datasets.synthetic import generate_tiny_runtime_dataset
from hpc_oda_commons.qst import cli
from tests.conftest import find_first, load_json, run_cli


@pytest.mark.integration
def test_embed_then_benchmark_end_to_end(
    repo_root: Path,
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ingest table -> `hpc-oda embed` (stub, offline) -> benchmark embedding kNN."""
    run_cli(["init"], cwd=tmp_project).assert_ok()
    monkeypatch.chdir(tmp_project)

    # a plain ingested table (no embedding column)
    src, _ = generate_tiny_runtime_dataset(tmp_project / "ds")

    # embed it with the deterministic stub encoder (no model download)
    ds_dir = tmp_project / "data" / "ingested" / "jobs_parquet" / "embedded_jobs"
    out = ds_dir / "data.parquet"
    cli.embed(
        input_path=src,
        out=out,
        model="stub",
        text_format="prose",
        config_path=None,
        device="cpu",
        dtype="fp32",
        batch_size=32,
        chunk_size=8,
        cache_dir=tmp_project / "cache",
        instruction="",
        trust_remote_code=False,
    )
    embedded = pq.read_table(out)
    assert "embedding" in embedded.column_names
    assert embedded.schema.field("embedding").type.list_size == 256
    assert Path(str(out) + ".manifest.json").exists()

    # benchmark the embedding kNN model on the embedded table
    recipe = {
        "recipe_id": "recipe.job_runtime.embed_it",
        "problem_domain": ["job-runtime-prediction"],
        "schema_version": "oda.job.v0.2.0",
        "dataset": {
            "id": "embedded_jobs",
            "table_path": "data/ingested/jobs_parquet/embedded_jobs/data.parquet",
            "manifest_path": "data/ingested/jobs_parquet/embedded_jobs/data.parquet.manifest.json",
        },
        "model": {"id": "model.job_runtime_embedding_knn", "version": "0.1.0"},
        "metrics": [
            {"name": "mae", "target": "runtime_seconds"},
            {"name": "rmse", "target": "runtime_seconds"},
        ],
        "split": {
            "method": "rolling",
            "n_windows": 8,
            "test_window_hours": 6,
            "training_lookback_days": 30,
        },
        "run": {"output_dir": "runs", "overwrite": False},
    }
    recipe_path = tmp_project / "embed_it.yml"
    recipe_path.write_text(yaml.safe_dump(recipe, sort_keys=False), encoding="utf-8")

    cli.benchmark(recipe_path)

    runs_dir = tmp_project / "runs"
    bundle_dir = find_first(runs_dir, "result.json").parent
    for fname in ("result.json", "metrics.json", "provenance.json"):
        assert (bundle_dir / fname).exists(), f"missing {fname}"
    result = load_json(bundle_dir / "result.json")
    assert result["model"]["id"] == "model.job_runtime_embedding_knn"
    assert "mae" in result["metrics"]
