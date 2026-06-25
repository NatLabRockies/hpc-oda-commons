from __future__ import annotations

import os
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml
from jsonschema import Draft202012Validator

from hpc_oda_commons.benchmark import runner
from hpc_oda_commons.kernel.artifacts.mapping_spec import new_mapping_spec, write_mapping_spec
from hpc_oda_commons.kernel.schemas import load_schema
from hpc_oda_commons.qst import cli
from tests.conftest import find_first, load_json, run_cli, write_slurmctld_log

REQUIRED_RESULT_FILES = ("result.json", "metrics.json", "provenance.json")


def _assert_result_bundle_dir(bundle_dir: Path) -> None:
    assert bundle_dir.exists() and bundle_dir.is_dir(), f"Missing bundle dir: {bundle_dir}"
    for fname in REQUIRED_RESULT_FILES:
        fpath = bundle_dir / fname
        assert fpath.exists(), f"Missing required result bundle file: {fpath}"


def _find_result_bundle_dir(project_dir: Path) -> Path:
    """
    Finds a result bundle directory under project_dir/runs by locating result.json.
    Assumes CLI writes results under runs/.
    """
    runs_dir = project_dir / "runs"
    assert runs_dir.exists(), f"Expected runs/ directory at {runs_dir}"
    result_json = find_first(runs_dir, "result.json")
    return result_json.parent


def _validate_json_against_schema(payload: dict, schema: dict) -> None:
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
    if errors:
        lines = ["JSON Schema validation failed:"]
        for e in errors[:20]:
            loc = "$"
            for p in list(e.path):
                loc += f".{p}"
            lines.append(f"- {loc}: {e.message}")
        raise AssertionError("\n".join(lines))


@pytest.mark.integration
def test_dod_1_cli_help(tmp_project: Path) -> None:
    """
    DoD-1: hpc-oda --help exits 0.
    (pip install -e . is performed by the environment/CI before tests run.)
    """
    res = run_cli(["--help"], cwd=tmp_project, timeout_s=60)
    res.assert_ok()
    assert "Usage" in res.stdout or "Commands" in res.stdout or "--help" in res.stdout


@pytest.mark.integration
def test_dod_2_offline_run_baseline_produces_result_bundle(
    repo_root: Path, tmp_project: Path
) -> None:
    """
    DoD-2: hpc-oda init; hpc-oda run-baseline; verify a result bundle exists (offline).
    """
    run_cli(["init"], cwd=tmp_project).assert_ok()
    run_cli(
        ["run-baseline"], cwd=tmp_project, env={"HPC_ODA_OFFLINE": "1"}, timeout_s=180
    ).assert_ok()

    bundle_dir = _find_result_bundle_dir(tmp_project)
    _assert_result_bundle_dir(bundle_dir)

    schema = load_schema("oda.result.v0.1.0")
    result_payload = load_json(bundle_dir / "result.json")
    _validate_json_against_schema(result_payload, schema)


@pytest.mark.integration
def test_dod_3_ingest_slurmctld_creates_schema_valid_artifacts(
    repo_root: Path, tmp_project: Path
) -> None:
    """
    DoD-3: ingest fixture slurmctld log → schema-valid Parquet + manifest.
    """
    run_cli(["init"], cwd=tmp_project).assert_ok()

    fixture_log = repo_root / "tests/fixtures/slurmctld.log"
    if not fixture_log.exists():
        fixture_log = write_slurmctld_log(tmp_project / "slurmctld.log")

    run_cli(
        ["ingest", "slurmctld", "--path", str(fixture_log)], cwd=tmp_project, timeout_s=180
    ).assert_ok()

    ingested_root = tmp_project / "data" / "ingested"
    assert ingested_root.exists(), f"Expected ingest output under {ingested_root}"

    manifest_path = find_first(ingested_root, "manifest.json")
    parquet_path = find_first(ingested_root, "*.parquet")

    assert manifest_path.exists(), f"Missing manifest: {manifest_path}"
    assert parquet_path.exists(), f"Missing parquet: {parquet_path}"

    # Validate parquet and assert quality report exists.
    run_cli(["validate", str(parquet_path)], cwd=tmp_project, timeout_s=120).assert_ok()
    assert parquet_path.with_suffix(".parquet.quality.json").exists()

    table = pq.read_table(parquet_path)
    cols = set(table.column_names)

    required_cols = {"job_id", "start_time", "end_time", "runtime_seconds"}
    missing = required_cols - cols
    assert not missing, f"Missing required columns in {parquet_path}: {sorted(missing)}"

    job_schema = load_schema("oda.job.v0.1.0")
    first_row = table.slice(0, 1).to_pylist()[0]
    _validate_json_against_schema(first_row, job_schema)

    manifest = load_json(manifest_path)
    assert "schema_version" in manifest, "manifest.json must include schema_version"
    assert "provenance" in manifest or "inputs" in manifest, (
        "manifest.json should include provenance/inputs info"
    )


