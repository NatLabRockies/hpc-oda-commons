from __future__ import annotations

import json
from pathlib import Path

import pytest
import pyarrow.parquet as pq
from jsonschema import Draft202012Validator

from tests.conftest import find_first, load_json, load_schema, run_cli


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
    # Lightweight sanity check that help looks like a CLI help screen.
    assert "Usage" in res.stdout or "Commands" in res.stdout or "--help" in res.stdout


@pytest.mark.integration
def test_dod_2_offline_run_baseline_produces_result_bundle(repo_root: Path, tmp_project: Path) -> None:
    """
    DoD-2: hpc-oda init; hpc-oda run-baseline; verify a result bundle exists (offline).
    """
    # Initialize project in isolated directory
    run_cli(["init"], cwd=tmp_project).assert_ok()

    # Run baseline offline. We set HPC_ODA_OFFLINE=1 as a contract expectation;
    # implementation should not require network for this path.
    run_cli(["run-baseline"], cwd=tmp_project, env={"HPC_ODA_OFFLINE": "1"}, timeout_s=180).assert_ok()

    bundle_dir = _find_result_bundle_dir(tmp_project)
    _assert_result_bundle_dir(bundle_dir)

    # Validate result.json against the canonical result schema
    schema = load_schema(repo_root, "schemas/oda/result/v0.1.0.json")
    result_payload = load_json(bundle_dir / "result.json")
    _validate_json_against_schema(result_payload, schema)


@pytest.mark.integration
def test_dod_3_ingest_slurmctld_creates_schema_valid_artifacts(repo_root: Path, tmp_project: Path) -> None:
    """
    DoD-3: ingest fixture slurmctld log → schema-valid Parquet + manifest.
    Validates:
      - output artifacts exist
      - required columns exist in Parquet
      - first row validates against oda.job.v0.1.0 JSON Schema
    """
    run_cli(["init"], cwd=tmp_project).assert_ok()

    fixture_log = repo_root / "tests/fixtures/slurmctld.log"
    assert fixture_log.exists(), f"Missing fixture: {fixture_log}"

    run_cli(["ingest", "slurmctld", "--path", str(fixture_log)], cwd=tmp_project, timeout_s=180).assert_ok()

    ingested_root = tmp_project / "data" / "ingested"
    assert ingested_root.exists(), f"Expected ingest output under {ingested_root}"

    # Find artifacts (first match)
    manifest_path = find_first(ingested_root, "manifest.json")
    parquet_path = find_first(ingested_root, "*.parquet")

    assert manifest_path.exists(), f"Missing manifest: {manifest_path}"
    assert parquet_path.exists(), f"Missing parquet: {parquet_path}"

    # Parquet required columns for runtime prediction v0.1
    table = pq.read_table(parquet_path)
    cols = set(table.column_names)

    required_cols = {"job_id", "start_time", "end_time", "runtime_seconds"}
    missing = required_cols - cols
    assert not missing, f"Missing required columns in {parquet_path}: {sorted(missing)}"

    # Validate first row against oda.job schema
    job_schema = load_schema(repo_root, "schemas/oda/job/v0.1.0.json")

    # Convert first row to a python dict for JSON Schema validation.
    first = table.slice(0, 1).to_pylist()[0]
    _validate_json_against_schema(first, job_schema)

    # Minimal manifest sanity (until a dedicated manifest schema is added)
    manifest = load_json(manifest_path)
    assert "schema_version" in manifest, "manifest.json must include schema_version"
    assert "provenance" in manifest or "inputs" in manifest, "manifest.json should include provenance/inputs info"


@pytest.mark.integration
def test_dod_4_benchmark_recipe_produces_metrics_and_provenance(repo_root: Path, tmp_project: Path) -> None:
    """
    DoD-4: run benchmark recipe for runtime prediction:
      hpc-oda benchmark recipes/job-runtime/baseline_tiny.yml
    Validate:
      - result bundle exists
      - result.json validates against oda.result.v0.1.0
      - provenance includes schema version + dataset hash + model identifier
    """
    run_cli(["init"], cwd=tmp_project).assert_ok()

    recipe = repo_root / "recipes/job-runtime/baseline_tiny.yml"
    assert recipe.exists(), f"Missing recipe: {recipe}"

    run_cli(["benchmark", str(recipe)], cwd=tmp_project, env={"HPC_ODA_OFFLINE": "1"}, timeout_s=300).assert_ok()

    bundle_dir = _find_result_bundle_dir(tmp_project)
    _assert_result_bundle_dir(bundle_dir)

    schema = load_schema(repo_root, "schemas/oda/result/v0.1.0.json")
    result_payload = load_json(bundle_dir / "result.json")
    _validate_json_against_schema(result_payload, schema)

    # Provenance assertions required by DoD-4
    prov = result_payload["provenance"]
    assert prov["schema_versions"]["input"], "provenance.schema_versions.input is required"
    assert prov["schema_versions"]["result"], "provenance.schema_versions.result is required"

    # Dataset hash is required by DoD-4 (even though schema marks it optional).
    dataset = result_payload.get("dataset", {})
    assert dataset.get("hash"), "dataset.hash must be populated for DoD-4"

    model = result_payload.get("model", {})
    assert model.get("id"), "model.id must be populated for DoD-4"
    assert model.get("version"), "model.version must be populated for DoD-4"
