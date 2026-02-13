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

---

## Continuation Plan (Authoritative Roadmap After Post-Cleanup Optimization)

This section defines the **next development phases** from the repo’s current state through **v0.1.0 “ship-quality”** and toward a **pillar-complete v1.0**.

### Scope Anchor (Clarification)

- The v0.x vertical slice remains: **SLURM Job Runtime Prediction** (not failure prediction).
- The **CLI** (`hpc-oda`) is the primary stable public surface in v0.1; Python APIs remain minimal/experimental.

### What “Done” Means

#### Completion A: v0.1.0 (Vertical Slice Done / Shippable)

1. A new user can install and complete the documented quickstart offline (where possible) and on a typical laptop/HPC login node.
2. Artifacts (Parquet + manifest + result bundles) are schema-valid, comparable, and provenance-complete.
3. Registry snapshot is usable offline and references packaged recipes/datasets correctly.
4. CI enforces “golden path” DoD gates (below).

#### Completion B: v1.0 (Platform Done / Extensible)

1. ODARSEA: stable schema evolution process + first-class adapter/model contracts + safe transformation policy.
2. ODABLV: strict recipe + metric definitions, environment lock records, reproducibility-ready leaderboard entries.
3. ODA-QST: guided workflows (analyze-my-data) and a lightweight dashboard/reporting path.
4. “Intelligence layer” exists in a pragmatic, minimal form (assistive heuristics + metadata graph), not an ML platform.

---

## Phase 1: Release Engineering and CI DoD Gates (v0.1.0 Hardening)

**Goal:** make installs and the 10-minute workflow boringly reliable; ensure CI protects it.

### Work Items

1. Packaging verification:
   - Build wheel/sdist locally.
   - Install wheel into a clean venv and re-run the CLI golden paths.
2. Offline install story:
   - Document supported offline modes:
     - pre-built wheelhouse (recommended for HPC)
     - internal index / mirror
     - container image (Docker/Apptainer)
   - Document what is *not* guaranteed offline (e.g., build isolation when build deps must be fetched).
3. CI DoD gates:
   - Add/ensure CI runs:
     - lint/format
     - unit tests
     - integration tests with `HPC_ODA_OFFLINE=1`
   - Ensure the integration “golden path” mirrors docs (init → run-baseline → ingest → validate → benchmark → leaderboard).
4. Release checklist alignment:
   - Ensure `scripts/release_checklist.md` matches exact commands that succeed.

### Likely Files

- `pyproject.toml`
- `scripts/release_checklist.md`
- `docs/how-to/install.md`
- `docs/how-to/quickstart.md`
- `.github/workflows/*` (if CI is in-repo)

### Acceptance

- Wheel install + CLI quickstart commands succeed.
- CI fails fast if any DoD gate regresses.

---

## Phase 2: ODARSEA Hardening (Schema + Adapters + Safe Transformations)

**Goal:** strengthen semantic interoperability without expanding scope.

### Work Items

1. SER (Schema Evolution Request) process:
   - Add a lightweight SER template and rules for semver + deprecation.
2. Adapter contract:
   - Define a minimal adapter protocol/base class with required metadata and supported schema versions.
   - Ensure slurmctld adapter conforms to contract.
3. Safe transformation policy:
   - Promote explicit, stable transformation helpers (hashing, timestamp binning, redaction hooks).
   - Record transformations in manifests/provenance.
4. Data quality standards:
   - Make quality rules configurable and versioned (baseline rules for v0.1, extensible for v0.2).

### Likely Files

- `src/hpc_oda_commons/kernel/*`
- `src/hpc_oda_commons/schema/*`
- `src/hpc_oda_commons/adapters/*`
- `docs/concepts/schema.md`
- `docs/concepts/security-data-handling.md`

### Acceptance

- No schema duplication; all validation uses canonical kernel loading.
- Ingest always produces schema-valid outputs and a quality report.
- Transformations are explicit and reproducible (recorded).

---

## Phase 3: ODABLV Expansion (Recipes + MDL + Provenance + Reproducibility)

**Goal:** make “Compare” defensible and repeatable beyond a single baseline.

### Work Items

1. Recipe schema + validation:
   - Define and enforce a strict recipe schema (and validate in CI).
2. Metric Definition Language (MDL) v0:
   - Start small: strict schema for metric declarations with deterministic computation.
   - Record metric config in result bundles verbatim.
3. Environment locking:
   - Support a minimal “environment descriptor” per recipe (constraints file, conda env, or container reference).
   - Record environment hash and tool versions into provenance.
4. Leaderboard reproducibility links:
   - Ensure leaderboard entries point to bundles with complete provenance (recipe, schema versions, inputs, env descriptor).

