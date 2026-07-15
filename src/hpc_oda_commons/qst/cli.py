from __future__ import annotations

import difflib
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

from hpc_oda_commons.adapters.slurmctld.adapter import SlurmctldAdapter
from hpc_oda_commons.benchmark.leaderboard_display import resolve_dataset_folder_name
from hpc_oda_commons.benchmark.recipes import load_recipe
from hpc_oda_commons.benchmark.results import build_leaderboard, write_leaderboard
from hpc_oda_commons.benchmark.run_extras import (
    needs_artifact_capture,
    parse_run_extras,
    write_run_extras,
)
from hpc_oda_commons.benchmark.runner import (
    run_fixed_baseline,
    run_fixed_uopc,
    run_rolling_baseline,
    run_rolling_embedding_knn,
    run_rolling_mlp,
    run_rolling_random_forest,
    run_rolling_tfidf_knn,
    run_rolling_xgboost,
)
from hpc_oda_commons.datasets.synthetic import (
    generate_tiny_runtime_dataset,
)
from hpc_oda_commons.ingest.jobs_parquet.apply import apply_mapping_spec
from hpc_oda_commons.ingest.jobs_parquet.profile import profile_parquet
from hpc_oda_commons.ingest.jobs_parquet.suggest import suggest_mapping
from hpc_oda_commons.ingest.jobs_parquet.wizard import (
    OPTIONAL_FIELDS as JOB_OPTIONAL_FIELDS,
)
from hpc_oda_commons.ingest.jobs_parquet.wizard import (
    REQUIRED_FIELDS as JOB_REQUIRED_FIELDS,
)
from hpc_oda_commons.ingest.jobs_parquet.wizard import (
    build_mapping_spec_interactive,
)
from hpc_oda_commons.kernel.artifacts.manifest import new_manifest, write_manifest
from hpc_oda_commons.kernel.artifacts.mapping_spec import (
    read_mapping_spec,
    write_mapping_spec,
)
from hpc_oda_commons.kernel.artifacts.oda_table import table_hash, write_table_parquet
from hpc_oda_commons.kernel.artifacts.result_bundle import write_result_bundle
from hpc_oda_commons.kernel.metrics import (
    compute_regression_metrics_from_defs,
)
from hpc_oda_commons.kernel.provenance import build_provenance
from hpc_oda_commons.kernel.serialization import to_jsonable
from hpc_oda_commons.kernel.validate import validate_json
from hpc_oda_commons.models.job_runtime_baseline.model import JobRuntimeBaselineModel
from hpc_oda_commons.qst.commands.browse import browse
from hpc_oda_commons.qst.commands.datasets import datasets_fetch, datasets_prepare
from hpc_oda_commons.qst.commands.embed import embed
from hpc_oda_commons.qst.commands.info import info
from hpc_oda_commons.qst.ingest_suggestions import build_ingest_suggestions
from hpc_oda_commons.schema.validator import (
    collect_job_table_type_issues,
    validate_parquet_with_quality,
)
from hpc_oda_commons.tools.report import (
    render_analysis_html,
    render_leaderboard_console,
    render_leaderboard_html,
)

app = typer.Typer(add_completion=False, help="hpc-oda-commons Quickstart Toolkit (v0.1)")
ingest_app = typer.Typer(
    add_completion=False, help="Ingest operational data into canonical ODA artifacts."
)
app.add_typer(ingest_app, name="ingest")
datasets_app = typer.Typer(
    add_completion=False, help="Discover and fetch public operational datasets."
)
app.add_typer(datasets_app, name="datasets")
datasets_app.command("fetch")(datasets_fetch)
datasets_app.command("prepare")(datasets_prepare)
app.command()(browse)
app.command()(info)
app.command()(embed)

console = Console()

SLURMCTLD_PATH_OPT = typer.Option(..., "--path", exists=True, readable=True)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ensure_dirs(project_root: Path) -> None:
    (project_root / ".hpc_oda").mkdir(parents=True, exist_ok=True)
    (project_root / "data").mkdir(parents=True, exist_ok=True)
    (project_root / "runs").mkdir(parents=True, exist_ok=True)


