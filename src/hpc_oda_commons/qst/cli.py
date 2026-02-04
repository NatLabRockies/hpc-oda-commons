from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console

from hpc_oda_commons.adapters.slurmctld.adapter import parse_slurmctld_log
from hpc_oda_commons.models.job_runtime_baseline.model import JobRuntimeBaselineModel

app = typer.Typer(add_completion=False, help="hpc-oda-commons Quickstart Toolkit (v0.1)")
ingest_app = typer.Typer(
    add_completion=False, help="Ingest operational data into canonical ODA artifacts."
)
app.add_typer(ingest_app, name="ingest")

console = Console()

SLURMCTLD_PATH_OPT = typer.Option(..., "--path", exists=True, readable=True)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_dirs(project_root: Path) -> None:
    (project_root / ".hpc_oda").mkdir(parents=True, exist_ok=True)
    (project_root / "data").mkdir(parents=True, exist_ok=True)
    (project_root / "runs").mkdir(parents=True, exist_ok=True)


def _default_config_text() -> str:
    # Keep minimal for v0.1; expand later.
    return """# hpc-oda-commons project config (v0.1)
# Vertical slice: SLURM job runtime prediction

[project]
name = "hpc-oda-project"
schema_job = "oda.job.v0.1.0"
schema_result = "oda.result.v0.1.0"

[paths]
data_dir = "data"
runs_dir = "runs"
state_dir = ".hpc_oda"
"""


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _result_bundle_dir(project_root: Path, run_id: str) -> Path:
    return project_root / "runs" / run_id


def _write_result_bundle(
    project_root: Path,
    run_id: str,
    recipe_id: str,
    metrics: dict[str, float],
    provenance: dict[str, Any],
    *,
    problem_domain: list[str] | None = None,
    model: dict[str, str] | None = None,
    dataset: dict[str, Any] | None = None,
    notes: str | None = None,
) -> Path:
    bundle_dir = _result_bundle_dir(project_root, run_id)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    result_payload: dict[str, Any] = {
        "schema_version": "oda.result.v0.1.0",
        "recipe_id": recipe_id,
        "problem_domain": problem_domain or ["job-runtime-prediction"],
        "created_at": _now_utc_iso(),
        "metrics": metrics,
        "provenance": provenance,
    }
    if model is not None:
        result_payload["model"] = model
    if dataset is not None:
        result_payload["dataset"] = dataset
    if notes:
        result_payload["notes"] = notes

    _write_json(bundle_dir / "result.json", result_payload)
    _write_json(bundle_dir / "metrics.json", metrics)
    _write_json(bundle_dir / "provenance.json", provenance)

    return bundle_dir


def _minimal_provenance(input_schema: str) -> dict[str, Any]:
    # Keep minimal but schema-valid; expand later.
    pyver = f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}"
    return {
        "schema_versions": {"input": input_schema, "result": "oda.result.v0.1.0"},
        "environment": {"python": pyver, "packages": []},
        "code": {"package_version": "0.1.0"},
    }


