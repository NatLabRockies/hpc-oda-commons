# v0.1 Release Checklist — SLURM Job Runtime Prediction

This checklist is the practical “ship list” for **hpc-oda-commons v0.1.0**.  
v0.1 is a vertical slice for **SLURM job runtime prediction** using **slurmctld logs**.

**Definition of Done (DoD) gates (must pass):**
- DoD-1: `pip install -e .` and `hpc-oda --help` works
- DoD-2: `hpc-oda run-baseline` produces a result bundle **offline**
- DoD-3: `hpc-oda ingest slurmctld …` produces **schema-valid** Parquet + manifest
- DoD-4: `hpc-oda benchmark recipes/job-runtime/baseline_tiny.yml` produces comparable metrics + provenance

---

## 1) Scope & Documentation Alignment (No surprises)

- [ ] `docs/concepts/v0_1_charter.md` exists and matches the intended v0.1 runtime-prediction scope.
- [ ] `README.md` explicitly states v0.1 focus: **SLURM Job Runtime Prediction** and links the charter.
- [ ] `ROADMAP.md` includes a v0.1 section and links the charter.
- [ ] Non-goals for v0.1 are explicitly documented and unchanged.

---

## 2) CLI Commands Exist and Are Documented

### Required commands (v0.1)
- [ ] `hpc-oda --help` returns exit code 0 and shows top-level commands.
- [ ] `hpc-oda init` exists and creates a local project skeleton.
- [ ] `hpc-oda browse` exists and works offline (uses bundled registry snapshot).
- [ ] `hpc-oda info` exists for adapters/models/recipes.
- [ ] `hpc-oda run-baseline` exists and works offline.
- [ ] `hpc-oda ingest slurmctld --path ...` exists.
- [ ] `hpc-oda validate ...` exists.
- [ ] `hpc-oda benchmark <recipe>` exists and produces a result bundle.

### Documentation sync
- [ ] `docs/how-to/quickstart.md` matches the actual CLI commands and output paths.
- [ ] `docs/reference/cli.md` lists and describes each required command.
- [ ] CLI output paths and filenames shown in docs match reality (no stale screenshots/paths).

---

## 3) Registry Snapshot (Find Pillar)

**Goal:** Offline discoverability of the official v0.1 adapter/model/recipe.

- [ ] `registry/snapshot.json` exists and is packaged (included in wheel/sdist).
- [ ] Snapshot includes entries for:
  - [ ] slurmctld adapter (official)
  - [ ] baseline runtime prediction model (official)
  - [ ] `recipes/job-runtime/baseline_tiny.yml`
- [ ] Each entry includes compatibility metadata:
  - [ ] problem domain tags include runtime prediction (e.g., `job-runtime-prediction`)
  - [ ] schema version compatibility is explicit
  - [ ] recipe/model references are resolvable (path or identifier)
- [ ] `hpc-oda browse` can filter/list the runtime-prediction vertical slice offline.

---

## 4) Schemas & Canonical Artifacts (Standardization Backbone)

### Schemas
- [ ] v0.1 input schema exists and is packaged:
  - [ ] `schemas/oda/job/v0.1.0.json` (job schema sufficient for runtime prediction)
- [ ] v0.1 registry schema exists and is packaged:
  - [ ] `schemas/oda/registry/v0.1.0.json`
- [ ] v0.1 result bundle schema exists and is packaged:
  - [ ] `schemas/oda/result/v0.1.0.json`
- [ ] Schema IDs and versions are referenced consistently in code, recipes, and docs.
- [ ] Schema is treated as frozen for v0.1 (no breaking changes post-freeze).

### Canonical artifacts produced by the system
- [ ] Ingest produces:
  - [ ] Parquet ODA table (runtime prediction fields present)
  - [ ] manifest JSON containing:
    - [ ] schema version
    - [ ] adapter ID/version
    - [ ] transformation ledger (even if empty)
    - [ ] provenance inputs/hashes (as available)
- [ ] Benchmark produces:
  - [ ] result bundle directory containing at least:
    - [ ] `result.json`
    - [ ] `metrics.json`
    - [ ] `provenance.json`

---

## 5) Tiny Synthetic Dataset (Offline Baseline)

**Goal:** `run-baseline` works with no network and no external data.

- [ ] A tiny synthetic dataset exists on disk in-repo and is packaged.
- [ ] Dataset includes a manifest (schema version + generation notes + hashes if available).
- [ ] Dataset is small enough to run quickly in CI (seconds, not minutes).

Suggested target locations (adjust to your chosen repo layout):
- [ ] `datasets/synthetic/job-runtime/tiny/data.parquet`
- [ ] `datasets/synthetic/job-runtime/tiny/manifest.json`

If you intentionally store the tiny dataset elsewhere:
- [ ] Docs and code reference the correct location consistently.

---

## 6) slurmctld Ingestion Works on Fixture Logs (Run Pillar)

