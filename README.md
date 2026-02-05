# hpc-oda-commons

_A community hub for **HPC Operational Data Analytics (ODA)** — built for clarity, comparability, and fast adoption._

> **Status:** early-stage, community-driven initiative (v0.1 in development).  
> **Founding collaborators:** NREL, NERSC, and BSC.  
> **Open source:** public, permissive licensing; contributions welcome and encouraged.

## What this aims to be
**hpc-oda-commons** is a public, open repository that will make ODA research and practice **discoverable, standardized, and reproducible**. It brings together a curated index of **models, datasets, and tools/instrumentation**, a shared set of **standards + benchmarks + leaderboards**, and a simple **tooling path** to run the same benchmarks on **your own data**, so results are apples-to-apples across sites.

## The three pillars
- **Find** — a central place to discover **models, datasets, and tools** (e.g., XDMoD, LDMS, Darshan, schedulers/simulators, digital twins, controllers) relevant to HPC ODA.  
- **Compare** — community **standards, benchmarks, and leaderboards** so results are measured the same way.  
- **Run** — a straightforward toolchain to **execute benchmarks on your own data** and produce reproducible, evidence-backed results.

> Goal: **standardize and unify** this domain — and help each other turn ideas into practice.

## The initial user experience we’re targeting (~10 minutes)
1. **Browse** the registry to pick a task (e.g., runtime or queue-time prediction).  
2. **Run** a baseline on a public dataset to see the metrics we all use.  
3. **Point** the same benchmark at your local logs (kept on-site) to get **comparable results** you can share internally.

## Who this is for
- **Site operators & sysadmins** — evaluate ideas on local data with minimal plumbing.  
- **Researchers & vendors** — submit models once and compare fairly across datasets and sites.  
- **Program managers** — track progress with transparent, reproducible leaderboards.

## Project Status

This repository is under active development toward **v0.1.0**, focused on a vertical slice for **SLURM Job Runtime Prediction**.

- v0.1 scope and exit criteria: **docs/concepts/v0_1_charter.md**
- Roadmap: **ROADMAP.md**

## Quickstart (10-minute workflow)
1. Install: `pip install -e ".[dev]"`
2. Initialize: `hpc-oda init`
3. Browse: `hpc-oda browse`
4. Run baseline: `HPC_ODA_OFFLINE=1 hpc-oda run-baseline`
5. Ingest logs: `hpc-oda ingest slurmctld --path /path/to/slurmctld.log`
6. Validate data: `hpc-oda validate data/ingested/slurmctld/<run>/data.parquet`
7. Benchmark: `HPC_ODA_OFFLINE=1 hpc-oda benchmark hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml`
8. Leaderboard: `hpc-oda leaderboard --runs runs --out leaderboard`


## Repo organization:

