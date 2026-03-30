# hpc-oda-commons (v0.1) White Paper: A Local-First, Artifact-Centric Commons for HPC Operational Data Analytics

## Abstract

High Performance Computing (HPC) operational data analytics (ODA) is fragmented: each site and research group often develops bespoke log parsers, schemas, and evaluation pipelines that are difficult to reproduce or compare. **hpc-oda-commons** addresses this by establishing a small, testable set of contracts (schemas and artifacts) and a pragmatic end-to-end toolchain that makes ODA workflows **discoverable (Find)**, **reproducible/comparable (Compare)**, and **easy to adopt locally (Run)**.

This document describes the system as it exists today: a **v0.1 vertical slice** focused on **SLURM job runtime prediction**, delivered as a Python package with a CLI, packaged schemas/recipes/datasets, deterministic benchmark execution, provenance capture, validation and data quality reports, and a static leaderboard generator.

## 1) The Problem This Solves

HPC ODA efforts commonly face the same structural problems:

1. **Semantic fragmentation**
   - Scheduler logs, accounting exports, and monitoring streams vary by site and configuration.
   - Even when fields overlap (job id, start/end time, resources), naming and semantics drift.
2. **Comparability gaps**
   - “Benchmarking” often means running different metrics, splits, preprocessing, or dataset versions.
   - Reported scores are difficult to compare across institutions or even within the same lab over time.
3. **Reproducibility gaps**
   - Results frequently lack provenance: input versions, schema versions, code version, environment snapshot.
   - Minor changes to parsing or evaluation pipelines can silently shift results.
4. **Adoption friction**
   - Operators need local-first tools that do not require uploading sensitive logs.
   - Getting from “clone repo” to “run something meaningful” is often too slow.

The net effect is that promising ODA ideas remain siloed, and the community lacks a reliable substrate for “apples-to-apples” evaluation.

## 2) What This Is

**hpc-oda-commons** is a **foundational, community-oriented repository and Python package** that operationalizes shared contracts:

1. **Versioned schemas** (JSON Schema) that define canonical artifacts.
2. **Canonical artifacts** (Parquet tables, manifests, result bundles) treated as the primary interface.
3. **A CLI-first user experience** (v0.1) that supports the 10-minute workflow: init → ingest → validate → analyze → benchmark → leaderboard.
4. **An offline registry snapshot** that makes official adapters/models/recipes discoverable without a server.

In v0.1, the scope is intentionally narrow:

- **Domain:** SLURM job runtime prediction
- **Source:** `slurmctld` logs (minimal patterns)
- **Data:** tiny packaged synthetic dataset (offline) + manifest
- **Models:** deterministic baseline (mean predictor) + XGBoost with rolling evaluation
- **Benchmark:** recipe-driven execution with regression metrics (MAE, RMSE)
- **Outputs:** schema-valid artifacts and static leaderboard generation

## 3) What It Does

At a high level, the system provides three user-visible capabilities.

### Find (offline discoverability)

- `hpc-oda browse` lists official components from a bundled registry snapshot.
- `hpc-oda info <entry_id>` prints metadata and compatibility.

### Run (local-first ingestion, validation, and analysis)

- `hpc-oda init` creates a local project structure (`data/`, `runs/`, `.hpc_oda/`).
- `HPC_ODA_OFFLINE=1 hpc-oda run-baseline` generates and caches a deterministic tiny synthetic dataset locally
  (offline), runs the baseline model, computes regression metrics (MAE/RMSE), and produces a result bundle
  under `runs/`. This is the fastest “sanity check” that the end-to-end toolchain is installed and working.
- `hpc-oda ingest slurmctld --path <log>` parses logs into schema-aligned rows, writes Parquet + `manifest.json`.
- `hpc-oda validate <path>` validates:
  - result bundles (`result.json` schema)
  - manifests (`manifest.json` schema)
  - parquet (row validation + semantic checks + quality report `*.quality.json`)
- `hpc-oda analyze --data <parquet|dir>` runs a baseline analysis over a local dataset and emits:
  - `analysis.json`
  - `index.html` (lightweight HTML report)

### Compare (recipes, benchmark execution, result bundles, leaderboard)

- `hpc-oda benchmark <recipe.yml>` executes a recipe-driven benchmark and writes a **result bundle** under `runs/`.
- `hpc-oda leaderboard --runs runs --out leaderboard` aggregates bundles into:
  - `leaderboard.json`
  - `index.html`

## 4) How It Does It (Technical Architecture)

The system is built around a simple premise: **artifacts are the interface**. Every pillar writes and reads stable, versioned artifacts.

### 4.1 Core Contracts: Schemas and IDs

Schemas are packaged JSON Schemas, loaded by ID at runtime:

- `oda.job.v0.1.0` (job table rows, runtime prediction slice)
- `oda.manifest.v0.1.0` (manifests for ingested artifacts)
- `oda.result.v0.1.0` (result bundles)
- `oda.registry.v0.1.0` (registry snapshot)
- `oda.recipe.v0.1.0` (benchmark recipes)
- `oda.mdl.v0.1.0` (metric definitions; “MDL v0”)
- `oda.mapping.v0.1.0` (field mapping specifications for data ingestion)

Implementation:

- `hpc_oda_commons.kernel.schemas.load_schema(schema_id)` resolves packaged schema resources under `src/hpc_oda_commons/schemas/...`.
- `hpc_oda_commons.kernel.validate.validate_json(...)` performs Draft 2020-12 JSON Schema validation.

### 4.2 Artifact Types and Layout

**ODA Table (Parquet)**

- Stored as Parquet and validated row-wise against `oda.job.v0.1.0`.
- Written/read via `hpc_oda_commons.kernel.artifacts.oda_table`.

**Manifest (JSON)**

- Written alongside ingested parquet outputs.
- Captures:
  - schema version
  - adapter identity/version
  - inputs
  - transformations ledger
  - provenance (including hashes)
- Implemented in `hpc_oda_commons.kernel.artifacts.manifest`.

**Result Bundle (Directory)**

Benchmarks and baseline runs write a directory containing:

- `result.json` (schema-validated via `oda.result.v0.1.0`)
- `metrics.json` (includes metric values and, for benchmarks, metric definitions)
- `provenance.json` (environment/code/inputs)

Implemented in `hpc_oda_commons.kernel.artifacts.result_bundle`.

### 4.3 Provenance and Reproducibility

Provenance is constructed in `hpc_oda_commons.kernel.provenance.build_provenance(...)` and includes:

- schema versions (input/result)
- environment snapshot:
  - python version
  - optional `pip freeze` capture
- code snapshot:
  - installed package version
  - git commit if available
- input hashing:
  - sha256 of file content (when available)
  - size and mtime

This enables “result bundles as evidence”: a leaderboard entry can trace back to exactly what ran, on what, and with which inputs.

### 4.4 Safe Transformations (Local-First Data Handling)

The system is designed to run without sending data off-cluster. When a site needs to share derived artifacts, it can apply explicit transformations:

- `hpc_oda_commons.kernel.transformations.hash_identifier(...)`

Transformations are recorded in the manifest’s transformation ledger.

### 4.5 Adapter Contract and slurmctld Ingestion

Adapters follow a minimal protocol:

- `SourceAdapter` with `metadata: AdapterMetadata`
- `parse(path) -> list[dict]` returning schema-aligned rows

v0.1 official adapter:

- `hpc_oda_commons.adapters.slurmctld.adapter.SlurmctldAdapter`
- It parses minimal slurmctld patterns:
  - allocation lines (job start + resources)
  - completion lines (job end)
- It computes `runtime_seconds = end_time - start_time` and **skips incomplete jobs** to preserve schema validity.

Ingestion flow:

1. Parse log → rows
2. Write Parquet (`data.parquet`)
3. Validate parquet rows + semantic checks
4. Emit `manifest.json`

The CLI also prints deterministic “ingest checks” (warnings about missing required fields or timestamp inconsistencies).

### 4.6 Benchmark Recipes and MDL v0

Benchmarks are defined by recipes (`oda.recipe.v0.1.0`) and metric definitions (`oda.mdl.v0.1.0`).

Validation rules enforced by `hpc_oda_commons.benchmark.recipes.validate_recipe(...)` include:

- required recipe fields are present
- metrics are MDL-valid
- required metrics for v0.1 runtime prediction are included:
  - `mae`
  - `rmse`
- all metrics share the same target field (v0.1 expects `runtime_seconds`)

Execution (`hpc_oda_commons.benchmark.runner`):

- loads recipe and dataset parquet
- resolves the model and split strategy:
  - **fixed split** with the baseline model (deterministic train/test partition)
  - **rolling split** with the XGBoost model (sliding window evaluation simulating production retraining)
- computes metrics and writes a result bundle under `runs/`

### 4.7 Leaderboard Generation

Leaderboards are generated from result bundles:

- `hpc_oda_commons.benchmark.results.build_leaderboard(...)`
  - scans `runs/` for `result.json`
  - validates bundles
  - aggregates into `leaderboard.json`
  - robustly skips invalid bundles

HTML is generated via `hpc_oda_commons.tools.report.html.render_leaderboard_html(...)`.

### 4.8 Minimal Intelligence Layer (Assistive, Deterministic)

The “intelligence layer” in today’s codebase is intentionally modest and testable:

- **Mapping suggestions:** deterministic suggestions based on observed row fields
  - `hpc_oda_commons.intelligence.mapping.suggest_job_runtime_mappings(...)`
