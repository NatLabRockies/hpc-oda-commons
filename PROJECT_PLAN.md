# hpc-oda-commons: High-Level Development Process (v0.1 → v1)

This document outlines a step-by-step, high-level development process to build **hpc-oda-commons** as a modular, extensible open-source Python package and repository. The immediate goal is a **v0.1 vertical slice** that demonstrably supports the **Find, Compare, Run** pillars and the **10-minute workflow**.

---

## Guiding Principles

- **Vertical slice first (v0.1):** ship an end-to-end workflow for a single high-impact use case before expanding scope.
- **Contracts over concepts:** every pillar is represented by testable CLI workflows and versioned artifacts.
- **Local-first + safe by default:** operational logs are processed locally; sensitive data transformations are explicit and recorded.
- **Artifacts are the interface:** comparability and reproducibility rely on canonical schemas and result bundles, not implicit conventions.
- **Community-ready:** even as a solo developer, structure contributions, governance hooks, and templates from day one.

---

## v0.1 Scope (Vertical Slice)

**Problem domain:** SLURM Job Runtime Prediction  
**Primary source:** `slurmctld` logs  
**Dataset strategy:** Tiny synthetic dataset included (offline) + manifest  
**Model strategy:** Fast, deterministic baseline (e.g., logistic regression / small RF)  
**Benchmarking:** One primary recipe: `baseline_tiny`  
**Outputs:** Canonical Parquet + manifests + result bundles

---

## Non-Negotiable Contracts (Testable “Golden Paths”)

### Find
Given a problem tag and data source type, list compatible models/adapters/tools with sufficient metadata to decide quickly.

### Compare
Given models and dataset(s), execute the same benchmark recipe and produce comparable metrics and reproducible result bundles.

### Run
Given local logs, ingest → validate → run baseline → run chosen model in <10 minutes on a laptop/HPC login node.

---

## Definitions of Done (DoD Gates)

These gates anchor development and become CI “golden path” checks.

- **DoD-1:** `pip install -e .` and `hpc-oda --help` works.
- **DoD-2:** `hpc-oda run-baseline` works offline and produces a result bundle.
- **DoD-3:** `hpc-oda ingest slurmctld …` produces schema-valid Parquet + manifest.
- **DoD-4:** `hpc-oda benchmark recipes/job-runtime/baseline_tiny.yml` produces comparable metrics + provenance.

---

## Repo Hygiene (Solo Development Practices)

- Develop in small branches and merge often (even locally).
- For every change: run lint + tests locally before committing.
- Keep quickstart docs aligned with CLI behavior (minimum: README + quickstart page).

---

## Step-by-Step Development Process

### 0) Establish “Rules of the Road” (one-time setup)

1. Lock in v0.1 scope (as above).
2. Confirm and document the three pillar contracts (Find/Compare/Run).
3. Confirm DoD gates and convert them into CI checks.
4. Validate the repo scaffold and ensure packaging works end-to-end.

---

### 1) Build the “Commons Kernel” (minimal stable foundation)

**Goal:** create the smallest set of stable primitives everything else builds on.

1. Implement core artifact formats:
   - **ODA Table** (Parquet)
   - **ODA Manifest** (JSON)
   - **Result Bundle** (directory with canonical JSON files)
2. Implement schema loader + validator:
   - load versioned JSON Schemas from `schemas/`
   - validate manifests, results, and (where appropriate) data records
   - provide human-friendly errors
3. Implement provenance capture:
   - hash inputs (paths + optional content hash)
   - record schema versions, code version, and environment snapshot (minimal first)

**DoD:** artifacts can be read/written and validated; provenance records are produced.

---

### 2) Make “Find” real (registry snapshot + metadata)

**Goal:** offline discoverability that works without any server.

1. Define metadata models:
   - adapter metadata (source type, schema compatibility, tags)
   - model metadata (problem domain, I/O schema versions, dependencies)
   - recipe metadata (required schema, metrics, dataset requirements)
2. Implement registry snapshot loader:
   - read `registry/snapshot.json`
   - provide basic search/filter: by tag, schema version, source type
3. CLI: implement `hpc-oda browse` + `hpc-oda info`:
   - browse lists curated items
   - info shows compatibility + required artifacts

**DoD:** `hpc-oda browse --tag job-runtime-prediction` shows baseline model, slurmctld adapter, baseline recipe.