@pytest.mark.integration
def test_benchmark_xgboost_recipe_small_window(
    repo_root: Path,
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Integration coverage for alternate model benchmark path.
    Uses a small rolling window for CI speed and monkeypatches the model class to
    keep execution deterministic in restricted sandbox environments.
    """

    class _FakeXGBModel:
        seen_n_windows: int | None = None

        def __init__(self, config: object) -> None:
            _FakeXGBModel.seen_n_windows = int(config.n_windows)

        def evaluate(
            self,
            rows: list[dict[str, object]],
            *,
            verbose: bool = False,
            metric_defs: list[dict[str, object]] | None = None,
            capture_artifacts: bool = False,
        ) -> dict[str, object]:
            assert rows
            _ = verbose
            _ = metric_defs
            _ = capture_artifacts
            return {
                "mae": 10.0,
                "rmse": 12.0,
                "definitions": [
                    {"name": "mae", "target": "runtime_seconds"},
                    {"name": "rmse", "target": "runtime_seconds"},
                ],
                "windows": [
                    {
                        "split_time": "2026-01-01T00:00:00Z",
                        "status": "ok",
                        "preprocessing_refit": True,
                        "metrics": {"mae": 10.0, "rmse": 12.0},
                    }
                ],
                "summary": {
                    "windows_total": 24,
                    "windows_scored": 1,
                    "windows_skipped": 23,
                    "preprocessing_refits": 1,
                    "rows_scored": len(rows),
                    "days_with_cached_preprocessing": ["2026-01-01"],
                    "n_windows": 24,
                },
            }

    run_cli(["init"], cwd=tmp_project).assert_ok()

    recipe_src = repo_root / "src/hpc_oda_commons/recipes/job-runtime/xgb_hourly_recent.yml"
    recipe_payload = yaml.safe_load(recipe_src.read_text(encoding="utf-8"))
    assert isinstance(recipe_payload, dict)
    recipe_payload["split"] = {"method": "rolling", "n_windows": 24}

    recipe_path = tmp_project / "xgb_hourly_recent_small.yml"
    recipe_path.write_text(yaml.safe_dump(recipe_payload, sort_keys=False), encoding="utf-8")

    monkeypatch.chdir(tmp_project)
    monkeypatch.setattr(runner, "JobRuntimeXGBoostModel", _FakeXGBModel)

    cli.benchmark(recipe_path)

    bundle_dir = _find_result_bundle_dir(tmp_project)
    _assert_result_bundle_dir(bundle_dir)
    result_payload = load_json(bundle_dir / "result.json")
    metrics_payload = load_json(bundle_dir / "metrics.json")

    assert _FakeXGBModel.seen_n_windows == 24
    assert result_payload["model"]["id"] == "model.job_runtime_xgboost"
    assert result_payload["metrics"]["mae"] == 10.0
    assert result_payload["metrics"]["rmse"] == 12.0
    assert metrics_payload["summary"]["n_windows"] == 24
    assert metrics_payload["summary"]["windows_total"] == 24


@pytest.mark.integration
def test_benchmark_xgboost_recipe_small_window_native_cli(
    repo_root: Path,
    tmp_project: Path,
) -> None:
    """
    Optional native lane for real XGBoost execution.
    Enable with HPC_ODA_ENABLE_NATIVE_XGBOOST_IT=1 on environments that allow
    OpenMP shared-memory primitives (outside restricted sandboxes).
    """
    if os.environ.get("HPC_ODA_ENABLE_NATIVE_XGBOOST_IT") != "1":
        pytest.skip("Set HPC_ODA_ENABLE_NATIVE_XGBOOST_IT=1 to run native XGBoost integration.")

    run_cli(["init"], cwd=tmp_project).assert_ok()

    recipe_src = repo_root / "src/hpc_oda_commons/recipes/job-runtime/alt_model_example.yml"
    recipe_payload = yaml.safe_load(recipe_src.read_text(encoding="utf-8"))
    assert isinstance(recipe_payload, dict)
    recipe_payload["split"] = {"method": "rolling", "n_windows": 24}

    recipe_path = tmp_project / "xgb_hourly_recent_native.yml"
    recipe_path.write_text(yaml.safe_dump(recipe_payload, sort_keys=False), encoding="utf-8")

    run_cli(
        ["benchmark", str(recipe_path)],
        cwd=tmp_project,
        env={"HPC_ODA_OFFLINE": "1"},
        timeout_s=600,
    ).assert_ok()

    bundle_dir = _find_result_bundle_dir(tmp_project)
    _assert_result_bundle_dir(bundle_dir)
    result_payload = load_json(bundle_dir / "result.json")
    metrics_payload = load_json(bundle_dir / "metrics.json")

    assert result_payload["model"]["id"] == "model.job_runtime_xgboost"
    assert result_payload["metrics"]["mae"] >= 0.0
    assert result_payload["metrics"]["rmse"] >= 0.0
    assert isinstance(metrics_payload.get("windows"), list)
    assert metrics_payload.get("summary", {}).get("n_windows") == 24


@pytest.mark.integration
def test_dod_4_benchmark_recipe_produces_metrics_and_provenance(
    repo_root: Path, tmp_project: Path
) -> None:
    """
    DoD-4: run benchmark recipe for runtime prediction:
      hpc-oda benchmark recipes/job-runtime/baseline_tiny.yml
    """
    run_cli(["init"], cwd=tmp_project).assert_ok()

    recipe = repo_root / "src/hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml"
    assert recipe.exists(), f"Missing recipe: {recipe}"

    run_cli(
        ["benchmark", str(recipe)], cwd=tmp_project, env={"HPC_ODA_OFFLINE": "1"}, timeout_s=300
    ).assert_ok()

    bundle_dir = _find_result_bundle_dir(tmp_project)
    _assert_result_bundle_dir(bundle_dir)

    schema = load_schema("oda.result.v0.1.0")
    result_payload = load_json(bundle_dir / "result.json")
    _validate_json_against_schema(result_payload, schema)

    prov = result_payload["provenance"]
    assert prov["schema_versions"]["input"], "provenance.schema_versions.input is required"
    assert prov["schema_versions"]["result"], "provenance.schema_versions.result is required"

    dataset = result_payload.get("dataset", {})
    assert dataset.get("hash"), "dataset.hash must be populated for DoD-4"

    model = result_payload.get("model", {})
    assert model.get("id"), "model.id must be populated for DoD-4"
    assert model.get("version"), "model.version must be populated for DoD-4"


@pytest.mark.integration
def test_analyze_command_creates_report_bundle(repo_root: Path, tmp_project: Path) -> None:
    run_cli(["init"], cwd=tmp_project).assert_ok()

    fixture_log = repo_root / "tests/fixtures/slurmctld.log"
    if not fixture_log.exists():
        fixture_log = write_slurmctld_log(tmp_project / "slurmctld.log")

    run_cli(
        ["ingest", "slurmctld", "--path", str(fixture_log)], cwd=tmp_project, timeout_s=180
    ).assert_ok()

    ingested_root = tmp_project / "data" / "ingested"
    parquet_path = find_first(ingested_root, "*.parquet")

    run_cli(["analyze", "--data", str(parquet_path)], cwd=tmp_project, timeout_s=180).assert_ok()

    reports_dir = tmp_project / "reports"
    analysis_json = find_first(reports_dir, "analysis.json")
    analysis_html = analysis_json.parent / "index.html"

    assert analysis_json.exists()
    assert analysis_html.exists()


@pytest.mark.integration
def test_ingest_jobs_parquet_with_mapping(tmp_project: Path) -> None:
    run_cli(["init"], cwd=tmp_project).assert_ok()

    jobs_path = tmp_project / "jobs.parquet"
    table = pa.table(
        {
            "JobID": [1, 2],
            "StartTime": ["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"],
            "EndTime": ["2026-01-01T00:10:00Z", "2026-01-01T01:05:00Z"],
            "SubmitTime": ["2026-01-01T00:00:00Z", "2026-01-01T00:59:00Z"],
            "State": ["COMPLETED", "FAILED"],
            "User": ["alice", "bob"],
            "Elapsed": [600.0, 300.0],
        }
    )
    pq.write_table(table, jobs_path)

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
            "submit_time": {
                "source": "SubmitTime",
                "transform": {"type": "timestamp", "format": "iso8601"},
            },
            "state": {"source": "State"},
            "user": {"source": "User", "transform": {"type": "hash_identifier"}},
            "runtime_seconds": {
                "source": "Elapsed",
                "transform": {"type": "duration", "unit": "seconds"},
            },
        },
    )
    mapping_path = tmp_project / "mapping.yml"
    write_mapping_spec(mapping_path, mapping, validate=True)

    run_cli(
        ["ingest", "jobs-parquet", "--path", str(jobs_path), "--mapping", str(mapping_path)],
        cwd=tmp_project,
        timeout_s=180,
    ).assert_ok()

    ingested_root = tmp_project / "data" / "ingested" / "jobs_parquet"
    assert ingested_root.exists()

    manifest_path = find_first(ingested_root, "manifest.json")
    parquet_path = find_first(ingested_root, "*.parquet")
    assert manifest_path.exists()
    assert parquet_path.exists()

    run_cli(["validate", str(parquet_path)], cwd=tmp_project, timeout_s=120).assert_ok()