### Likely Files

- `src/hpc_oda_commons/benchmark/*`
- `src/hpc_oda_commons/kernel/provenance.py`
- `recipes/*`
- `scripts/validate_recipes.py`
- `docs/reference/recipes.md`
- `docs/concepts/benchmarks.md`

### Acceptance

- Recipes can be validated mechanically before execution.
- Result bundles are sufficient to reproduce metrics.
- Leaderboard generation is stable and schema-backed.

---

## Phase 4: ODA-QST UX Upgrade (Guided Workflows)

**Goal:** improve operator usability without forcing a heavy UI framework too early.

### Work Items

1. “Intelligent ingest” v0 (pragmatic):
   - Add deterministic checks/suggestions for the slurmctld ingest path (required fields present, timestamp parsing, missingness).
   - Defer an interactive wizard until there is real demand.
2. `analyze-my-data` command:
   - Select a model + input dataset artifact and run inference/evaluation, emitting a report bundle.
3. Dashboard/reporting:
   - Prefer a static HTML report artifact first (build on existing HTML generation).
   - Add Streamlit/Dash only as an optional extra once report contracts stabilize.

### Likely Files

- `src/hpc_oda_commons/qst/cli.py`
- `src/hpc_oda_commons/tools/report/*`
- `docs/reference/cli.md`
- `docs/how-to/quickstart.md`

### Acceptance

- Users can run “ingest → validate → analyze” with clear outputs and a shareable report bundle.

---

## Phase 5: “Intelligence Layer” (Minimal, Practical Form)

**Goal:** add assistive features without committing to a large ML/infra system.

### Work Items

1. Mapping suggestion library:
   - Create a small library of reusable parsing/mapping hints learned from in-tree adapters.
2. Synthetic generator feedback loop:
   - Add a harness that scores synthetic datasets on realism/coverage proxies and stores summary metrics.
3. Metadata graph:
   - Generate a static graph derived from registry metadata (tags, schema versions, domains, metrics).
   - Use it to power better “Find” queries and docs.

### Acceptance

- “Assist” features are deterministic and testable.
- No new infra dependencies required.

---

## Phase 6: Expand Breadth (Still Runtime First; Defer Failure Domain)

**Goal:** expand only after contracts are stable and CI gates are solid.

### Work Items

1. Add 1–2 additional **runtime** datasets (prefer external pointers + manifests).
2. Add at least one additional **runtime** model (simple but distinct).
3. Add another ingestion source (or a second SLURM format) only after adapter contracts stabilize.
4. Introduce **failure prediction** as a new domain only after runtime is boringly reliable.

### Acceptance

- New datasets/models/adapters land with:
  - schema and metadata
  - unit tests
  - integration coverage for user workflows
  - docs updates

---

## Tests and Verification (Ongoing)

For any change that touches user workflows:

- Fast: `pytest -q tests/unit`
- Full: `pytest -q`
- Offline integration: `HPC_ODA_OFFLINE=1 pytest -q -m integration`
- CLI smoke (manual/release): run quickstart commands in a clean venv (wheel install preferred).

---

## Additional Testing Plan (CI Hardening / Coverage Gaps)

This section captures a focused test expansion plan to reduce regression risk and
catch packaging drift early. It is intentionally **prioritized** and biased
toward “contract tests” that protect the v0.1 CLI golden paths.

### Under-Tested Areas (Current Gaps)

1. **Packaged non-code artifacts**
   - Risk: `.gitignore` and packaging drift can silently remove runtime-required assets (schemas, recipes, registry snapshot, tiny datasets).
2. **CLI workflow coverage gaps**
   - Integration covers DoD-1..DoD-4 and leaderboard generation, but does not currently assert:
     - `hpc-oda validate` behavior (including writing `*.quality.json`)
     - `hpc-oda analyze` behavior (analysis bundle + HTML)
     - CLI subprocess wiring for `browse` / `info`
3. **slurmctld parsing edge cases**
   - Parsing is minimally tested (smoke), but not locked down for multi-job interleaving, incomplete jobs, or exact runtime computation.
4. **Baseline model behavior**
   - Baseline model has no direct unit tests for determinism and error behavior (`predict` before `fit`).
5. **Semantic validation failure modes**
   - Happy path quality report is covered, but failure behavior is not (negative runtime, start > end, invalid timestamps).
6. **Leaderboard robustness**
   - Leaderboard intentionally skips invalid bundles; behavior and sorting are not explicitly tested.
7. **Registry snapshot validation**
   - We do not assert the packaged snapshot validates against `oda.registry.v0.1.0`.