def _result_bundle_dir(project_root: Path, run_id: str) -> Path:
    return project_root / "runs" / run_id


def _expected_job_fields() -> tuple[str, ...]:
    return tuple(JOB_REQUIRED_FIELDS) + tuple(JOB_OPTIONAL_FIELDS)


def _short_row_preview(row: dict[str, Any], *, max_value_chars: int = 120) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        normalized = to_jsonable(value)
        if isinstance(normalized, str) and len(normalized) > max_value_chars:
            out[key] = normalized[: max_value_chars - 3] + "..."
        else:
            out[key] = normalized
    return out


def _read_parquet_head(
    path: Path, *, max_rows: int = 3
) -> tuple[list[str], int, list[dict[str, Any]]]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(path)
    nrows = int(parquet.metadata.num_rows) if parquet.metadata is not None else 0
    columns = list(parquet.schema.names)

    head: list[dict[str, Any]] = []
    if max_rows > 0 and nrows > 0:
        for batch in parquet.iter_batches(batch_size=max_rows):
            head = pa.Table.from_batches([batch]).to_pylist()
            break

    return columns, nrows, head[:max_rows]


def _print_parquet_preview(path: Path, *, label: str, max_rows: int = 3) -> None:
    columns, row_count, head_rows = _read_parquet_head(path, max_rows=max_rows)
    console.print(f"[blue]{label}[/blue]: {path}")
    console.print(f"Rows: {row_count}")
    console.print(f"Columns ({len(columns)}): {', '.join(columns)}")
    if not head_rows:
        console.print("[yellow]No rows available for preview.[/yellow]")
        return
    console.print(f"Sample rows (head {len(head_rows)}):")
    for row in head_rows:
        console.print(json.dumps(_short_row_preview(row), ensure_ascii=True, sort_keys=True))


def _print_time_format_examples() -> None:
    console.print("[blue]Time format examples[/blue]")
    console.print("timestamp iso8601: 2026-01-01T00:00:00Z")
    console.print("timestamp epoch_s: 1735689600")
    console.print("timestamp epoch_ms: 1735689600000")
    console.print("timestamp epoch_us: 1735689600000000")
    console.print("duration seconds: 3600")
    console.print("duration minutes: 60")
    console.print("duration hours: 1.0")
    console.print("duration HH:MM:SS: 01:00:00")


def _print_expected_field_coverage_from_suggestions(
    suggestions: dict[str, list[dict[str, Any]]],
) -> None:
    expected = _expected_job_fields()
    missing_candidates = [field for field in expected if not suggestions.get(field)]
    if missing_candidates:
        console.print(
            "[yellow]Expected canonical fields with no source-column candidates[/yellow]: "
            + ", ".join(missing_candidates)
        )
    else:
        console.print(
            "[green]All expected canonical fields have at least one source candidate.[/green]"
        )


def _print_mapping_coverage(
    *,
    mapping_payload: dict[str, Any],
    available_columns: list[str],
) -> None:
    fields = mapping_payload.get("fields", {})
    if not isinstance(fields, dict):
        console.print("[yellow]Mapping spec has no fields section.[/yellow]")
        return

    expected = _expected_job_fields()
    missing_expected: list[str] = []
    used_input_columns: set[str] = set()

    for field in expected:
        spec = fields.get(field, {})
        if not isinstance(spec, dict):
            missing_expected.append(field)
            continue
        source = spec.get("source")
        derive = spec.get("derive")
        if source:
            used_input_columns.add(str(source))
        if not source and not derive:
            missing_expected.append(field)

    if missing_expected:
        console.print(
            "[yellow]Expected canonical fields not provided by mapping[/yellow]: "
            + ", ".join(missing_expected)
        )
    else:
        console.print("[green]Mapping provides all expected canonical fields.[/green]")

    unused_input = [column for column in available_columns if column not in used_input_columns]
    if unused_input:
        console.print(
            "[yellow]Input columns not used by mapping[/yellow]: " + ", ".join(unused_input)
        )
    else:
        console.print("[green]All input columns are used by the mapping.[/green]")