- **Synthetic scoring:** lightweight coverage/realism proxies (missingness, runtime stats, diversity)
  - `hpc_oda_commons.intelligence.synthetic_scoring.score_job_runtime_rows(...)`
- **Metadata graph:** static graph derived from the registry snapshot (entries, tags, domains, schemas)
  - `hpc_oda_commons.intelligence.metadata_graph.build_metadata_graph(...)`

These are library-level APIs available for programmatic use but not currently integrated into the CLI.

### 4.9 Packaging, Offline Support, and CI

Key packaging decisions (v0.1):

- Schemas, registry snapshot, recipes, and tiny runtime dataset are packaged as data files.
- Recipe and schema validation scripts exist for CI:
  - `python scripts/validate_recipes.py`
  - `python scripts/validate_schemas.py`

CI runs:

- `ruff check .` and `ruff format . --check`
- unit tests (`pytest -q -m "not integration"`)
- offline integration tests (`pytest -q -m integration` with `HPC_ODA_OFFLINE=1`)
- recipe validation script

## 5) How This Moves Toward Solving the Problem

This v0.1 slice is deliberately narrow, but it establishes the foundation needed for community-scale progress:

1. **Standardization** via versioned schemas and schema-backed validation
2. **Comparability** via recipe-driven benchmarking and canonical result bundles
3. **Reproducibility** via provenance capture and deterministic tiny dataset runs
4. **Adoption** via a CLI-first, local-first workflow that works offline
5. **Community alignment** via a discoverable registry snapshot and an SER template for schema evolution

The practical impact is that sites and researchers can now share comparable *artifacts* rather than ad hoc scripts and screenshots.

## 6) What Is Left To Be Done

The current system is a stable vertical slice, not yet a fully general platform. The major next steps are:

1. **Additional adapters and data sources**
   - support for additional ingestion sources beyond slurmctld and Parquet exports (e.g., PBS/Torque, sacct)
2. **Environment locking**
   - recipes should carry a minimal environment descriptor (constraints/conda/container reference)
   - provenance should record environment descriptors and hashes
3. **Richer validation and transformation policy**
   - expand quality rules in a versioned way
   - additional privacy-preserving transformations (timestamp binning, value redaction)
4. **More data**
   - add external dataset references with immutable identifiers/checksums
5. **New problem domains**
   - extend beyond runtime prediction to job failure prediction, resource utilization, queue wait-time estimation
6. **Publishing and automation**
   - automate leaderboard publication (e.g., GitHub Pages) from validated result bundles

## 7) Future Vision for the HPC ODA Community

In a mature state, hpc-oda-commons can function as a shared substrate for HPC ODA:

1. **A community-governed semantic “Rosetta Stone”**
   - schemas evolve via SERs with clear compatibility rules and deprecation paths
2. **A benchmark and reproducibility vault**
   - recipes represent reproducible scientific claims
   - CI-backed benchmark runs produce verifiable result bundles
3. **A trusted leaderboard**
   - each entry links to provenance-complete bundles
   - results remain comparable as schemas and recipes evolve
4. **A low-friction operator toolkit**
   - sites can ingest locally, validate, transform, and run comparable evaluations without data exfiltration
5. **An adaptive ecosystem**
   - mapping hints improve ingestion ergonomics
   - synthetic datasets evolve using benchmark feedback
   - metadata graphs and structured registry metadata enable “smart find” experiences

The long-term payoff is a community where ODA progress is cumulative: models, datasets, adapters, and evaluation practices can be shared and improved without re-litigating the basics each time.

## Appendix A: CLI Commands (v0.1)

```bash
hpc-oda --help
hpc-oda init
hpc-oda browse
hpc-oda info model.job_runtime_baseline

HPC_ODA_OFFLINE=1 hpc-oda run-baseline
hpc-oda ingest slurmctld --path /path/to/slurmctld.log
hpc-oda validate data/ingested/slurmctld/<run>/data.parquet
hpc-oda analyze --data data/ingested/slurmctld/<run>

HPC_ODA_OFFLINE=1 hpc-oda benchmark hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml
hpc-oda leaderboard --runs runs --out leaderboard
```

## Appendix B: Primary Artifact Outputs

- Ingest:
  - `data/ingested/slurmctld/<run>/data.parquet`
  - `data/ingested/slurmctld/<run>/manifest.json`
  - `data/ingested/slurmctld/<run>/data.parquet.quality.json` (after validation)
- Benchmark / baseline:
  - `runs/<run>/result.json`
  - `runs/<run>/metrics.json`
  - `runs/<run>/provenance.json`
- Analysis:
  - `reports/analysis-*/analysis.json`
  - `reports/analysis-*/index.html`
- Leaderboard:
  - `leaderboard/leaderboard.json`
  - `leaderboard/index.html`