8. **Scripts/CI validations**
   - `scripts/validate_recipes.py` exists but is not enforced in CI; `scripts/validate_schemas.py` is a stub.

---

## Test Development Plan (Prioritized)

### P0 — Packaging and Golden Path Contracts

1. Packaged assets contract test
   - Add `tests/unit/test_packaged_assets.py` asserting required packaged assets exist:
     - `oda.*` schemas (job/result/registry/recipe/mdl)
     - `registry/snapshot.json`
     - `recipes/job-runtime/baseline_tiny.yml`
     - `datasets/synthetic/job-runtime/tiny/manifest.json`
     - `datasets/synthetic/job-runtime/tiny/data.parquet` (if we keep “bundled tiny dataset” as a hard contract)
   - Verification:
     - `pytest -q tests/unit`
   - Follow-on (if needed): update `.gitignore` to allow the specific tiny parquet under `src/` and ensure it is tracked.

2. Expand integration golden path coverage: `validate` + `analyze`
   - Extend `tests/integration/test_cli_golden_path.py` (or add a new file) to assert:
     - `hpc-oda validate <parquet>` writes `*.quality.json`
     - `hpc-oda analyze --data <ingest_dir>` writes:
       - `reports/analysis-*/analysis.json`
       - `reports/analysis-*/index.html`
   - Verification:
     - `HPC_ODA_OFFLINE=1 pytest -q -m integration`

### P1 — Correctness Lock-Down for Core Components

3. slurmctld parser correctness tests
   - Add `tests/unit/test_slurmctld_parser.py`:
     - single job allocate+done → exact `runtime_seconds`
     - multiple interleaved jobs → correct per-job outputs
     - incomplete job behavior is explicit (skip or emit nulls) and tested
   - Verification:
     - `pytest -q tests/unit`

4. Baseline model unit tests
   - Add `tests/unit/test_job_runtime_baseline_model.py`:
     - `predict()` before `fit()` raises
     - `fit()` ignores null runtimes and computes mean correctly
     - predictions are constant/deterministic
   - Verification:
     - `pytest -q tests/unit`

5. Validation failure-mode tests
   - Extend `tests/unit/test_validator.py`:
     - negative runtime triggers `SchemaValidationError`
     - `start_time > end_time` triggers `SchemaValidationError`
     - invalid timestamp format triggers `SchemaValidationError`
   - Verification:
     - `pytest -q tests/unit`

### P2 — Robustness and CI Guardrails

6. Leaderboard robustness tests
   - Extend `tests/unit/test_leaderboard.py`:
     - one valid + one invalid bundle → leaderboard includes only valid entries
     - ordering by `created_at` is stable
   - Verification:
     - `pytest -q tests/unit`

7. Registry snapshot validation test
   - Add `tests/unit/test_registry_validate.py`:
     - `validate_registry_snapshot(snapshot_resource_path())` succeeds
   - Verification:
     - `pytest -q tests/unit`

8. CI script enforcement
   - Add CI steps to run:
     - `python scripts/validate_recipes.py`
   - Either:
     - implement `scripts/validate_schemas.py` minimally (load all packaged schema JSON and validate they are JSON objects), and run it in CI
     - or remove the stub until implemented

### P3 — Test Hygiene

9. Reduce fixture fragility
   - Add helper(s) in `tests/conftest.py` to generate slurmctld logs for tests (avoid `.gitignore` surprises).
   - Fill in `tests/README.md` with:
     - unit vs integration definitions
     - “no gitignored fixtures” rule
     - recommended commands

---

## Repo Cleanup Plan (Post-v0.1 Hardening)

This section captures a **repo cleanup plan** to remove scaffold leftovers, reduce confusion,
and ensure docs/scripts/packaging match the current v0.1 runtime-prediction vertical slice.

### Key Cleanup Findings

1. **Placeholder docs/READMEs** remain in multiple places (`<!-- ... -->` stubs).
2. **Stub Python modules** exist (docstring-only) and are not imported/used.
3. **Placeholder “fake data” artifacts** exist (text files with `.parquet`, placeholder signatures).
4. **Scripts are partially non-runnable** as written (paths rely on gitignored fixtures).
5. **Packaging correctness risks**:
   - runtime import of `jsonschema` is not declared under `[project].dependencies`
   - `MANIFEST.in` includes root-level paths that don’t exist and may omit `src/hpc_oda_commons/...` assets from sdist
6. **Repo naming collisions/confusion**:
   - top-level `leaderboard/` contains old scaffold templates and ignored generated files; CLI also outputs to `leaderboard/` by default.

---

## Cleanup Checklist (File-Level Operations)

### 1) Remove/Replace Placeholder Artifacts (High ROI / Low Risk)