---

### 3) Make “Run” real (project init + offline baseline run)

**Goal:** immediate user value, no network required.

1. Implement project initialization:
   - `hpc-oda init` creates `hpc-oda.toml`, directories, and local state (`.hpc_oda/`)
2. Implement baseline runner path:
   - use included tiny synthetic dataset + manifest
   - run baseline model plugin
   - compute metrics
   - emit result bundle + concise terminal summary
3. CLI: implement `hpc-oda run-baseline`

**DoD:** fresh clone can `init` and `run-baseline` successfully offline.

---

### 4) Implement ingestion for v0.1 (slurmctld → oda.job.v0.1.0)

**Goal:** convert real logs into standardized artifacts locally, safely.

1. Finalize and freeze the v0.1 job schema:
   - keep lean: job IDs, timestamps, exit_code, derived label/reason, resources
2. Implement slurmctld adapter:
   - parser: extract required fields
   - mapping: normalize to schema
3. Integrate Safe Transformation Policy:
   - hash user IDs by default
   - timestamp binning option
   - redaction/denylist support
4. CLI: implement `hpc-oda ingest slurmctld --path …`:
   - outputs Parquet + manifest
   - writes into project directory

**DoD:** ingesting a fixture log produces schema-valid outputs.

---

### 5) Implement validation + data quality reporting

**Goal:** enforce comparability and increase trust for operators.

1. Schema validation:
   - required fields present
   - types correct
   - logical checks (e.g., start ≤ end)
2. Data quality checks (v0.1 minimal set):
   - missingness rates
   - timestamp consistency
   - label distribution sanity checks
3. CLI: implement `hpc-oda validate <path>`:
   - prints concise report
   - writes a JSON quality report artifact

**DoD:** validation catches common ingestion mistakes and produces a usable report.

---

### 6) Make “Compare” real (recipes → benchmark runner → metrics → bundles)

**Goal:** reproducible benchmarking producing leaderboard-ready artifacts.

1. Recipe format:
   - parse YAML/TOML into strict internal representation
   - validate required fields (schema version, model reference, dataset reference, metrics)
2. Benchmark runner:
   - load dataset artifact(s)
   - run model plugin
   - compute metrics (classification first)
   - emit result bundle with provenance
3. CLI: implement `hpc-oda benchmark <recipe.yml>`

**DoD:** baseline_tiny recipe produces repeatable result bundles.

---

### 7) Generate a static leaderboard (from result bundles)

**Goal:** a simple public “Compare” surface with minimal maintenance.

1. Collector:
   - scan result bundle directories
   - validate each bundle schema
   - aggregate into `leaderboard.json`
2. Static HTML generator:
   - minimal table view (filters later)
   - host via GitHub Pages if desired

**DoD:** a single command generates publishable leaderboard artifacts.

---

### 8) Testing strategy integrated into the build (don’t postpone)

Add tests aligned with DoD gates as each component lands.

- Unit tests:
  - schema loading/version parsing
  - recipe parsing + metric definition parsing
  - transformation policy behavior
  - metrics computations
- Integration tests (“golden paths”):
  - `run-baseline` end-to-end
  - slurmctld ingestion on fixture logs
  - benchmark smoke test on tiny synthetic recipe

**DoD:** CI runs unit + integration tests on every commit.

---

### 9) Documentation + packaging polish (usable by strangers)

1. Quickstart docs match CLI:
   - installation
   - 10-minute workflow
   - example outputs
2. Contribution docs:
   - add adapters/models/recipes
   - schema evolution (SER) process
3. Release v0.1.0:
   - tag + changelog
   - registry snapshot includes official items
   - baseline is offline and deterministic

**DoD:** a new user can succeed from docs without help.

---

## Recommended Build Order (fastest path to “working”)

1. Core artifacts + schema loader/validator + provenance
2. CLI skeleton + `run-baseline` (offline)
3. Registry snapshot + `browse` / `info`
4. slurmctld ingestion
5. Benchmark runner + recipe parsing + metrics
6. Leaderboard generator
7. Docs + packaging polish

---

## Post-v0.1 Expansion Loop (repeatable iteration cycle)

For each new domain/source:

1. Propose schema extension (SER)
2. Add adapter(s) + tests
3. Add baseline model(s) + recipes
4. Run benchmarks + publish updated leaderboard
5. Improve docs + examples
6. Cut a minor version release