**Goal:** Ingest works deterministically and produces schema-valid artifacts.

- [ ] Fixture log exists:
  - [ ] `tests/fixtures/slurmctld.log`
- [ ] `hpc-oda ingest slurmctld --path tests/fixtures/slurmctld.log ...` succeeds.
- [ ] Output Parquet + manifest validate against the v0.1 schema/requirements.
- [ ] Runtime targets/labels required for training/eval are derivable for the vertical slice:
  - [ ] runtime = end_time - start_time (or equivalent canonical definition)
- [ ] Safe transformations are supported (at minimum):
  - [ ] hashing/pseudonymization for user identifiers
  - [ ] optional timestamp binning / redaction hooks
- [ ] Ingest is local-first (no outbound calls required).

---

## 7) Baseline Model (Fast + Deterministic)

**Goal:** A baseline runtime prediction model exists and behaves predictably.

- [ ] Baseline model plugin exists and is discoverable (direct import or plugin mechanism).
- [ ] Model inputs and outputs are explicitly documented (schema version / fields).
- [ ] `hpc-oda run-baseline` runs the baseline model on the tiny synthetic dataset.
- [ ] Baseline run produces a result bundle offline.
- [ ] Model behavior is deterministic given fixed inputs (seeded if needed).

---

## 8) Benchmark Recipe + Runner (Compare Pillar)

**Goal:** Recipes produce comparable metrics and reproducible result bundles.

- [ ] Runtime prediction recipe exists:
  - [ ] `recipes/job-runtime/baseline_tiny.yml`
- [ ] Recipe specifies:
  - [ ] dataset reference (tiny synthetic)
  - [ ] baseline model reference
  - [ ] schema version requirement
  - [ ] metric configuration
- [ ] `hpc-oda benchmark recipes/job-runtime/baseline_tiny.yml` succeeds.
- [ ] Metrics are appropriate for runtime prediction (regression). At minimum, pick one:
  - [ ] MAE
  - [ ] RMSE
  - [ ] MAPE (optional; beware zeros)
  - [ ] R² (optional)
- [ ] Result bundle includes provenance sufficient to reproduce:
  - [ ] schema version(s)
  - [ ] dataset identifier/hash (as available)
  - [ ] model identifier/version
  - [ ] environment capture (at least minimal `pip freeze` or equivalent)
  - [ ] code version (git commit if available)

---

## 9) CI Runs Golden-Path Tests (No manual verification)

**Goal:** CI enforces the DoD gates and prevents regressions.

- [ ] Lint runs in CI (e.g., ruff).
- [ ] Unit tests run in CI.
- [ ] Integration tests run in CI and cover:
  - [ ] DoD-1 install + help
  - [ ] DoD-2 run-baseline offline
  - [ ] DoD-3 ingest fixture logs → schema-valid artifacts
  - [ ] DoD-4 benchmark baseline_tiny → result bundle with provenance
- [ ] CI runtime is reasonable (ideally <10 minutes total).

---

## 10) Packaging & Installation Validation

- [ ] `pip install -e .` works in a clean environment.
- [ ] `pip install .` (wheel/sdist) includes required non-code artifacts:
  - [ ] schemas
  - [ ] registry snapshot
  - [ ] tiny synthetic dataset + manifest
  - [ ] recipes
- [ ] `python -m hpc_oda_commons --help` works (if supported).
- [ ] Optional extras do not break core install (e.g., `[viz]` is truly optional).

---

## 11) Security & Data Handling (v0.1 expectations)

- [ ] `SECURITY.md` exists and describes vulnerability reporting.
- [ ] Data handling is local-first by default (no uploads).
- [ ] Transformation policy is explicit and recorded in manifests (even if minimal).
- [ ] No credentials, tokens, or sensitive fixture data are committed.

---

## 12) Minimal Leaderboard Generation (Local)

- [ ] Leaderboard generator script exists and runs locally.
- [ ] It reads one or more result bundles and emits:
  - [ ] `leaderboard.json`
  - [ ] (optional) `index.html`
- [ ] Leaderboard artifacts are clearly marked as generated outputs (not hand-edited).

---

## 13) Release Hygiene (Final checks)

- [ ] Version is set to `0.1.0` (or appropriate) consistently.
- [ ] `CHANGELOG.md` has a v0.1.0 entry describing the runtime-prediction vertical slice.
- [ ] `CITATION.cff` is populated (optional but recommended).
- [ ] License files are present and correct.
- [ ] Tagging/release process documented and reproducible.

---

## 14) Final “Go/No-Go” Summary

Before tagging v0.1.0, confirm:
- [ ] All DoD gates pass locally
- [ ] All DoD gates pass in CI
- [ ] Docs quickstart matches the exact CLI behavior
- [ ] Registry snapshot lists the runtime prediction vertical slice offline
- [ ] A new user can complete the offline baseline workflow without network access