- Delete placeholder “fake parquet” fixtures:
  - Delete `tests/fixtures/expected_job_table.parquet` (not a real parquet file)
  - Delete `tests/fixtures/expected_manifest.json` (placeholder-only)
- Remove unused failure-prediction synthetic dataset scaffolding:
  - Delete `datasets/synthetic/job-failure/`
  - Delete `datasets/synthetic/shared/schema_examples.jsonl`
- Remove placeholder registry signature:
  - Delete `registry/snapshot.sig`
- Optional: remove ignored generated leftovers in working trees (not committed):
  - remove local `leaderboard/public/index.html`, `leaderboard/public/leaderboard.json` if present

**Verify:** `ruff check .`, `ruff format .`, `pytest -q tests/unit`, `HPC_ODA_OFFLINE=1 pytest -q -m integration`

---

### 2) Remove Dead Stub Python Modules (Reduce Surface Area)

Delete unused docstring-only modules that are not imported and provide no behavior:

- slurmctld adapter stubs:
  - Delete `src/hpc_oda_commons/adapters/slurmctld/parser.py`
  - Delete `src/hpc_oda_commons/adapters/slurmctld/mapping.py`
  - Delete `src/hpc_oda_commons/adapters/slurmctld/labeling.py`
  - Delete `src/hpc_oda_commons/adapters/slurmctld/fixtures.py`
- baseline model stubs (classification leftovers):
  - Delete `src/hpc_oda_commons/models/job_runtime_baseline/features.py`
  - Delete `src/hpc_oda_commons/models/job_runtime_baseline/calibrate.py`
  - Delete `src/hpc_oda_commons/models/job_runtime_baseline/explain.py`
- QST scaffolding not used:
  - Delete `src/hpc_oda_commons/qst/config.py`
  - Delete `src/hpc_oda_commons/qst/project.py`
  - Delete `src/hpc_oda_commons/qst/tui/render.py`
- utils stubs not used:
  - Delete `src/hpc_oda_commons/utils/io.py`
  - Delete `src/hpc_oda_commons/utils/logging.py`
  - Delete `src/hpc_oda_commons/utils/time.py`
- version module decision:
  - Either implement `src/hpc_oda_commons/version.py` (recommended: expose `__version__` via `importlib.metadata`)
  - Or delete it and keep version capture only in `kernel/provenance.py`

**Verify:** `ruff check .`, `ruff format .`, `pytest -q tests/unit`, `HPC_ODA_OFFLINE=1 pytest -q -m integration`

---

### 3) Packaging and Install Correctness (Must-Have)

- Add missing runtime dependency:
  - Update `pyproject.toml` `[project].dependencies` to include `jsonschema>=4`
- Fix sdist packaging:
  - Update `MANIFEST.in` to include packaged assets under `src/hpc_oda_commons/...`:
    - `src/hpc_oda_commons/schemas/**/*.json`
    - `src/hpc_oda_commons/registry/*.json`
    - `src/hpc_oda_commons/recipes/**/*.{yml,yaml,toml}`
    - `src/hpc_oda_commons/datasets/**/*`
  - Keep docs inclusion in sdist only if intentional (`recursive-include docs *`)
- Ensure the tiny runtime parquet is actually committed:
  - Confirm `src/hpc_oda_commons/datasets/synthetic/job-runtime/tiny/data.parquet` is tracked

**Verify:**
- `pytest -q tests/unit`
- `HPC_ODA_OFFLINE=1 pytest -q -m integration`
- optional build verification:
  - `python -m pip wheel -w dist .` then install wheel in a clean venv and run `hpc-oda --help`

---

### 4) Scripts Cleanup (Make Real or Remove)

- Fix `scripts/golden_path_local.sh`:
  - determine repo root from the script location
  - generate a tiny slurmctld log in the temp project (avoid relying on `tests/fixtures/slurmctld.log`)
  - use a real recipe path (`recipes/job-runtime/baseline_tiny.yml` or packaged copy under `src/`)
  - include `hpc-oda validate ...` and `hpc-oda analyze ...` to mirror docs
- Handle stub scripts (choose one path per script):
  - implement `scripts/validate_schemas.py` minimally (load all schema JSON files and ensure valid JSON objects; optionally validate `$id` presence)
  - implement `scripts/build_registry_snapshot.py` as a “sync + validate” utility (validate `registry/snapshot.json` and copy into `src/hpc_oda_commons/registry/snapshot.json`)
  - implement or remove `scripts/dev_bootstrap.sh` (currently placeholder)

**Verify:** `python scripts/validate_recipes.py`, `python scripts/validate_schemas.py` (if implemented), plus test suite.

---

