# v0.1 Project Charter — hpc-oda-commons (Runtime Prediction Vertical Slice)

**Status:** Draft (intended to be committed as `docs/concepts/v0_1_charter.md`)  
**Release Target:** v0.1.0  
**Last Updated:** 2026-02-03

---

## 1. Purpose

The purpose of v0.1 is to deliver a **complete, working vertical slice** of hpc-oda-commons that demonstrates the core value proposition:

- **Find**: discover compatible adapters/models/recipes offline via a curated registry snapshot
- **Run**: ingest local operational logs safely, validate them, and run a baseline model
- **Compare**: run a benchmark recipe that produces comparable metrics and a reproducible result bundle

v0.1 is explicitly focused on proving the project’s viability and usability through a fast, low-friction workflow.

**Find Acceptance (v0.1):** Find is satisfied when `hpc-oda browse` and `hpc-oda info` work offline using the bundled `registry/snapshot.json`, and they list the baseline slurmctld adapter, baseline runtime prediction model, and the `baseline_tiny` recipe with compatibility metadata (schema versions + supported source).
**Run Acceptance (v0.1):** Run is satisfied when a user can ingest slurmctld logs locally into `oda.job.v0.1.0` Parquet + manifest, validate them successfully (schema + minimal logical checks), and run the baseline runtime prediction model to produce a canonical result bundle under `runs/` without requiring network access.
**Compare Acceptance (v0.1):** Compare is satisfied when `hpc-oda benchmark hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml` produces a deterministic, schema-valid result bundle containing regression metrics (at least MAE and RMSE) and provenance (schema versions, dataset identifier/hash, model identifier/version, environment capture, and code version when available).

---

## 2. Scope (v0.1)

### 2.1 Problem Domain (v0.1)
- **SLURM Job Runtime Prediction** (predicting job walltime / runtime duration based on job metadata and scheduler-observable information)

### 2.2 Primary Data Source (v0.1)
- **`slurmctld` logs** (and/or SLURM scheduler output sources strictly necessary to extract job lifecycle timestamps and requested resources)

> Note: v0.1 is deliberately constrained to the minimum set of log-derived fields required to support runtime prediction and benchmarking.

### 2.3 Target Audiences (v0.1)
- **Site Operators**
  - ingest local data
  - apply safe transformations (hashing/redaction/binning)
  - run the baseline model locally and inspect results
- **Researchers**
  - contribute benchmark recipes, models, and validation rules
  - reproduce results using result bundles and pinned recipes
- **Program Managers**
  - review the leaderboard and benchmark reports
  - understand the state of community baselines (read-only in v0.1)

---

## 3. Deliverables (v0.1)

### 3.1 User Workflow Deliverables (10-minute workflow)
v0.1 must support a first-run workflow that is achievable in ~10 minutes on a laptop or HPC login node:

1. Install package
2. Initialize a local project
3. Browse what’s available (offline registry snapshot)
4. Run an offline baseline on included tiny synthetic data
5. Point the system at local logs for ingestion
6. Validate ingested artifacts
7. Run the baseline model on local ingested data (optional in first 10 minutes, but should be straightforward)

### 3.2 Core Technical Deliverables
- **CLI supports the 10-minute workflow**
  - `hpc-oda init`
  - `hpc-oda browse`
  - `hpc-oda info`
  - `hpc-oda run-baseline`
  - `hpc-oda ingest slurmctld ...`
  - `hpc-oda validate ...`
  - `hpc-oda benchmark ...` (or equivalent compare command)
- **slurmctld ingestion → schema-valid Parquet + manifest**
  - Ingestion produces:
    - ODA Table (Parquet)
    - ODA Manifest (JSON) including schema version + provenance + transformations ledger
- **Benchmark runner executes `baseline_tiny` recipe**
  - Recipe defines:
    - dataset reference (tiny synthetic)
    - model reference (baseline)
    - required schema version(s)
    - metrics configuration
- **Result bundle schema + provenance**
  - Benchmark output is a canonical result bundle with:
    - `result.json`
    - `metrics.json`
    - `provenance.json` (schema versions, dataset hash, model ID/version, environment capture)
- **Minimal leaderboard generator (static)**
  - Reads result bundles and generates:
    - `leaderboard.json`
    - `index.html` (optional but recommended)
  - Hosting is optional for v0.1; generation must work locally.

---

## 4. Non-Goals (v0.1)

The following are explicitly **out of scope** for v0.1:

- Distributed benchmarking infrastructure / shared compute orchestration
- Complex dashboards (beyond optional minimal local HTML report output)
- LDMS/Darshan/XDMoD ingestion beyond placeholders/stubs (no full integrations in v0.1)
- “Intelligence layer” features:
  - learned mapping suggestions
  - knowledge graph
  - adaptive synthetic generator feedback loops
- Multi-site federated data sharing pipelines
- Production-grade privacy guarantees beyond:
  - local-first operation
  - explicit transformation policy and transformation ledger

---

## 5. Assumptions (v0.1)

- **Local-first processing:** no data uploads, telemetry, or external calls are required for v0.1 workflows.
- **Schema governance starts in v0.1, but evolution is later:**
  - Schema evolution will be handled via SER (Schema Evolution Requests) in future iterations.
  - Once the v0.1 schema is implemented and validated for the vertical slice, it is treated as **frozen** for the remainder of v0.1.

---

## 6. v0.1 Exit Criteria (Definition of Done Gates)

v0.1 is considered complete only when **all** the following gates pass:

- **DoD-1:** `pip install -e .` and `hpc-oda --help` works
- **DoD-2:** `hpc-oda run-baseline` produces a result bundle offline
- **DoD-3:** `hpc-oda ingest slurmctld …` produces schema-valid Parquet + manifest
- **DoD-4:** `hpc-oda benchmark hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml` produces comparable metrics + provenance

> Note: This charter updates the recipe path for runtime prediction to `hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml`.

---

## 7. Success Metrics (v0.1)

A successful v0.1 should demonstrate:

- A new user can complete the offline baseline workflow without reading source code.
- A site operator can ingest a representative slurmctld log snippet into schema-valid artifacts.
- A researcher can run a benchmark recipe and obtain a reproducible result bundle.
- The repository structure clearly supports contributions for adapters/models/recipes and future schema evolution.

---

## 8. Reference Links (to be updated)

- Quickstart: `docs/how-to/quickstart.md`
- CLI reference: `docs/reference/cli.md`
- Schema overview: `docs/concepts/schema.md`
- Benchmarks overview: `docs/concepts/benchmarks.md`
- Project Plan: `PROJECT_PLAN.md`