def _state_source_column(mapping_payload: dict[str, Any]) -> str | None:
    fields = mapping_payload.get("fields", {})
    if not isinstance(fields, dict):
        return None
    state_spec = fields.get("state", {})
    if not isinstance(state_spec, dict):
        return None
    source = state_spec.get("source")
    if source is None or str(source).strip() == "":
        return None
    return str(source)


def _collect_state_counts(path: Path, state_source_column: str) -> dict[str, int]:
    import pyarrow.parquet as pq

    table = pq.read_table(path, columns=[state_source_column])
    values = table.column(state_source_column).to_pylist()
    counts: Counter[str] = Counter()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        counts[text] += 1
    return dict(counts)


def _validate_state_filter_selection(
    selected_values: list[str], valid_values: set[str]
) -> tuple[set[str] | None, dict[str, list[str]]]:
    cleaned = [value.strip() for value in selected_values if value.strip()]
    if not cleaned:
        return None, {}

    invalid = [value for value in cleaned if value not in valid_values]
    if invalid:
        suggestions = {
            value: difflib.get_close_matches(value, sorted(valid_values), n=3, cutoff=0.6)
            for value in invalid
        }
        return None, suggestions
    return set(cleaned), {}


def _prompt_state_allowlist(
    *,
    path: Path,
    mapping_payload: dict[str, Any],
    non_interactive: bool,
) -> set[str] | None:
    if non_interactive:
        return None

    if not sys.stdin.isatty():
        console.print(
            "[blue]State filter prompt skipped[/blue]: non-interactive input stream detected."
        )
        return None

    state_source = _state_source_column(mapping_payload)
    if state_source is None:
        console.print(
            "[yellow]State filter unavailable[/yellow]: mapping does not provide a state source column."
        )
        return None

    try:
        counts = _collect_state_counts(path, state_source)
    except Exception as exc:
        console.print(
            f"[yellow]State filter unavailable[/yellow]: could not profile state values ({exc})."
        )
        return None

    if not counts:
        console.print(
            "[yellow]State filter unavailable[/yellow]: state column has no non-empty values in input data."
        )
        return None

    apply_filter = typer.prompt(
        "Filter rows by state? [y/N]",
        default="n",
    )
    if apply_filter.strip().lower() not in {"y", "yes"}:
        return None

    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    top = ranked[:20]
    console.print("[blue]State options (top 20 by frequency)[/blue]:")
    for value, count in top:
        console.print(f"- {value}: {count}")

    valid_values = set(counts.keys())
    while True:
        raw = typer.prompt("Enter comma-separated state values to include (exact match)")
        selected, suggestions = _validate_state_filter_selection(raw.split(","), valid_values)
        if selected is not None:
            console.print("[green]State filter selected[/green]: " + ", ".join(sorted(selected)))
            return selected
        if not raw.strip():
            console.print(
                "[yellow]No values provided. Please enter at least one state value.[/yellow]"
            )
            continue

        invalid_values = [
            value.strip()
            for value in raw.split(",")
            if value.strip() and value.strip() not in valid_values
        ]
        console.print("[red]Invalid state values[/red]: " + ", ".join(invalid_values))
        for value in invalid_values:
            matches = suggestions.get(value, [])
            if matches:
                console.print(f"  suggestion for '{value}': {', '.join(matches)}")
            else:
                console.print(f"  no close match for '{value}'")


def _print_validation_issues(report: dict[str, Any]) -> None:
    validation = report.get("validation", {})
    if not isinstance(validation, dict):
        return

    schema_count = int(validation.get("schema_error_count", 0))
    semantic_count = int(validation.get("semantic_error_count", 0))
    if schema_count == 0 and semantic_count == 0:
        console.print("[green]Validation summary[/green]: no schema or semantic issues detected.")
        return

    console.print(
        "[yellow]Validation summary[/yellow]: "
        f"schema_errors={schema_count}, semantic_errors={semantic_count}. "
        "Ingest continued; inspect sample rows below."
    )

    for section_name, display in (
        ("schema_errors", "Schema issues"),
        ("semantic_errors", "Semantic issues"),
    ):
        entries = validation.get(section_name, [])
        if not isinstance(entries, list) or not entries:
            continue
        console.print(f"[yellow]{display}[/yellow]:")
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            issue = str(entry.get("issue", "unknown issue"))
            count = int(entry.get("count", 0))
            console.print(f"- {issue} (count={count})")
            examples = entry.get("examples", [])
            if not isinstance(examples, list):
                continue
            for sample in examples[:3]:
                if not isinstance(sample, dict):
                    continue
                row_index = sample.get("row_index")
                row = sample.get("row")
                if not isinstance(row, dict):
                    continue
                preview = _short_row_preview(row)
                console.print(
                    "  row "
                    + str(row_index)
                    + ": "
                    + json.dumps(preview, ensure_ascii=True, sort_keys=True)
                )


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
    if method not in {"fixed", "rolling"}:
        raise typer.BadParameter(f"Unsupported split method: {method}")
    split["method"] = method
    return split