### 5) Docs/README Cleanup (Remove Scaffold Smell)

- Update quickstarts consistently:
  - Update `README.md` to include the `hpc-oda analyze --data ...` step
  - Update `docs/index.md` 10-minute workflow to include analyze
- Replace placeholder docs with minimal accurate content:
  - Fill `docs/concepts/pillars.md` (map Find/Compare/Run to actual CLI commands + modules)
  - Fill `docs/concepts/artifacts.md` (ODA table, manifest, result bundle, quality report, analysis report)
  - Fill `docs/how-to/add-model.md` (what “adding a model” means in v0.1 and how to test it)
  - Fill repo READMEs: `datasets/README.md`, `recipes/README.md`, `registry/README.md`, `containers/README.md`, `examples/README.md`, `examples/projects/sample_project/README.md`
  - Fill/rename baseline model README:
    - Update `src/hpc_oda_commons/models/job_runtime_baseline/README.md` (currently titled “Job Failure Baseline Model”)
  - Fill adapter README:
    - Update `src/hpc_oda_commons/adapters/slurmctld/README.md` with supported formats, limitations, and examples
- Remove stale references to gitignored fixtures:
  - scrub references to `tests/fixtures/slurmctld.log` in docs/checklists/scripts (prefer generated sample logs or inline snippets)

**Verify:** `ruff check .`, `ruff format .`, `pytest -q`, `HPC_ODA_OFFLINE=1 pytest -q -m integration`

---

### 6) Optional CI Guardrails

- Add CI step for schema sanity checks if/when `scripts/validate_schemas.py` is implemented.
- Decide what to do with disabled workflows (`.github/workflows/*.disabled`):
  - keep as templates but update to current commands
  - or remove redundant ones to reduce noise (CI already covers golden paths)

---

## Proposed Commit Order (PR Shape)

1. Remove placeholder artifacts (fake parquet, placeholder signatures, unused failure dataset scaffolding).
2. Remove dead stub Python modules; decide fate of `version.py`.
3. Packaging fixes (`jsonschema` dependency, `MANIFEST.in` for `src/` packaged assets, ensure tiny parquet tracked).
4. Scripts cleanup (fix golden path script; implement/remove stub scripts).
5. Docs/README cleanup (fill placeholders, fix stale references).
6. Optional CI guardrails (schema sanity check; workflow template decisions).

## Verification Strategy (for cleanup PR)

- After each commit:
  - `ruff check .`
  - `ruff format .`
  - `pytest -q tests/unit`
- At the end:
  - `pytest -q`
  - `HPC_ODA_OFFLINE=1 pytest -q -m integration`
  - `python scripts/validate_recipes.py`
  - `python scripts/validate_schemas.py` (if implemented)

---

## Next Feature Plan: Jobs Parquet Ingestion Wizard (DB Export → ODA Job Table)

This plan addresses a common HPC ODA reality: researchers often cannot access `slurmctld` logs or `sacct`
exports directly, but can query an internal database and export a **jobs table** as Parquet.

### Goal

Add a new ingestion helper that:
- inspects a jobs Parquet file (columns + dtypes + a small sample),
- proposes best-effort mappings to the **v0.1 runtime prediction slice** fields,
- runs an **interactive confirmation** workflow (including units and timestamp formats),
- writes a reusable **mapping spec** + schema-valid ODA artifacts (Parquet + manifest).

### Scope (First Pass)

Assumptions for the first pass (per expected DB export shape):
- the jobs table includes `start_time`, `end_time`, and `submit_time` (or equivalents)
- the jobs table includes `state` (e.g., `PENDING`, `RUNNING`, `COMPLETED`, `TIMEOUT`, `FAILED`)
- the jobs table includes (or can derive) `runtime_seconds`

Fields to detect and map in v0.1 (minimum useful set):
- Required ODA fields: `job_id`, `start_time`, `end_time`, `runtime_seconds`
- Additional v0.1 fields to include for this first pass: `submit_time`, `state`
- Categorical features (if present): `user`, `account`, `partition`, `qos`
- Numeric features (if present): wallclock requested, nodes requested, memory requested, processors requested, gpus requested
  - Note: “wallclock used” is treated as `runtime_seconds` and not a separate canonical field.

### Design Decisions

1. New CLI command (under `ingest`)
- `hpc-oda ingest jobs-parquet --path <jobs.parquet>`
- Default mode is interactive (wizard).
- A non-interactive mode reuses an existing mapping spec:
  - `hpc-oda ingest jobs-parquet --path <jobs.parquet> --mapping mapping.yml`

