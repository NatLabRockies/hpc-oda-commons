from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

from hpc_oda_commons.adapters.slurmctld.adapter import SlurmctldAdapter
from hpc_oda_commons.benchmark.recipes import load_recipe
from hpc_oda_commons.benchmark.results import build_leaderboard, write_leaderboard
from hpc_oda_commons.ingest.jobs_parquet.apply import apply_mapping_spec
from hpc_oda_commons.ingest.jobs_parquet.profile import profile_parquet
from hpc_oda_commons.ingest.jobs_parquet.suggest import suggest_mapping
from hpc_oda_commons.ingest.jobs_parquet.wizard import build_mapping_spec_interactive
from hpc_oda_commons.kernel.artifacts.manifest import new_manifest, write_manifest
from hpc_oda_commons.kernel.artifacts.mapping_spec import (
    read_mapping_spec,
    write_mapping_spec,
)
from hpc_oda_commons.kernel.artifacts.oda_table import table_hash, write_table_parquet
from hpc_oda_commons.kernel.artifacts.result_bundle import write_result_bundle
from hpc_oda_commons.kernel.provenance import build_provenance
from hpc_oda_commons.kernel.validate import validate_json
from hpc_oda_commons.models.job_runtime_baseline.model import JobRuntimeBaselineModel
from hpc_oda_commons.models.job_runtime_xgboost.model import (
    JobRuntimeXGBoostConfig,
    JobRuntimeXGBoostModel,
)
from hpc_oda_commons.qst.commands.browse import browse
from hpc_oda_commons.qst.commands.info import info
from hpc_oda_commons.qst.ingest_suggestions import build_ingest_suggestions
from hpc_oda_commons.schema.validator import validate_parquet_with_quality
from hpc_oda_commons.tools.report import render_analysis_html, render_leaderboard_html

app = typer.Typer(add_completion=False, help="hpc-oda-commons Quickstart Toolkit (v0.1)")
ingest_app = typer.Typer(
    add_completion=False, help="Ingest operational data into canonical ODA artifacts."
)
app.add_typer(ingest_app, name="ingest")
app.command()(browse)
app.command()(info)

console = Console()

SLURMCTLD_PATH_OPT = typer.Option(..., "--path", exists=True, readable=True)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ensure_dirs(project_root: Path) -> None:
    (project_root / ".hpc_oda").mkdir(parents=True, exist_ok=True)
    (project_root / "data").mkdir(parents=True, exist_ok=True)
    (project_root / "runs").mkdir(parents=True, exist_ok=True)


def _default_config_text() -> str:
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


def _result_bundle_dir(project_root: Path, run_id: str) -> Path:
    return project_root / "runs" / run_id


def _compute_regression_metrics(y_true: list[float], y_pred: list[float]) -> dict[str, float]:
    if len(y_true) != len(y_pred) or not y_true:
        raise ValueError("y_true and y_pred must be the same non-zero length")

    n = float(len(y_true))
    mae = sum(abs(a - b) for a, b in zip(y_true, y_pred)) / n
    rmse = (sum((a - b) ** 2 for a, b in zip(y_true, y_pred)) / n) ** 0.5
    return {"mae": float(mae), "rmse": float(rmse)}


def _compute_regression_metrics_from_defs(
    y_true: list[float], y_pred: list[float], metric_defs: list[dict[str, Any]]
) -> dict[str, float]:
    base = _compute_regression_metrics(y_true, y_pred)
    requested = {str(m.get("name", "")) for m in metric_defs}
    metrics: dict[str, float] = {k: v for k, v in base.items() if k in requested}

    if "mape" in requested:
        denom = [abs(v) for v in y_true if v != 0]
        if not denom:
            raise ValueError("MAPE is undefined when all targets are zero.")
        mape = sum(abs(a - b) / abs(a) for a, b in zip(y_true, y_pred) if a != 0) / len(denom)
        metrics["mape"] = float(mape)

    if "r2" in requested:
        mean = sum(y_true) / float(len(y_true))
        ss_tot = sum((v - mean) ** 2 for v in y_true)
        ss_res = sum((a - b) ** 2 for a, b in zip(y_true, y_pred))
        metrics["r2"] = float(1.0 - ss_res / ss_tot) if ss_tot != 0 else 0.0

    return metrics


