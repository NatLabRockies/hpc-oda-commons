from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from hpc_oda_commons.datasets.synthetic import generate_tiny_embedded_runtime_dataset
from hpc_oda_commons.qst import cli
from tests.conftest import find_first, load_json, run_cli


def _find_result_bundle_dir(project_dir: Path) -> Path:
    runs_dir = project_dir / "runs"
    assert runs_dir.exists(), f"Expected runs/ directory at {runs_dir}"
    return find_first(runs_dir, "result.json").parent


@pytest.mark.integration
def test_benchmark_embedding_knn_end_to_end(
    repo_root: Path,
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full benchmark path for the embedding kNN model on a generated embedded dataset."""
    run_cli(["init"], cwd=tmp_project).assert_ok()

    ds_dir = tmp_project / "data" / "ingested" / "jobs_parquet" / "embedded_jobs"
    generate_tiny_embedded_runtime_dataset(ds_dir)

    recipe_src = repo_root / "src/hpc_oda_commons/recipes/job-runtime/embedding_knn_rolling.yml"
    recipe_payload = yaml.safe_load(recipe_src.read_text(encoding="utf-8"))
    recipe_payload["dataset"] = {
        "id": "embedded_jobs",
        "table_path": "data/ingested/jobs_parquet/embedded_jobs/data.parquet",
        "manifest_path": "data/ingested/jobs_parquet/embedded_jobs/manifest.json",
    }
    recipe_payload["split"] = {
        "method": "rolling",
        "n_windows": 12,
        "test_window_hours": 6,
        "training_lookback_days": 30,
    }
    recipe_path = tmp_project / "embedding_knn_small.yml"
    recipe_path.write_text(yaml.safe_dump(recipe_payload, sort_keys=False), encoding="utf-8")

    monkeypatch.chdir(tmp_project)
    cli.benchmark(recipe_path)

    bundle_dir = _find_result_bundle_dir(tmp_project)
    for fname in ("result.json", "metrics.json", "provenance.json"):
        assert (bundle_dir / fname).exists(), f"missing {fname}"

    result_payload = load_json(bundle_dir / "result.json")
    metrics_payload = load_json(bundle_dir / "metrics.json")
    assert result_payload["model"]["id"] == "model.job_runtime_embedding_knn"
    assert "mae" in result_payload["metrics"] and "rmse" in result_payload["metrics"]
    assert metrics_payload["summary"]["rows_scored"] > 0
    assert metrics_payload["summary"]["embedding_dim"] == 16