2. Mapping spec is a first-class artifact
- Store mapping as a versioned artifact: `oda.mapping.v0.1.0`.
- Format: YAML (human-editable, easy to review in diffs).
- The mapping spec records:
  - input column selections
  - timestamp parsing expectations (ISO vs epoch seconds/ms/us)
  - unit conversions (durations, memory)
  - safe transformations (hash/redact identifiers)
  - derivations (e.g., runtime from start/end)

3. Schema-valid outputs by default
- The command writes a schema-valid `oda.job.v0.1.0` Parquet + manifest.
- Rows missing required fields are skipped by default (mirrors `slurmctld` adapter behavior).
- The command prints counts (kept vs skipped) and records them in the manifest notes/provenance.

4. Safe-by-default identifiers
- The wizard defaults to hashing `user` and `account` using `kernel.transformations.hash_identifier`.
- The mapping spec must record transformations; avoid embedding secrets (prefer env var name for salts).

### Step-by-Step Implementation Plan (Small Increments)

#### Increment 0: Mapping Spec Artifact (Foundation)

WIP already present in working tree (expected to be committed as the first increment):
- `src/hpc_oda_commons/schemas/oda/mapping/v0.1.0.json`
- `src/hpc_oda_commons/kernel/artifacts/mapping_spec.py`
- `tests/unit/test_mapping_spec_artifact.py`

Tasks:
- Ensure `oda.mapping.v0.1.0` loads through the canonical schema loader (`kernel.schemas`).
- Add `oda.mapping.v0.1.0` to `tests/unit/test_packaged_assets.py` so packaging contracts cover it.

Verify:
- `pytest -q tests/unit`

#### Increment 1: Parquet Inspection + Column Profiling (Non-interactive Core)

Add a reusable library that profiles a Parquet file:
- column names and normalized aliases
- Arrow dtypes (string, integer, float, timestamp)
- sample non-null values (small N)
- null rate (estimate or from Arrow statistics if available cheaply)

Proposed new files:
- `src/hpc_oda_commons/ingest/jobs_parquet/profile.py`
- `tests/unit/test_jobs_parquet_profile.py`

Verify:
- `pytest -q tests/unit`

#### Increment 2: Deterministic Mapping Suggestions (Explainable Heuristics)

Implement a suggestion engine that ranks candidate columns for:
- Required fields: `job_id`, `start_time`, `end_time`, `submit_time`, `state`, `runtime_seconds`
- Categorical: `user`, `account`, `partition`, `qos`
- Numeric: wallclock requested, nodes requested, memory requested, processors requested, gpus requested
  - “wallclock used” should map to `runtime_seconds` and not a separate field.

Heuristic signals (v0.1):
- column-name patterns and common aliases (case-insensitive, snake/camel tolerant)
- dtype compatibility (timestamp-like vs numeric vs string)
- value-shape checks for durations (e.g., `HH:MM:SS`, minutes, seconds)
- value-shape checks for GPU request encodings (e.g., `gpu:2` in a `gres`-like string)

Proposed new files:
- `src/hpc_oda_commons/ingest/jobs_parquet/suggest.py`
- `tests/unit/test_jobs_parquet_suggest.py`

Verify:
- `pytest -q tests/unit`

#### Increment 3: Interactive Wizard (Confirm Mappings + Units + Transformations)

Add an interactive wizard (Typer prompts) that:
- shows suggestions per canonical field and asks the user to confirm or choose a different column
- asks unit questions only when needed:
  - timestamps: ISO vs epoch seconds/ms/us
  - durations: seconds/minutes/hours or `HH:MM:SS`
  - memory: bytes/KB/MB/GB/MiB/GiB and whether memory is per-node vs total
- asks safe-transform questions (defaults):
  - hash `user` and `account` (default yes)
  - optional redaction for sensitive free-form columns
- writes `mapping.yml` and validates it against `oda.mapping.v0.1.0`

Proposed new files:
- `src/hpc_oda_commons/ingest/jobs_parquet/wizard.py`
- `tests/unit/test_jobs_parquet_units.py` (unit conversion logic, non-interactive)

Verify:
- `pytest -q tests/unit`

#### Increment 4: Apply Mapping Spec (Produce Canonical ODA Artifacts)

Implement the execution engine that applies a mapping spec to an input Parquet:
- reads in batches (avoid loading huge datasets in memory)
- renames/selects columns
- applies conversions (timestamps to ISO-8601 `Z`, durations to seconds, memory to bytes or MB)
- applies safe transforms (hash/redact)
- derives `runtime_seconds` if missing (from `start_time` and `end_time`)
- filters/skips rows missing required fields by default
- writes:
  - `data/ingested/jobs_parquet/<run_id>/data.parquet`
  - `data/ingested/jobs_parquet/<run_id>/manifest.json`
  - `data/ingested/jobs_parquet/<run_id>/mapping.yml`