@app.command()
def init() -> None:
    """
    Initialize a local hpc-oda-commons project in the current directory.
    """
    root = Path.cwd()
    _ensure_dirs(root)

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
    table_path, _meta_path = generate_tiny_runtime_dataset(ds_dir)
    ds_hash = table_hash(table_path)

    import pyarrow.parquet as pq

    table = pq.read_table(table_path)
    rows = table.to_pylist()
    y_true = [float(r["runtime_seconds"]) for r in rows]

    model = JobRuntimeBaselineModel()
    train_eval_started = time.perf_counter()
    model.fit(rows)
    y_pred = model.predict(rows)

    metric_defs = [
        {"name": "mae", "target": "runtime_seconds"},
        {"name": "rmse", "target": "runtime_seconds"},
    ]
    metrics = compute_regression_metrics_from_defs(y_true, y_pred, metric_defs)
    total_train_eval_seconds = round(time.perf_counter() - train_eval_started, 3)
    metrics_payload: dict[str, Any] = {**metrics, "definitions": metric_defs}

    from hpc_oda_commons.kernel.integrity import check_integrity

    integrity = check_integrity(project_root=root)

    prov = build_provenance(
        input_schema="oda.job.v0.2.0",
        result_schema="oda.result.v0.1.0",
        inputs=[table_path],
        project_root=root,
        capture_packages=False,
        source_hash=integrity["code_hash"],
    )

    run_id = f"run-baseline-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    bundle_dir = _result_bundle_dir(root, run_id)

    result_payload: dict[str, Any] = {
        "schema_version": "oda.result.v0.1.0",
        "recipe_id": "run-baseline.offline_tiny",
        "problem_domain": ["job-runtime-prediction"],
        "created_at": _now_utc_iso(),
        "metrics": metrics,
        "integrity": integrity,
        "provenance": prov,
        "model": {"id": "model.job_runtime_baseline", "version": "0.1.0"},
        "dataset": {
            "id": "synthetic_job_runtime_tiny",
            "schema_version": "oda.job.v0.2.0",
            "hash": ds_hash,
        },
        "notes": "Offline baseline demo run (v0.1).",
        "timing": {"total_train_eval_seconds": total_train_eval_seconds},
    }

    validate_json(result_payload, "oda.result.v0.1.0")
    write_result_bundle(
        bundle_dir, result=result_payload, metrics=metrics_payload, provenance=prov, validate=True
    )

    console.print(f"[green]Baseline run complete[/green] → runs/{run_id}/")