---

## Next Step

Start coding with the smallest stable foundation:
- canonical artifacts (Parquet + manifest + result bundle)
- schema loader/validator
- minimal CLI entrypoint

Once these exist, everything else plugs into them cleanly.

---

## Next Steps (Post-Cleanup Optimization Plan)

This plan defines the **optimal development path** from the current repo state to a stable v0.1.0 release. Decisions below are intentional to maximize reliability in both **editable installs** and **packaged wheels**.

### Decision Summary (Explicit)

1. **Bundle recipes and tiny dataset in the wheel**  
   - Rationale: avoid "works in repo, breaks in wheel" failures.  
   - Action: place tiny synthetic dataset under `src/hpc_oda_commons/datasets/` and ensure recipe points there.

2. **Canonical schema loader lives in `kernel/schemas.py`**  
   - Rationale: core validation already uses kernel; keep a single surface and avoid drift.  
   - Action: remove unused `schema/loader.py` and `schema/ids.py` after refactoring any consumers.

3. **CLI is the public surface for v0.1**  
   - Rationale: keep API stability focused on CLI; Python API remains minimal/experimental.

4. **Add a single integration test for leaderboard**  
   - Rationale: protect the new CLI command and generated artifacts with low overhead.

### Step-by-Step Plan

#### 1) Packaging Consistency (Recipes + Datasets)
**Goal:** ensure a clean wheel install can run the entire quickstart.

- Move tiny dataset into package:
  - `src/hpc_oda_commons/datasets/synthetic/job-runtime/tiny/data.parquet`
  - `src/hpc_oda_commons/datasets/synthetic/job-runtime/tiny/manifest.json`
- Update recipe to point at packaged dataset path.
- Ensure `pyproject.toml` includes datasets in package-data.
- Verify registry snapshot references packaged recipe path.

**Acceptance:**
- `pip install -e .` (and wheel install) can run:
  - `hpc-oda run-baseline`
  - `hpc-oda benchmark hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml`

#### 2) Consolidate Schema APIs
**Goal:** one canonical schema loader/validator surface.

- Keep:
  - `src/hpc_oda_commons/kernel/schemas.py`
  - `src/hpc_oda_commons/kernel/validate.py`
- Retain `src/hpc_oda_commons/schema/validator.py` for quality checks, but remove:
  - `src/hpc_oda_commons/schema/loader.py`
  - `src/hpc_oda_commons/schema/ids.py`
  - `src/hpc_oda_commons/schema/migration.py` (if still unused)
- Update docs to reflect the canonical loader location.

**Acceptance:**
- All tests pass.
- No duplicate schema loaders remain.

#### 3) Residual Dead Code Cleanup
**Goal:** eliminate any remaining unused modules after consolidation.

- Re-run import/reference scan.
- Remove any unused files discovered.
- Update README tree if structure changes.

**Acceptance:**
- `pytest -q` passes.
- README tree matches actual repo.

#### 4) Leaderboard Integration Coverage
**Goal:** protect the new leaderboard CLI and artifacts.

- Add integration test that:
  1. Runs a benchmark
  2. Runs `hpc-oda leaderboard`
  3. Asserts `leaderboard.json` and `index.html` exist

**Acceptance:**
- `pytest -q -m integration` passes.

#### 5) Public Surface Stabilization
**Goal:** clarify v0.1 surface and reduce churn.

- Document in `docs/reference/python-api.md`:
  - CLI is stable for v0.1
  - Python APIs are minimal/experimental
- Ensure README quickstart is consistent with packaged paths.

**Acceptance:**
- Docs match actual CLI behavior.

#### 6) Release Readiness Pass
**Goal:** ensure v0.1.0 is shippable.

- Run quickstart in a fresh venv using installed wheel.
- Verify DoD gates:
  - DoD-1..DoD-4
- Update `CHANGELOG.md` with final date and summary.

**Acceptance:**
- `scripts/release_checklist.md` can be checked off.

### Test Strategy (for the plan above)

- Fast checks:
  - `pytest -q tests/unit`
- Full suite:
  - `pytest -q`
  - `HPC_ODA_OFFLINE=1 pytest -q -m integration`
- Packaging verification:
  - wheel install in a clean venv
  - run quickstart commands from docs