Proposed new files:
- `src/hpc_oda_commons/ingest/jobs_parquet/apply.py`
- `tests/unit/test_jobs_parquet_apply.py`

Verify:
- `pytest -q tests/unit`

#### Increment 5: CLI Wiring (`hpc-oda ingest jobs-parquet`)

Wire the command into the CLI:
- `hpc-oda ingest jobs-parquet --path ...` runs wizard + apply
- `--mapping mapping.yml` skips wizard
- expose basic knobs:
  - `--sample-rows`
  - `--batch-size`
  - `--non-interactive` (fail if required mapping cannot be inferred or provided)
  - `--hash-identifiers/--no-hash-identifiers`

Files to change:
- `src/hpc_oda_commons/qst/cli.py`

Integration test:
- Extend `tests/integration/test_cli_golden_path.py`:
  - generate a tiny Parquet on the fly
  - run `hpc-oda ingest jobs-parquet ...`
  - run `hpc-oda validate` on the output Parquet and manifest

Verify:
- `pytest -q tests/unit`
- `pytest -q`
- `HPC_ODA_OFFLINE=1 pytest -q -m integration`

#### Increment 6: Docs + Registry (Discoverability)

Docs:
- Add `docs/how-to/ingest-jobs-parquet.md`
- Update `docs/how-to/quickstart.md` to mention the DB-export ingestion path as an alternative to `slurmctld`

Registry (optional but consistent with “Find”):
- Add an entry in `registry/snapshot.json` describing the new ingest helper.

Verify:
- `pytest -q`
- `HPC_ODA_OFFLINE=1 pytest -q -m integration`

### File-Level Change Checklist (Expected)

- New:
  - `src/hpc_oda_commons/ingest/jobs_parquet/profile.py`
  - `src/hpc_oda_commons/ingest/jobs_parquet/suggest.py`
  - `src/hpc_oda_commons/ingest/jobs_parquet/wizard.py`
  - `src/hpc_oda_commons/ingest/jobs_parquet/apply.py`
  - `src/hpc_oda_commons/kernel/artifacts/mapping_spec.py`
  - `src/hpc_oda_commons/schemas/oda/mapping/v0.1.0.json`
  - `tests/unit/test_jobs_parquet_*.py`
  - `tests/unit/test_mapping_spec_artifact.py`
  - `docs/how-to/ingest-jobs-parquet.md`

- Update:
  - `src/hpc_oda_commons/qst/cli.py`
  - `tests/integration/test_cli_golden_path.py`
  - `tests/unit/test_packaged_assets.py`
  - `registry/snapshot.json` (optional)

### Test Strategy (While Implementing)

- After each increment:
  - `pytest -q tests/unit`
- When CLI wiring lands:
  - `pytest -q`
  - `HPC_ODA_OFFLINE=1 pytest -q -m integration`

### Acceptance Criteria

- Given a DB-export Parquet jobs table, a user can run:
  - `hpc-oda ingest jobs-parquet --path jobs.parquet`
  - and obtain schema-valid `oda.job.v0.1.0` Parquet + manifest under `data/ingested/...`
- The wizard produces a reusable `mapping.yml` and re-running with `--mapping` is deterministic.
- The output includes `submit_time` and `state` when available (and records any skipping/filtering).
- CI remains green (`ruff` + unit + integration).

---

## Next Feature Plan: XGBoost Runtime Model Alternate (Hourly Rolling Evaluation)

### Requested Phase
This work maps to `PROJECT_PLAN.md` Phase 6 (“add another runtime model”) with Phase 3 implications (recipe/benchmark reproducibility).

### Scope and Assumptions
1. Add a new alternate runtime model based on `XGBoost` regression.
2. Implement automatic categorical preprocessing:
   one-hot encoding + PCA-equivalent dimensionality reduction on encoded categorical space.
3. Implement rolling hourly evaluation:
   for each split hour, train on jobs with `end_time < split_time`, test on jobs with `submit_time` in `[split_time, split_time + 1h)`.
4. Default window count is `n_recent_hours=1000`, configurable in recipe split settings.
5. Refit one-hot/PCA only at midnight boundaries; retrain XGBoost every hour.
6. Keep current baseline model and behavior unchanged.
7. Integrate as the first alternate model via registry + recipe.
8. Use `TruncatedSVD` for sparse one-hot PCA behavior (same objective: variance coverage with much lower memory cost).

### Implementation Plan (Incremental)
1. **Dependencies + model scaffold**
   - Add `xgboost` and `scikit-learn` dependencies.
   - Create new model package under `src/hpc_oda_commons/models/` for XGBoost runtime model.
   - Add README for model behavior and constraints.