def _tiny_dataset_is_rolling_compatible(table_path: Path) -> bool:
    try:
        import pyarrow.parquet as pq
    except Exception:
        return False

    try:
        table = pq.read_table(table_path)
    except Exception:
        return False

    if "submit_time" not in table.column_names:
        return False

    submit_values = table.column("submit_time").to_pylist()
    hour_bins: set[str] = set()
    for value in submit_values:
        if value in (None, ""):
            continue
        text = str(value)
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        hour_bins.add(
            dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0).isoformat()
        )

    return len(hour_bins) >= 3


def _generate_tiny_runtime_dataset(out_dir: Path) -> tuple[Path, Path]:
    """
    Deterministically generate a tiny synthetic dataset in Parquet + minimal manifest-like JSON.
    v0.1: keep generation local-first; no network access required.
    """
    import json

    out_dir.mkdir(parents=True, exist_ok=True)
    table_path = out_dir / "data.parquet"
    meta_path = out_dir / "manifest.json"

    if (
        table_path.exists()
        and meta_path.exists()
        and _tiny_dataset_is_rolling_compatible(table_path)
    ):
        return table_path, meta_path

    base_submit = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    rows: list[dict[str, Any]] = []
    for i in range(30):
        submit = base_submit + timedelta(hours=i, minutes=2)
        start = submit + timedelta(minutes=3)
        runtime = float(600 + (i % 10) * 120)  # 600..1680 seconds
        end = start + timedelta(seconds=runtime)
        rows.append(
            {
                "job_id": 1001 + i,
                "submit_time": submit.isoformat().replace("+00:00", "Z"),
                "start_time": start.isoformat().replace("+00:00", "Z"),
                "end_time": end.isoformat().replace("+00:00", "Z"),
                "runtime_seconds": runtime,
                "allocated_cpus": int((i % 8) + 1),
                "partition": "debug" if i % 2 == 0 else "compute",
            }
        )

    write_table_parquet(rows, table_path)
    meta = {
        "schema_version": "oda.job.v0.1.0",
        "generated_at": _now_utc_iso(),
        "description": (
            "Deterministic tiny synthetic dataset for v0.1 job runtime prediction "
            "with submit_time for rolling-hour compatibility."
        ),
        "table_path": str(table_path),
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return table_path, meta_path


def _load_recipe(recipe_path: Path) -> dict[str, Any]:
    try:
        return load_recipe(recipe_path, validate=True)
    except Exception as exc:
        raise typer.BadParameter(str(exc)) from exc


def _normalize_split(recipe_payload: dict[str, Any]) -> dict[str, Any]:
    split = recipe_payload.get("split", {}) or {}
    if not isinstance(split, dict):
        raise typer.BadParameter("recipe.split must be an object")
    method = str(split.get("method", "fixed"))
    if method not in {"fixed", "rolling_hourly"}:
        raise typer.BadParameter(f"Unsupported split method: {method}")
    split["method"] = method
    return split


def _run_fixed_baseline_benchmark(
    rows: list[dict[str, Any]],
    *,
    split: dict[str, Any],
    metric_defs: list[dict[str, Any]],
) -> tuple[dict[str, float], dict[str, Any]]:
    train_fraction = float(split.get("train_fraction", 0.8))
    n_train = max(1, int(len(rows) * train_fraction))
    train_rows = rows[:n_train]
    test_rows = rows[n_train:] if n_train < len(rows) else rows[:]
    y_true = [float(r["runtime_seconds"]) for r in test_rows]

    model = JobRuntimeBaselineModel()
    model.fit(train_rows)
    y_pred = model.predict(test_rows)

    metrics = _compute_regression_metrics_from_defs(y_true, y_pred, metric_defs)
    metrics_payload: dict[str, Any] = {**metrics, "definitions": metric_defs}
    return metrics, metrics_payload


def _run_rolling_hourly_xgboost_benchmark(
    rows: list[dict[str, Any]],
    *,
    split: dict[str, Any],
    metric_defs: list[dict[str, Any]],
) -> tuple[dict[str, float], dict[str, Any]]:
    requested = {str(m.get("name", "")) for m in metric_defs}
    unsupported = sorted(requested - {"mae", "rmse"})
    if unsupported:
        raise typer.BadParameter(
            "rolling_hourly benchmark currently supports only mae/rmse metrics; "
            f"unsupported: {', '.join(unsupported)}"
        )

    n_recent_hours = int(split.get("n_recent_hours", 1000))
    model = JobRuntimeXGBoostModel(config=JobRuntimeXGBoostConfig(n_recent_hours=n_recent_hours))
    eval_payload = model.evaluate_hourly(rows)

    metrics = {
        "mae": float(eval_payload["mae"]),
        "rmse": float(eval_payload["rmse"]),
    }
    metrics_payload: dict[str, Any] = {**eval_payload, "definitions": metric_defs}
    return metrics, metrics_payload


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

    ds_dir = root / ".hpc_oda" / "cache" / "datasets" / "synthetic_job_runtime_tiny"
    table_path, _meta_path = _generate_tiny_runtime_dataset(ds_dir)
    ds_hash = table_hash(table_path)

    import pyarrow.parquet as pq

    table = pq.read_table(table_path)
    rows = table.to_pylist()
    y_true = [float(r["runtime_seconds"]) for r in rows]

    model = JobRuntimeBaselineModel()
    model.fit(rows)
    y_pred = model.predict(rows)

    metric_defs = [
        {"name": "mae", "target": "runtime_seconds"},
        {"name": "rmse", "target": "runtime_seconds"},
    ]
    metrics = _compute_regression_metrics_from_defs(y_true, y_pred, metric_defs)
    metrics_payload: dict[str, Any] = {**metrics, "definitions": metric_defs}

    prov = build_provenance(
        input_schema="oda.job.v0.1.0",
        result_schema="oda.result.v0.1.0",
        inputs=[table_path],
        project_root=root,
        capture_packages=False,
    )

    run_id = f"run-baseline-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    bundle_dir = _result_bundle_dir(root, run_id)

    result_payload: dict[str, Any] = {
        "schema_version": "oda.result.v0.1.0",
        "recipe_id": "run-baseline.offline_tiny",
        "problem_domain": ["job-runtime-prediction"],
        "created_at": _now_utc_iso(),
        "metrics": metrics,
        "provenance": prov,
        "model": {"id": "model.job_runtime_baseline", "version": "0.1.0"},
        "dataset": {
            "id": "synthetic_job_runtime_tiny",
            "schema_version": "oda.job.v0.1.0",
            "hash": ds_hash,
        },
        "notes": "Offline baseline demo run (v0.1).",
    }

    validate_json(result_payload, "oda.result.v0.1.0")
    write_result_bundle(
        bundle_dir, result=result_payload, metrics=metrics_payload, provenance=prov, validate=True
    )

    console.print(f"[green]Baseline run complete[/green] → runs/{run_id}/")


@ingest_app.command("slurmctld")
def ingest_slurmctld(path: Path = SLURMCTLD_PATH_OPT) -> None:
    """
    Ingest slurmctld log into canonical oda.job.v0.1.0 Parquet + manifest.
    """
    root = Path.cwd()
    _ensure_dirs(root)

    adapter = SlurmctldAdapter()
    rows = adapter.parse(path)

    run_id = f"slurmctld-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    out_dir = root / "data" / "ingested" / "slurmctld" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    parquet_path = out_dir / "data.parquet"
    write_table_parquet(rows, parquet_path)

    # Validate some rows against the job schema (human-friendly errors on failure)
    validate_parquet_with_quality(parquet_path, schema_id="oda.job.v0.1.0", sample=10)

    prov = build_provenance(
        input_schema="oda.job.v0.1.0",
        result_schema="oda.result.v0.1.0",
        inputs=[path, parquet_path],
        project_root=root,
        capture_packages=False,
    )

    manifest = new_manifest(
        input_schema_version="oda.job.v0.1.0",
        adapter={"id": adapter.metadata.id, "version": adapter.metadata.version},
        inputs=[{"path": str(path)}],
        artifact={
            "type": "ingest",
            "paths": {"table": str(parquet_path), "manifest": str(out_dir / "manifest.json")},
        },
        provenance=prov,
        transformations=[],
    )
    write_manifest(out_dir / "manifest.json", manifest, validate=True)

    suggestions = build_ingest_suggestions(path)
    for suggestion in suggestions:
        level = suggestion.get("level", "info")
        msg = suggestion.get("message", "")
        if level == "error":
            console.print(f"[red]Ingest check[/red]: {msg}")
        elif level == "warning":
            console.print(f"[yellow]Ingest check[/yellow]: {msg}")
        else:
            console.print(f"[blue]Ingest check[/blue]: {msg}")

    console.print(f"[green]Ingest complete[/green] → {out_dir}")


@ingest_app.command("jobs-parquet")
def ingest_jobs_parquet(
    path: Annotated[Path, typer.Option(..., "--path", exists=True, readable=True)],
    mapping: Annotated[Path | None, typer.Option("--mapping")] = None,
    sample_rows: Annotated[int, typer.Option("--sample-rows")] = 200,
    batch_size: Annotated[int, typer.Option("--batch-size")] = 50_000,
    non_interactive: Annotated[bool, typer.Option("--non-interactive")] = False,
    hash_identifiers: Annotated[
        bool, typer.Option("--hash-identifiers/--no-hash-identifiers")
    ] = True,
) -> None:
    """
    Ingest a jobs Parquet export into canonical oda.job.v0.1.0 artifacts.
    """
    root = Path.cwd()
    _ensure_dirs(root)

    run_id = f"jobs-parquet-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    out_dir = root / "data" / "ingested" / "jobs_parquet" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    if mapping is None:
        if non_interactive:
            raise typer.BadParameter("Non-interactive mode requires --mapping.")
        profiles = profile_parquet(path, sample_rows=sample_rows)
        suggestions = suggest_mapping(profiles)
        mapping_payload = build_mapping_spec_interactive(
            profiles,
            suggestions,
            input_path=path,
            default_hash_identifiers=hash_identifiers,
        )
        mapping = out_dir / "mapping.yml"
        write_mapping_spec(mapping, mapping_payload, validate=True)
    else:
        read_mapping_spec(mapping, validate=True)

    parquet_path = out_dir / "data.parquet"
    summary = apply_mapping_spec(
        path,
        mapping,
        parquet_path,
        batch_size=batch_size,
        skip_incomplete=True,
    )

    validate_parquet_with_quality(parquet_path, schema_id="oda.job.v0.1.0", sample=10)

    prov = build_provenance(
        input_schema="oda.job.v0.1.0",
        result_schema="oda.result.v0.1.0",
        inputs=[path, parquet_path, mapping],
        project_root=root,
        capture_packages=False,
    )

    manifest = new_manifest(
        input_schema_version="oda.job.v0.1.0",
        adapter={"id": "adapter.jobs_parquet", "version": "0.1.0"},
        inputs=[{"path": str(path)}],
        artifact={
            "type": "ingest",
            "paths": {"table": str(parquet_path), "manifest": str(out_dir / "manifest.json")},
        },
        provenance=prov,
        transformations=[
            {
                "kind": "mapping_spec",
                "path": str(mapping),
                "summary": summary,
            }
        ],
    )
    write_manifest(out_dir / "manifest.json", manifest, validate=True)

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

    dataset = recipe_payload.get("dataset", {}) or {}
    table_path_str = dataset.get("table_path")
    table_path = Path(table_path_str) if table_path_str else None

    if table_path is None or not table_path.exists():
        ds_dir = root / ".hpc_oda" / "cache" / "datasets" / "synthetic_job_runtime_tiny"
        table_path, _meta = _generate_tiny_runtime_dataset(ds_dir)

    ds_hash = table_hash(table_path)

    import pyarrow.parquet as pq

    table = pq.read_table(table_path)
    rows = table.to_pylist()

    split = _normalize_split(recipe_payload)

    model_ref = recipe_payload.get("model", {}) or {}
    model_id = str(model_ref.get("id", "model.job_runtime_baseline"))
    model_version = str(model_ref.get("version", "0.1.0"))
    split_method = split.get("method", "fixed")
    metric_defs = recipe_payload.get("metrics", []) or []

    if model_id == "model.job_runtime_baseline" and split_method == "fixed":
        metrics, metrics_payload = _run_fixed_baseline_benchmark(
            rows, split=split, metric_defs=metric_defs
        )
    elif model_id == "model.job_runtime_xgboost" and split_method == "rolling_hourly":
        metrics, metrics_payload = _run_rolling_hourly_xgboost_benchmark(
            rows, split=split, metric_defs=metric_defs
        )
    else:
        raise typer.BadParameter(
            f"Unsupported model/split combination: model={model_id}, split.method={split_method}"
        )

    prov = build_provenance(
        input_schema=input_schema,
        result_schema="oda.result.v0.1.0",
        inputs=[recipe, table_path],
        project_root=root,
        capture_packages=True,
    )

    run_id = f"benchmark-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    bundle_dir = _result_bundle_dir(root, run_id)

    result_payload: dict[str, Any] = {
        "schema_version": "oda.result.v0.1.0",
        "recipe_id": recipe_id,
        "problem_domain": ["job-runtime-prediction"],
        "created_at": _now_utc_iso(),
        "metrics": metrics,
        "provenance": prov,
        "model": {"id": model_id, "version": model_version},
        "dataset": {
            "id": str(dataset.get("id", "synthetic_job_runtime_tiny")),
            "schema_version": input_schema,
            "hash": ds_hash,
        },
        "notes": f"Benchmark run for {recipe_id}.",
    }

    validate_json(result_payload, "oda.result.v0.1.0")
    write_result_bundle(
        bundle_dir, result=result_payload, metrics=metrics_payload, provenance=prov, validate=True
    )

    console.print(f"[green]Benchmark complete[/green] → runs/{run_id}/")


@app.command("analyze")
def analyze_my_data(
    data: Annotated[Path, typer.Option("--data", exists=True, readable=True)],
    out: Annotated[Path, typer.Option("--out", exists=False)] = Path("reports"),
) -> None:
    """
    Analyze a local dataset with the baseline model and emit a report bundle.
    """
    root = Path.cwd()
    _ensure_dirs(root)

    if data.is_dir():
        data_path = data / "data.parquet"
        manifest_path = data / "manifest.json"
    else:
        data_path = data
        manifest_path = data.with_name("manifest.json")

    if not data_path.exists():
        raise typer.BadParameter(f"Parquet data not found: {data_path}")

    ds_hash = table_hash(data_path)

    import pyarrow.parquet as pq

    table = pq.read_table(data_path)
    rows = table.to_pylist()
    if not rows:
        raise typer.BadParameter("Dataset is empty; cannot analyze.")

    y_true = [float(r["runtime_seconds"]) for r in rows if r.get("runtime_seconds") is not None]
    model = JobRuntimeBaselineModel()
    model.fit(rows)
    y_pred = model.predict(rows)

    metric_defs = [
        {"name": "mae", "target": "runtime_seconds"},
        {"name": "rmse", "target": "runtime_seconds"},
    ]
    metrics = _compute_regression_metrics_from_defs(y_true, y_pred, metric_defs)

    prov = build_provenance(
        input_schema="oda.job.v0.1.0",
        result_schema="oda.result.v0.1.0",
        inputs=[data_path],
        project_root=root,
        capture_packages=True,
    )

    report_id = f"analysis-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    out_dir = out if out.is_absolute() else root / out
    out_dir = out_dir / report_id
    out_dir.mkdir(parents=True, exist_ok=True)

    report_payload = {
        "summary": {"report_id": report_id, "created_at": _now_utc_iso()},
        "model": {"id": "model.job_runtime_baseline", "version": "0.1.0"},
        "dataset": {
            "id": str(manifest_path) if manifest_path.exists() else str(data_path),
            "schema_version": "oda.job.v0.1.0",
            "hash": ds_hash,
        },
        "metrics": metrics,
        "metrics_definitions": metric_defs,
        "provenance": prov,
    }

    json_path = out_dir / "analysis.json"
    json_path.write_text(
        json.dumps(report_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    html = render_analysis_html(report_payload)
    html_path = out_dir / "index.html"
    html_path.write_text(html, encoding="utf-8")

    console.print(f"[green]Analysis report[/green]: {json_path}")
    console.print(f"[green]Analysis HTML[/green]: {html_path}")


@app.command()
def validate(path: Path) -> None:
    """
    Validate artifacts (v0.1):
    - If path is a result bundle dir, validate result.json against schema.
    - If path is a manifest.json, validate it against manifest schema.
    - If path is a parquet file, validate first rows as oda.job.v0.1.0.
    """
    if not path.exists():
        raise typer.BadParameter(f"Path not found: {path}")

    if path.is_dir() and (path / "result.json").exists():
        from hpc_oda_commons.kernel.artifacts.result_bundle import validate_result_bundle

        validate_result_bundle(path)
        console.print(f"[green]Valid result bundle[/green]: {path}")
        return

    if path.is_file() and path.name == "manifest.json":
        from hpc_oda_commons.kernel.artifacts.manifest import validate_manifest

        validate_manifest(path)
        console.print(f"[green]Valid manifest[/green]: {path}")
        return

    if path.is_file() and path.suffix == ".parquet":
        report_path = path.with_suffix(path.suffix + ".quality.json")
        report = validate_parquet_with_quality(
            path, schema_id="oda.job.v0.1.0", report_path=report_path
        )
        console.print(f"[green]Valid parquet rows[/green]: {path}")
        console.print(
            f"[green]Quality report written[/green]: {report_path} "
            f"(rows={report.get('row_count', 0)})"
        )
        return

    console.print(f"[yellow]No validation rule for[/yellow]: {path}")


@app.command()
def leaderboard(
    runs: Annotated[
        Path, typer.Option("--runs", exists=False, help="Runs directory containing result bundles.")
    ] = Path("runs"),
    out: Annotated[
        Path, typer.Option("--out", exists=False, help="Output directory for leaderboard.")
    ] = Path("leaderboard"),
) -> None:
    """
    Generate leaderboard.json + index.html from result bundles under runs/.
    """
    runs_dir = runs if runs.is_absolute() else Path.cwd() / runs
    out_dir = out if out.is_absolute() else Path.cwd() / out

    leaderboard_data = build_leaderboard(runs_dir)
    json_path = write_leaderboard(leaderboard_data, out_dir)

    html = render_leaderboard_html(leaderboard_data)
    html_path = out_dir / "index.html"
    html_path.write_text(html, encoding="utf-8")

    console.print(f"[green]Leaderboard JSON[/green]: {json_path}")
    console.print(f"[green]Leaderboard HTML[/green]: {html_path}")