@ingest_app.command("slurmctld")
def ingest_slurmctld(path: Path = SLURMCTLD_PATH_OPT) -> None:
    """
    Ingest slurmctld log into canonical oda.job.v0.2.0 Parquet + manifest.
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

    report_path = parquet_path.with_suffix(".parquet.quality.json")
    report = validate_parquet_with_quality(
        parquet_path,
        schema_id="oda.job.v0.2.0",
        sample=10,
        strict=False,
        report_path=report_path,
    )
    _print_validation_issues(report)

    prov = build_provenance(
        input_schema="oda.job.v0.2.0",
        result_schema="oda.result.v0.1.0",
        inputs=[path, parquet_path],
        project_root=root,
        capture_packages=False,
    )

    manifest = new_manifest(
        input_schema_version="oda.job.v0.2.0",
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
    Ingest a jobs Parquet export into canonical oda.job.v0.2.0 artifacts.
    """
    root = Path.cwd()
    _ensure_dirs(root)

    run_id = f"jobs-parquet-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    out_dir = root / "data" / "ingested" / "jobs_parquet" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    _print_parquet_preview(path, label="Input parquet preview", max_rows=3)
    _print_time_format_examples()

    profiles = profile_parquet(path, sample_rows=sample_rows)
    suggestions = suggest_mapping(profiles)
    _print_expected_field_coverage_from_suggestions(suggestions)
    available_columns = [profile.name for profile in profiles]

    mapping_payload: dict[str, Any]
    if mapping is None:
        if non_interactive:
            raise typer.BadParameter("Non-interactive mode requires --mapping.")
        mapping_payload = build_mapping_spec_interactive(
            profiles,
            suggestions,
            input_path=path,
            default_hash_identifiers=hash_identifiers,
        )
        mapping = out_dir / "mapping.yml"
        write_mapping_spec(mapping, mapping_payload, validate=True)
    else:
        mapping_payload = read_mapping_spec(mapping, validate=True)

    _print_mapping_coverage(
        mapping_payload=mapping_payload,
        available_columns=available_columns,
    )
    state_allowlist = _prompt_state_allowlist(
        path=path,
        mapping_payload=mapping_payload,
        non_interactive=non_interactive,
    )

    parquet_path = out_dir / "data.parquet"
    summary = apply_mapping_spec(
        path,
        mapping,
        parquet_path,
        batch_size=batch_size,
        skip_incomplete=True,
        state_allowlist=state_allowlist,
    )

    _print_parquet_preview(parquet_path, label="Canonical output preview", max_rows=3)

    report_path = parquet_path.with_suffix(".parquet.quality.json")
    report = validate_parquet_with_quality(
        parquet_path,
        schema_id="oda.job.v0.2.0",
        sample=10,
        strict=False,
        report_path=report_path,
    )
    _print_validation_issues(report)

    prov = build_provenance(
        input_schema="oda.job.v0.2.0",
        result_schema="oda.result.v0.1.0",
        inputs=[path, parquet_path, mapping],
        project_root=root,
        capture_packages=False,
    )

    manifest = new_manifest(
        input_schema_version="oda.job.v0.2.0",
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
def benchmark(
    recipe: Path,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Print progress updates during benchmark execution.",
        ),
    ] = False,
) -> None:
    """
    Run a benchmark recipe (v0.1 runtime prediction).
    Writes a result bundle under ./runs/.
    """
    root = Path.cwd()
    _ensure_dirs(root)

    recipe_payload = _load_recipe(recipe)
    recipe_id = str(recipe_payload.get("recipe_id", "recipe.unknown"))
    input_schema = str(recipe_payload.get("schema_version", "oda.job.v0.2.0"))

    dataset = recipe_payload.get("dataset", {}) or {}
    table_path_str = dataset.get("table_path")
    table_path = Path(table_path_str) if table_path_str else None

    if table_path is None or not table_path.exists():
        # The synthetic fallback only provides job-runtime data (runtime_seconds).
        # For any other problem domain it would silently substitute a dataset that
        # lacks the recipe's target column, surfacing later as a confusing
        # "No rows with a finite target value" error. Fail clearly instead.
        problem_domain = recipe_payload.get("problem_domain", []) or []
        if "job-runtime-prediction" not in problem_domain:
            raise typer.BadParameter(
                f"dataset table not found at {table_path_str!r}; the synthetic "
                "fallback only provides job-runtime data (runtime_seconds), which "
                f"does not satisfy problem_domain={problem_domain}. Provide the "
                "dataset before running this recipe."
            )
        ds_dir = root / ".hpc_oda" / "cache" / "datasets" / "synthetic_job_runtime_tiny"
        table_path, _meta = generate_tiny_runtime_dataset(ds_dir)
        if verbose:
            console.print(
                "[blue][verbose][/blue] dataset path missing in recipe; "
                f"using generated tiny dataset at {table_path}"
            )

    ds_hash = table_hash(table_path)

    import pyarrow.parquet as pq

    table = pq.read_table(table_path)
    # Fail loudly on stale v0.1 (ISO-string) job tables instead of letting the
    # missing native timestamps surface as a misleading downstream symptom.
    timestamp_type_issues = collect_job_table_type_issues(table)
    if timestamp_type_issues:
        raise typer.BadParameter(
            f"dataset at {table_path} has non-timestamp job-timestamp columns "
            f"({'; '.join(timestamp_type_issues)}). This looks like oda.job v0.1 "
            "(ISO-string timestamps); v0.2 requires native Arrow timestamp columns. "
            "Re-ingest the data with the current version."
        )
    rows = table.to_pylist()

    split = _normalize_split(recipe_payload)

    model_ref = recipe_payload.get("model", {}) or {}
    model_id = str(model_ref.get("id", "model.job_runtime_baseline"))
    model_version = str(model_ref.get("version", "0.1.0"))
    split_method = split.get("method", "fixed")
    metric_defs = recipe_payload.get("metrics", []) or []
    run_extras = parse_run_extras(recipe_payload)
    capture_artifacts = needs_artifact_capture(run_extras)
    if verbose:
        console.print(
            "[blue][verbose][/blue] benchmark resolved: "
            f"recipe_id={recipe_id}, "
            f"model={model_id}@{model_version}, "
            f"split={split_method}, "
            f"table={table_path}, "
            f"rows={len(rows)}"
        )
        console.print(
            "[blue][verbose][/blue] metrics requested: "
            + ", ".join(str(m.get("name", "")) for m in metric_defs)
        )

    train_eval_started = time.perf_counter()
    if model_id == "model.job_runtime_baseline" and split_method == "fixed":
        metrics, metrics_payload, artifacts = run_fixed_baseline(
            rows, split=split, metric_defs=metric_defs, capture_artifacts=capture_artifacts
        )
    elif model_id == "model.job_power_uopc" and split_method == "fixed":
        metrics, metrics_payload, artifacts = run_fixed_uopc(
            rows,
            split=split,
            metric_defs=metric_defs,
            verbose=verbose,
            capture_artifacts=capture_artifacts,
        )
    elif model_id == "model.job_runtime_baseline" and split_method == "rolling":
        metrics, metrics_payload, artifacts = run_rolling_baseline(
            rows,
            split=split,
            metric_defs=metric_defs,
            verbose=verbose,
            capture_artifacts=capture_artifacts,
        )
    elif model_id == "model.job_runtime_tfidf_knn" and split_method == "rolling":
        metrics, metrics_payload, artifacts = run_rolling_tfidf_knn(
            rows,
            split=split,
            metric_defs=metric_defs,
            verbose=verbose,
            capture_artifacts=capture_artifacts,
        )
    elif model_id == "model.job_runtime_embedding_knn" and split_method == "rolling":
        metrics, metrics_payload, artifacts = run_rolling_embedding_knn(
            rows,
            split=split,
            metric_defs=metric_defs,
            verbose=verbose,
            capture_artifacts=capture_artifacts,
        )
    elif model_id == "model.job_runtime_xgboost" and split_method == "rolling":
        metrics, metrics_payload, artifacts = run_rolling_xgboost(
            rows,
            split=split,
            metric_defs=metric_defs,
            verbose=verbose,
            capture_artifacts=capture_artifacts,
        )
    elif model_id == "model.job_runtime_random_forest" and split_method == "rolling":
        metrics, metrics_payload, artifacts = run_rolling_random_forest(
            rows,
            split=split,
            metric_defs=metric_defs,
            verbose=verbose,
            capture_artifacts=capture_artifacts,
        )
    elif model_id == "model.job_runtime_mlp" and split_method == "rolling":
        metrics, metrics_payload, artifacts = run_rolling_mlp(
            rows,
            split=split,
            metric_defs=metric_defs,
            verbose=verbose,
            capture_artifacts=capture_artifacts,
        )
    else:
        raise typer.BadParameter(
            f"Unsupported model/split combination: model={model_id}, split.method={split_method}"
        )
    total_train_eval_seconds = round(time.perf_counter() - train_eval_started, 3)

    from hpc_oda_commons.kernel.integrity import check_integrity

    integrity = check_integrity(project_root=root)

    prov = build_provenance(
        input_schema=input_schema,
        result_schema="oda.result.v0.1.0",
        inputs=[recipe, table_path],
        project_root=root,
        capture_packages=True,
        source_hash=integrity["code_hash"],
    )

    run_id = f"benchmark-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_cfg = recipe_payload.get("run") or {}
    runs_rel = str(run_cfg.get("output_dir") or "runs")
    runs_dir = root / runs_rel
    bundle_dir = runs_dir / run_id
    if bundle_dir.exists() and not bool(run_cfg.get("overwrite", False)):
        raise typer.BadParameter(
            f"Result bundle already exists: {bundle_dir}. "
            "Set run.overwrite: true in the recipe to replace it."
        )
    runs_dir.mkdir(parents=True, exist_ok=True)

    result_payload: dict[str, Any] = {
        "schema_version": "oda.result.v0.1.0",
        "recipe_id": recipe_id,
        "problem_domain": ["job-runtime-prediction"],
        "created_at": _now_utc_iso(),
        "metrics": metrics,
        "integrity": integrity,
        "provenance": prov,
        "model": {"id": model_id, "version": model_version},
        "dataset": {
            "id": resolve_dataset_folder_name(
                str(dataset.get("id", "")),
                table_path=str(table_path) if table_path is not None else None,
            )
            or "synthetic_job_runtime_tiny",
            "schema_version": input_schema,
            "hash": ds_hash,
        },
        "notes": f"Benchmark run for {recipe_id}.",
        "timing": {"total_train_eval_seconds": total_train_eval_seconds},
    }

    validate_json(result_payload, "oda.result.v0.1.0")
    write_result_bundle(
        bundle_dir, result=result_payload, metrics=metrics_payload, provenance=prov, validate=True
    )

    extras_written: list[str] = []
    if capture_artifacts:
        extras_written = write_run_extras(bundle_dir, run_extras, artifacts)

    if verbose:
        validated_str = "yes" if integrity["validated"] else "NO"
        console.print(
            f"[blue][verbose][/blue] integrity: validated={validated_str} "
            f"code_hash={integrity['code_hash'][:12] if integrity['code_hash'] else 'unknown'}..."
        )
        console.print(
            "[blue][verbose][/blue] benchmark metrics: "
            + ", ".join(f"{k}={v:.6f}" for k, v in sorted(metrics.items()))
        )
        console.print(f"[blue][verbose][/blue] result bundle written: {bundle_dir}")
        if extras_written:
            console.print("[blue][verbose][/blue] run extras written: " + ", ".join(extras_written))

    console.print(f"[green]Benchmark complete[/green] → {runs_rel}/{run_id}/")


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
    metrics = compute_regression_metrics_from_defs(y_true, y_pred, metric_defs)

    prov = build_provenance(
        input_schema="oda.job.v0.2.0",
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
            "schema_version": "oda.job.v0.2.0",
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
    - If path is a parquet file, validate first rows as oda.job.v0.2.0.
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
            path, schema_id="oda.job.v0.2.0", report_path=report_path
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

    render_leaderboard_console(leaderboard_data, console=console)

    console.print(f"[green]Leaderboard JSON[/green]: {json_path}")
    console.print(f"[green]Leaderboard HTML[/green]: {html_path}")


@app.command("record-hash")
def record_hash_cmd() -> None:
    """Record the current source code hash for this git commit.

    Appends a (git_commit, source_hash) entry to integrity/known_hashes.json.
    Run this after tests pass on a clean commit to register it as validated.
    """
    from hpc_oda_commons.kernel.integrity import record_hash

    result = record_hash(project_root=Path.cwd())
    if result["git_commit"] is None:
        console.print("[yellow]Warning[/yellow]: not in a git repository, no commit to record.")
        return
    if result["source_hash"] is None:
        console.print("[yellow]Warning[/yellow]: could not resolve package directory.")
        return
    console.print(
        f"[green]Recorded[/green]: commit={result['git_commit'][:12]}... "
        f"hash={result['source_hash'][:12]}..."
    )