2. **Automatic preprocessing analysis module**
   - Implement feature profiling for categorical columns (cardinality, sparsity, frequency distribution).
   - Implement automatic one-hot config selection (including infrequent-category handling).
   - Implement automatic PCA coverage selection (target explained variance; choose smallest component count meeting threshold).
   - Persist/emit preprocessing diagnostics for reproducibility.

3. **Rolling split engine + daily preprocessor refresh**
   - Implement hourly split generator for last `n_recent_hours`.
   - Implement day-keyed cache so one-hot/SVD fit is recomputed only once per day (at first split for that day).
   - Implement strict filtering semantics for train/test rows using `end_time` and `submit_time`.

4. **XGBoost hourly train/eval loop**
   - Train one XGBoost model per split hour.
   - Aggregate predictions/targets across hours and compute global `mae`/`rmse` for result schema compatibility.
   - Store per-hour metrics/details in `metrics.json`.

5. **Benchmark integration**
   - Add model resolution in benchmark path (current code is baseline-hardcoded).
   - Extend recipe split handling to support `rolling_hourly` + `n_recent_hours`.
   - Keep existing `fixed` split fully backward-compatible.

6. **Registry + recipe assets**
   - Add new registry entry for the XGBoost model as first alternate.
   - Add new recipe for the hourly XGBoost run (and packaged copy under `src/.../recipes/...`).
   - Run `python scripts/build_registry_snapshot.py` because registry changes.

7. **Dataset compatibility**
   - Ensure benchmarkable dataset has `submit_time`.
   - Update/regenerate tiny synthetic packaged dataset (and manifest notes) if needed.

8. **Tests**
   - Unit tests for:
     - preprocessing analysis and auto component selection
     - hourly split semantics
     - daily refresh behavior (refit only on day change)
     - model determinism and fit/predict behavior
     - recipe validation for new split method
   - Integration test:
     - benchmark with XGBoost recipe (small `n_recent_hours` for CI speed).
   - Update packaged-assets and registry tests for new model/recipe assets.

9. **Docs**
   - Update model/recipe reference docs and add short how-to for alternate model benchmarking.
   - No CLI command changes expected; if any CLI surface changes occur, also update `README.md`, `docs/how-to/quickstart.md`, and `docs/reference/cli.md` per repo rule.

### Planned File Changes
1. `pyproject.toml`
2. `src/hpc_oda_commons/models/job_runtime_xgboost/__init__.py` (new)
3. `src/hpc_oda_commons/models/job_runtime_xgboost/model.py` (new)
4. `src/hpc_oda_commons/models/job_runtime_xgboost/README.md` (new)
5. `src/hpc_oda_commons/qst/cli.py`
6. `src/hpc_oda_commons/benchmark/recipes.py`
7. `src/hpc_oda_commons/schemas/oda/recipe/v0.1.0.json`
8. `recipes/job-runtime/xgb_hourly_recent.yml` (new)
9. `src/hpc_oda_commons/recipes/job-runtime/xgb_hourly_recent.yml` (new)
10. `recipes/job-runtime/alt_model_example.yml`
11. `registry/snapshot.json`
12. `src/hpc_oda_commons/registry/snapshot.json` (via sync script)
13. `src/hpc_oda_commons/datasets/synthetic/job-runtime/tiny/data.parquet` (if submit_time missing)
14. `src/hpc_oda_commons/datasets/synthetic/job-runtime/tiny/manifest.json` (if dataset updated)
15. `tests/unit/test_job_runtime_xgboost_model.py` (new)
16. `tests/unit/test_job_runtime_xgboost_preprocessing.py` (new)
17. `tests/unit/test_job_runtime_xgboost_hourly_split.py` (new)
18. `tests/unit/test_recipe_validation.py`
19. `tests/unit/test_registry.py`
20. `tests/unit/test_packaged_assets.py`
21. `tests/integration/test_cli_golden_path.py`
22. `docs/reference/recipes.md`
23. `docs/how-to/add-model.md` (and related model docs as needed)

### Verification Plan
1. After each increment:
   - `./.venv/bin/ruff check .`
   - `./.venv/bin/ruff format . --check`
   - `./.venv/bin/pytest -q tests/unit`
   - If formatting fails: `./.venv/bin/ruff format .` then re-check.
2. When feature is complete:
   - `./.venv/bin/pytest -q`
   - `HPC_ODA_OFFLINE=1 ./.venv/bin/pytest -q -m integration`
3. Extra validation when registry changes:
   - `python scripts/build_registry_snapshot.py`
   - `python scripts/validate_recipes.py`