```
hpc-oda-commons/
├─ README.md                         # What this is, who it’s for, 10-minute quickstart, links to docs/leaderboard
├─ LICENSE                           # Project license (e.g., Apache-2.0 or BSD-3-Clause)
├─ NOTICE                            # Required notices (if Apache-2.0) and third-party attributions
├─ CHANGELOG.md                      # Human-readable release notes (keep updated per tag)
├─ CITATION.cff                      # Citation metadata for academic use
├─ CODE_OF_CONDUCT.md                # Community behavior expectations
├─ CONTRIBUTING.md                   # How to contribute (code, schema, adapters, models, recipes, docs)
├─ GOVERNANCE.md                     # Roles, decision process, TSC description, voting/consensus rules
├─ SECURITY.md                       # Vulnerability reporting and security expectations
├─ SUPPORT.md                        # Where to ask questions (issues/discussions), response expectations
├─ ROADMAP.md                        # Near-term and longer-term milestones (v0.1 → v0.2+)
├─ pyproject.toml                    # Build system + dependencies + optional extras + tool configs
├─ MANIFEST.in                       # Ensures non-Python artifacts are packaged (schemas, registry snapshot, etc.)
├─ .gitignore                        # Standard ignores (build/, dist/, .venv/, .hpc_oda/, caches)
├─ .gitattributes                    # Line endings, linguist hints, large-file rules (optional)
├─ .editorconfig                     # Editor-agnostic formatting consistency
├─ .pre-commit-config.yaml           # Pre-commit hooks (format, lint, whitespace, yaml)
├─ ruff.toml                         # Lint configuration (or in pyproject.toml)
├─ mypy.ini                          # Type checking configuration (or in pyproject.toml)
├─ pytest.ini                        # Pytest configuration (or in pyproject.toml)
├─ tox.ini                           # Multi-env test runner (optional; choose tox or nox)
├─ noxfile.py                        # Task automation (lint/test/docs/build) (optional)
├─ Makefile                          # Convenience targets (dev, test, docs, release) (optional)
│
├─ .github/
│  ├─ ISSUE_TEMPLATE/
│  │  ├─ bug_report.yml              # Structured bug reports
│  │  ├─ feature_request.yml         # Structured feature proposals
│  │  ├─ adapter_request.yml         # New data-source adapter request
│  │  ├─ model_request.yml           # New model plugin request
│  │  ├─ schema_evolution_request.yml# SER template (schema change proposal)
│  │  ├─ benchmark_recipe.yml        # New benchmark/recipe proposal
│  │  └─ config.yml                  # GitHub template settings
│  ├─ PULL_REQUEST_TEMPLATE.md       # PR checklist (tests, docs, schema/recipe updates)
│  ├─ dependabot.yml                 # Dependency update automation
│  ├─ CODEOWNERS                     # Review routing for schema/recipes/core areas
│  └─ workflows/
│     ├─ ci.yml                      # Lint + unit tests + build + minimal “golden path” run
│     ├─ docs.yml                    # Build/publish docs site
│     ├─ release.yml                 # Tag-driven build/publish to PyPI + GitHub Release
│     ├─ benchmark-smoke.yml         # Fast benchmark recipe smoke test (tiny synthetic)
│     └─ leaderboard.yml             # Generate/update static leaderboard artifacts (scheduled/manual)
│
├─ docs/
│  ├─ mkdocs.yml                     # Docs configuration (or sphinx conf.py if using Sphinx)
│  ├─ index.md                       # Landing page (install + 10-minute workflow)
│  ├─ concepts/
│  │  ├─ pillars.md                  # How Find/Compare/Run map to components
│  │  ├─ schema.md                   # Schema philosophy, versioning, SER process
│  │  ├─ artifacts.md                # Parquet + manifests + result bundles
│  │  ├─ security-data-handling.md   # Local-first, transformation policy, handling guidance
│  │  └─ benchmarks.md               # Recipes, metrics, reproducibility expectations
│  ├─ how-to/
│  │  ├─ install.md                  # Install options + extras
│  │  ├─ quickstart.md               # Step-by-step minimal workflow
│  │  ├─ ingest-slurmctld.md         # Slurmctld ingestion guide
│  │  ├─ add-adapter.md              # Writing a source adapter plugin
│  │  ├─ add-model.md                # Writing a model plugin
│  │  ├─ add-recipe.md               # Writing a benchmark recipe
│  │  └─ contribute.md               # Contribution paths and expectations
│  ├─ reference/
│  │  ├─ cli.md                      # CLI command reference
│  │  ├─ python-api.md               # Public Python API reference
│  │  ├─ schema-versions.md          # List of schema versions and changelog pointers
│  │  └─ recipes.md                  # List of built-in recipes and what they do
│  └─ assets/
│     ├─ images/                     # Diagrams/screenshots for docs
│     └─ diagrams/                   # Source diagrams (e.g., drawio/mermaid sources)
│
├─ src/
│  └─ hpc_oda_commons/
│     ├─ __init__.py                 # Package version export, high-level imports (keep minimal)
│     ├─ __main__.py                 # Enables `python -m hpc_oda_commons` to invoke CLI
│     ├─ version.py                  # Single source of truth for version (if not using dynamic tooling)
│     │
│     ├─ schema/
│     │  ├─ __init__.py              # Schema loading + validation entry points
│     │  ├─ validator.py             # JSONSchema + additional semantic checks glue
│     │  ├─ quality_rules.py         # Pluggable data quality rules (v0.1 defaults here)
│     │  └─ quality_rules.py         # Pluggable data quality rules (v0.1 defaults here)
│     │
│     ├─ registry/
│     │  ├─ __init__.py              # Registry API (search/filter/resolve)
│     │  ├─ models.py                # Metadata models (adapter/model/tool/recipe entries)
│     │  ├─ snapshot.py              # Bundled snapshot loading + optional update mechanism
│     │  ├─ index.py                 # In-memory indices + filtering logic (Find pillar)
│     │  └─ validate.py              # Validates registry JSON against registry schema
│     │
│     ├─ adapters/
│     │  ├─ __init__.py              # Official adapters shipped with package
│     │  ├─ slurmctld/
│     │  │  ├─ __init__.py           # Slurmctld adapter package
│     │  │  ├─ adapter.py            # SourceAdapter implementation for slurmctld logs
│     │  │  ├─ parser.py             # Parsing logic (regex/state machine) + normalization
│     │  │  ├─ mapping.py            # Field mapping to oda.job schema fields
│     │  │  ├─ labeling.py           # Failure label derivation rules (exit_code, messages, etc.)
│     │  │  ├─ fixtures.py           # Small parser fixtures for tests/docs
│     │  │  └─ README.md             # Adapter-specific notes and limitations
│     ├─ models/
│     │  ├─ __init__.py              # Official baseline models shipped with package
│     │  └─ job_runtime_baseline/
│     │     ├─ __init__.py           # Baseline model package
│     │     ├─ model.py              # ModelPlugin implementation (train/infer)
│     │     ├─ features.py           # Feature extraction from oda.job tables
│     │     ├─ calibrate.py          # Optional threshold calibration utilities
│     │     ├─ explain.py            # Simple feature importance / coefficients extraction
│     │     └─ README.md             # Model scope, assumptions, expected inputs/outputs
│     │
│     ├─ tools/
│     │  ├─ __init__.py              # Utility “tools” that aren’t models (optional)
│     │  └─ report/
│     │     ├─ __init__.py           # Report generation utilities
│     │     └─ html.py               # Lightweight HTML report builder for local results
│     │
│     ├─ benchmark/
│     │  ├─ __init__.py              # Benchmark APIs (Compare pillar)
│     │  └─ results.py               # Result bundle schema + leaderboard helpers
│     │
│     ├─ qst/
│     │  ├─ __init__.py              # Quickstart Toolkit entry points (Run pillar)
│     │  ├─ cli.py                   # Root CLI definition + subcommand registration
│     │  ├─ config.py                # Project config model (hpc-oda.toml) + defaults
│     │  ├─ project.py               # Project init/layout, state dir (.hpc_oda) management
│     │  ├─ commands/
│     │  │  ├─ __init__.py           # CLI command package (browse/info only)
│     │  │  ├─ browse.py             # `hpc-oda browse`
│     │  │  └─ info.py               # `hpc-oda info` for adapters/models/recipes
│     │
│     └─ utils/
│        ├─ __init__.py               # Small shared helpers (keep lean)
│        ├─ io.py                     # Small IO helpers not in core/artifacts
│        ├─ time.py                   # Timestamp parsing/binning helpers
│        └─ logging.py                # Standard logger configuration
│
├─ schemas/
│  ├─ oda/
│  │  ├─ job/
│  │  │  └─ v0.1.0.json              # Core ODA schema for v0.1 vertical slice
│  │  ├─ result/
│  │  │  └─ v0.1.0.json              # Result bundle schema (leaderboard reads this)
│  │  └─ registry/
│  │     └─ v0.1.0.json              # Registry metadata schema
│  └─ README.md                      # How schema versioning works + SER instructions
│
├─ registry/
│  ├─ snapshot.json                  # Curated offline index of adapters/models/recipes
│  ├─ snapshot.sig                   # Optional signature/checksum for integrity
│  └─ README.md                      # How snapshots are generated + updated
│
├─ recipes/
│  ├─ README.md                      # What recipes are, naming conventions, required fields
│  └─ job-runtime/
│     └─ baseline_tiny.yml           # Tiny synthetic runtime prediction recipe (v0.1)
│
├─ datasets/
│  ├─ README.md                      # Dataset policy: manifests only, hosting pointers, licensing rules
│  ├─ synthetic/
│  │  └─ job-runtime/
│  │     └─ tiny/
│  │        ├─ data.parquet          # Tiny dataset used for offline baseline
│  │        └─ manifest.json         # Provenance + schema version + generation params
│  └─ external/
│     ├─ zenodo_links.yml            # Pointers to externally hosted datasets + checksums
│     └─ golden_datasets.yml         # Curated “golden” references (if any exist for v0.1)
│
├─ leaderboard/
│  └─ README.md                      # How leaderboard is generated and what it contains
│
├─ containers/
│  ├─ README.md                      # How to run with containers on HPC
│  ├─ Dockerfile                     # Optional container build
│  ├─ apptainer.def                  # Apptainer/Singularity definition for HPC sites
│  └─ env/
│     ├─ environment.yml             # Conda environment for container builds
│     └─ constraints.txt             # Pinned constraints for reproducibility
│
├─ scripts/
│  ├─ build_registry_snapshot.py     # Build registry snapshot from installed/official plugins+recipes
│  ├─ validate_recipes.py            # Pre-commit/CI validation for recipe format + MDL
│  ├─ validate_schemas.py            # Schema sanity checks (semver, required metadata, examples)
│  ├─ release_checklist.md           # Human release steps not easily automated
│  └─ dev_bootstrap.sh               # Developer convenience setup (optional)
│
├─ examples/
│  ├─ README.md                      # What examples exist and how to run them
│  ├─ notebooks/
│  │  ├─ 00_quickstart.ipynb         # Walkthrough: init → run-baseline → ingest → run
│  │  ├─ 01_slurmctld_ingest.ipynb   # Deep dive: parsing + mapping + transformations
│  │  └─ 02_benchmark_compare.ipynb  # Compare models via recipes and view bundles
│  └─ projects/
│     └─ sample_project/             # Minimal example project directory created by `hpc-oda init`
│        ├─ hpc-oda.toml             # Example config file
│        └─ README.md                # Instructions for sample project usage
│
├─ tests/
│  ├─ README.md                      # Test strategy: unit vs integration vs golden path
│  ├─ conftest.py                    # Shared pytest fixtures
│  ├─ unit/
│  │  ├─ test_schema_loader.py       # Schema loading/version parsing tests
│  │  ├─ test_validator.py           # Validation rules and error reporting tests
│  │  ├─ test_registry.py            # Filtering/search tests
│  │  ├─ test_recipe_parsing.py      # Recipe schema + MDL parsing tests
│  │  ├─ test_result_bundle.py       # Result bundle schema and I/O tests
│  │  ├─ test_security_policy.py     # Transformation policy behavior tests
│  │  └─ test_plugins_entrypoints.py # Plugin discovery tests
│  ├─ integration/
│  │  ├─ test_cli_golden_path.py     # End-to-end: init → run-baseline → ingest → validate → run
│  │  ├─ test_slurmctld_ingest.py    # Parses fixture logs and produces schema-valid outputs
│  │  └─ test_benchmark_smoke.py     # Runs baseline_tiny recipe and validates outputs
│  └─ fixtures/
│     ├─ slurmctld.log               # Small sample log for parser tests
│     ├─ expected_job_table.parquet  # Expected parsed output for regression checks
│     ├─ expected_manifest.json      # Expected manifest output (minus volatile fields)
│     └─ recipes/
│        └─ baseline_tiny.yml        # Fixture recipe for tests
│
└─ .devcontainer/                    # Optional: VSCode devcontainer setup
   ├─ devcontainer.json              # Devcontainer configuration
   └─ Dockerfile                     # Devcontainer image (separate from runtime container)

```

## Contribute
- Add a **dataset, model, or tool card** (link-first, with immutable references and SPDX license info).  
- Propose a **benchmark** (task, metrics, and minimal baseline).  
- Share a **result card** to update the leaderboard via PR.  
We welcome early contributors from across the community. Please open an issue to get involved.

> Note: the tools registry is **link-first** and non-endorsement; it’s for discoverability and interoperability signals.

---

**This repo complements the BoF series on AI for HPC Workload Analytics** — the BoF sets community priorities; **hpc-oda-commons operationalizes them** with shared artifacts and repeatable results.