def _generate_tiny_runtime_dataset(out_dir: Path) -> tuple[Path, Path]:
    """
    Deterministically generate a tiny synthetic runtime dataset in Parquet + manifest.
    This avoids committing binary Parquet early while still enabling offline golden-path tests.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    out_dir.mkdir(parents=True, exist_ok=True)
    table_path = out_dir / "data.parquet"
    manifest_path = out_dir / "manifest.json"

    if table_path.exists() and manifest_path.exists():
        return table_path, manifest_path

    base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    rows: list[dict[str, Any]] = []
    for i in range(1, 31):
        start = base.replace(minute=(i % 60))
        runtime = float((i % 10 + 1) * 30)  # 30..330 seconds
        end = start.timestamp() + runtime
        end_dt = datetime.fromtimestamp(end, tz=timezone.utc)
        rows.append(
            {
                "job_id": 1000 + i,
                "start_time": start.isoformat().replace("+00:00", "Z"),
                "end_time": end_dt.isoformat().replace("+00:00", "Z"),
                "runtime_seconds": runtime,
                "allocated_cpus": int((i % 8) + 1),
                "partition": "debug" if i % 2 == 0 else "compute",
            }
        )

    table = pa.Table.from_pylist(rows)
    pq.write_table(table, table_path)

    manifest = {
        "schema_version": "oda.job.v0.1.0",
        "generated_at": _now_utc_iso(),
        "description": "Deterministic tiny synthetic dataset for v0.1 job runtime prediction.",
        "table_path": str(table_path),
    }
    _write_json(manifest_path, manifest)

    return table_path, manifest_path


def _load_recipe(recipe_path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(recipe_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise typer.BadParameter("Recipe YAML must be a mapping/object.")
    return payload


def _compute_regression_metrics(y_true: list[float], y_pred: list[float]) -> dict[str, float]:
    if len(y_true) != len(y_pred) or not y_true:
        raise ValueError("y_true and y_pred must be the same non-zero length")

    n = float(len(y_true))
    mae = sum(abs(a - b) for a, b in zip(y_true, y_pred)) / n
    rmse = (sum((a - b) ** 2 for a, b in zip(y_true, y_pred)) / n) ** 0.5
    return {"mae": float(mae), "rmse": float(rmse)}


@app.command()
def init() -> None:
    """
    Initialize a local hpc-oda-commons project in the current directory.
    """
    root = Path.cwd()
    _ensure_dirs(root)

    cfg = root / "hpc-oda.toml"
    if not cfg.exists():
        cfg.write_text(_default_config_text(), encoding="utf-8")

    console.print("[green]Initialized hpc-oda project[/green]")


@app.command("run-baseline")
def run_baseline() -> None:
    """
    Run an offline baseline demo using a deterministic tiny synthetic dataset.
    Writes a result bundle under ./runs/.
    """
    root = Path.cwd()
    _ensure_dirs(root)

    # Generate dataset in local project cache
    ds_dir = root / ".hpc_oda" / "cache" / "datasets" / "synthetic_job_runtime_tiny"
    table_path, _manifest_path = _generate_tiny_runtime_dataset(ds_dir)
    ds_hash = _sha256_file(table_path)

    # Load data
    import pyarrow.parquet as pq

    table = pq.read_table(table_path)
    rows = table.to_pylist()
    y_true = [float(r["runtime_seconds"]) for r in rows]

    # Fit/predict baseline
    model = JobRuntimeBaselineModel()
    model.fit(rows)
    y_pred = model.predict(rows)

    metrics = _compute_regression_metrics(y_true, y_pred)
    prov = _minimal_provenance("oda.job.v0.1.0")

    run_id = f"run-baseline-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    _write_result_bundle(
        root,
        run_id,
        recipe_id="run-baseline.offline_tiny",
        metrics=metrics,
        provenance=prov,
        model={"id": "model.job_runtime_baseline", "version": "0.1.0"},
        dataset={
            "id": "synthetic_job_runtime_tiny",
            "schema_version": "oda.job.v0.1.0",
            "hash": ds_hash,
        },
        notes="Offline baseline demo run (v0.1).",
    )

    console.print(f"[green]Baseline run complete[/green] → runs/{run_id}/")


@ingest_app.command("slurmctld")
def ingest_slurmctld(path: Path = SLURMCTLD_PATH_OPT) -> None:
    """
    Ingest slurmctld log into canonical oda.job.v0.1.0 Parquet + manifest.
    """
    root = Path.cwd()
    _ensure_dirs(root)

    rows = parse_slurmctld_log(path)

    # Write Parquet
    import pyarrow as pa
    import pyarrow.parquet as pq

    run_id = f"slurmctld-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    out_dir = root / "data" / "ingested" / "slurmctld" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    table = pa.Table.from_pylist(rows)
    parquet_path = out_dir / "data.parquet"
    pq.write_table(table, parquet_path)

    manifest = {
        "schema_version": "oda.job.v0.1.0",
        "created_at": _now_utc_iso(),
        "adapter": {"id": "adapter.slurmctld", "version": "0.1.0"},
        "inputs": {"slurmctld_log_path": str(path)},
        "provenance": {"note": "local-first ingest; no uploads"},
        "outputs": {"table_path": str(parquet_path)},
        "transformations": [],
    }
    _write_json(out_dir / "manifest.json", manifest)

    console.print(f"[green]Ingest complete[/green] → {out_dir}")


@app.command()
def benchmark(recipe: Path) -> None:
    """
    Run a benchmark recipe (v0.1 runtime prediction).
    Writes a result bundle under ./runs/.
    """
    root = Path.cwd()
    _ensure_dirs(root)

    recipe_payload = _load_recipe(recipe)
    recipe_id = str(recipe_payload.get("recipe_id", "recipe.unknown"))
    input_schema = str(recipe_payload.get("schema_version", "oda.job.v0.1.0"))

    # Dataset resolution:
    # For v0.1, if the dataset paths referenced in the recipe are missing, generate a tiny dataset locally.
    dataset = recipe_payload.get("dataset", {}) or {}
    table_path_str = dataset.get("table_path")
    manifest_path_str = dataset.get("manifest_path")

    # Prefer recipe-referenced paths if they exist; else generate.
    table_path = Path(table_path_str) if table_path_str else None
    manifest_path = Path(manifest_path_str) if manifest_path_str else None

    if table_path is None or not table_path.exists():
        ds_dir = root / ".hpc_oda" / "cache" / "datasets" / "synthetic_job_runtime_tiny"
        table_path, manifest_path = _generate_tiny_runtime_dataset(ds_dir)

    ds_hash = _sha256_file(table_path)

    import pyarrow.parquet as pq

    table = pq.read_table(table_path)
    rows = table.to_pylist()

    # Deterministic split (fixed fraction + seed) to match recipe contract.
    split = recipe_payload.get("split", {}) or {}
    train_fraction = float(split.get("train_fraction", 0.8))
    n_train = max(1, int(len(rows) * train_fraction))
    train_rows = rows[:n_train]
    test_rows = rows[n_train:] if n_train < len(rows) else rows[:]

    y_true = [float(r["runtime_seconds"]) for r in test_rows]

    model_ref = recipe_payload.get("model", {}) or {}
    model_id = str(model_ref.get("id", "model.job_runtime_baseline"))
    model_version = str(model_ref.get("version", "0.1.0"))

    model = JobRuntimeBaselineModel()
    model.fit(train_rows)
    y_pred = model.predict(test_rows)

    metrics = _compute_regression_metrics(y_true, y_pred)

    prov = _minimal_provenance(input_schema)
    # Populate required DoD-4 provenance fields (dataset hash + model id/version)
    run_id = f"benchmark-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    _write_result_bundle(
        root,
        run_id,
        recipe_id=recipe_id,
        metrics=metrics,
        provenance=prov,
        model={"id": model_id, "version": model_version},
        dataset={
            "id": str(dataset.get("id", "synthetic_job_runtime_tiny")),
            "schema_version": input_schema,
            "hash": ds_hash,
        },
        notes=f"Benchmark run for {recipe_id}.",
    )

    console.print(f"[green]Benchmark complete[/green] → runs/{run_id}/")


@app.command()
def validate(path: Path) -> None:
    """
    v0.1 placeholder: validate artifacts (schema + simple logical checks).
    Not required by golden-path tests yet.
    """
    if not path.exists():
        raise typer.BadParameter(f"Path not found: {path}")
    console.print(f"[yellow]validate[/yellow] not yet implemented for: {path}")
