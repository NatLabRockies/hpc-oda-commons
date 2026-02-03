#!/usr/bin/env bash
# Scaffold the full hpc-oda-commons repo structure (v0.1) with placeholder content.
# Usage:
#   ./scaffold_hpc_oda_commons.sh [target_dir]
# Example:
#   ./scaffold_hpc_oda_commons.sh hpc-oda-commons

set -euo pipefail

ROOT="${1:-hpc-oda-commons}"

# -------- helpers --------
write_file() {
  local rel="$1"
  local content="$2"
  local full="${ROOT}/${rel}"

  mkdir -p "$(dirname "$full")"

  if [[ -e "$full" ]]; then
    echo "SKIP (exists): $full"
    return 0
  fi

  printf "%s" "$content" > "$full"
  echo "CREATE: $full"
}

escape_json_string() {
  # Escape backslashes then double quotes for safe embedding in JSON strings.
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  printf "%s" "$s"
}

py_stub() {
  local comment="$1"
  local tmpl
  tmpl=$(cat <<'PY'
"""
__COMMENT__
"""

from __future__ import annotations

PY
)
  tmpl="${tmpl//__COMMENT__/${comment}}"
  printf "%s" "$tmpl"
}

md_stub() {
  local title="$1"
  local comment="$2"
  cat <<MD
# ${title}

<!-- ${comment} -->
MD
}

yml_stub() { local comment="$1"; printf "# %s\n" "$comment"; }
toml_stub() { local comment="$1"; printf "# %s\n" "$comment"; }
ini_stub() { local comment="$1"; printf "; %s\n" "$comment"; }

json_stub() {
  local comment="$1"
  local esc
  esc="$(escape_json_string "$comment")"
  cat <<JSON
{
  "_comment": "${esc}"
}
JSON
}

css_stub() { local comment="$1"; printf "/* %s */\n" "$comment"; }

html_stub() {
  local comment="$1"
  cat <<HTML
<!-- ${comment} -->
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>hpc-oda-commons</title>
  </head>
  <body>
    <h1>hpc-oda-commons</h1>
    <p>Placeholder HTML. Replace with generated leaderboard output.</p>
  </body>
</html>
HTML
}

jinja_stub() {
  local comment="$1"
  cat <<J2
{# ${comment} #}
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>ODA Leaderboard</title>
    <link rel="stylesheet" href="style.css">
  </head>
  <body>
    <h1>ODA Leaderboard</h1>
    <p>Placeholder Jinja2 template. Replace with real layout.</p>
  </body>
</html>
J2
}

sh_stub() {
  local comment="$1"
  cat <<SH
#!/usr/bin/env bash
# ${comment}

set -euo pipefail
SH
}

docker_stub() {
  local comment="$1"
  cat <<DOCKER
# ${comment}
FROM python:3.11-slim

# Placeholder container. Replace with a real build for HPC-ODA Commons.
WORKDIR /app
COPY . /app
RUN pip install -U pip && pip install -e .
CMD ["python", "-m", "hpc_oda_commons", "--help"]
DOCKER
}

apptainer_stub() {
  local comment="$1"
  cat <<DEF
# ${comment}
Bootstrap: docker
From: python:3.11-slim

%post
    echo "Placeholder Apptainer/Singularity definition."
    pip install -U pip
    # In a real build you would copy project contents and install.

%runscript
    exec python -m hpc_oda_commons --help
DEF
}

ipynb_stub() {
  local comment="$1"
  local esc
  esc="$(escape_json_string "$comment")"
  cat <<JSON
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# Notebook Placeholder\\n",
        "\\n",
        "${esc}\\n"
      ]
    }
  ],
  "metadata": {
    "kernelspec": {
      "display_name": "Python 3",
      "language": "python",
      "name": "python3"
    },
    "language_info": {
      "name": "python",
      "version": "3.x"
    }
  },
  "nbformat": 4,
  "nbformat_minor": 5
}
JSON
}

# -------- top-level files --------
write_file "README.md" "$(md_stub "hpc-oda-commons" "Project overview, audiences, and 10-minute quickstart. Link to docs and leaderboard.")"
write_file "LICENSE" "TODO: Choose a license (e.g., Apache-2.0 or BSD-3-Clause) and paste full text here.\n"
write_file "NOTICE" "NOTICE\n\nPlaceholder notices and third-party attributions (needed for some licenses).\n"
write_file "CHANGELOG.md" "$(md_stub "Changelog" "Release notes per version tag. Keep updated for every release.")"
write_file "CITATION.cff" "$(yml_stub "Citation metadata for academic use (CFF format). Fill in authors/title/version/doi.")"
write_file "CODE_OF_CONDUCT.md" "$(md_stub "Code of Conduct" "Community behavior expectations and enforcement guidelines.")"
write_file "CONTRIBUTING.md" "$(md_stub "Contributing" "Contribution guide: code, schema (SER), adapters, models, recipes, docs.")"
write_file "GOVERNANCE.md" "$(md_stub "Governance" "Roles and decision process (e.g., TSC), including schema evolution governance.")"
write_file "SECURITY.md" "$(md_stub "Security" "Vulnerability reporting, data-handling expectations, and secure development practices.")"
write_file "SUPPORT.md" "$(md_stub "Support" "Where to ask questions (issues/discussions) and support boundaries.")"
write_file "ROADMAP.md" "$(md_stub "Roadmap" "Milestones and planned phases (v0.1 vertical slice → v0.2+).")"

write_file "pyproject.toml" "$(cat <<'TOML'
# Build metadata, dependencies, and tooling config for hpc-oda-commons.

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "hpc-oda-commons"
version = "0.1.0"
description = "HPC Operational Data Analytics Commons: schema, adapters, models, and reproducible benchmarks."
readme = "README.md"
requires-python = ">=3.9"
license = { file = "LICENSE" }
authors = [{ name = "HPC-ODA Commons Contributors" }]
dependencies = [
  # Keep v0.1 lean; add as needed:
  # "pydantic>=2",
  # "jsonschema>=4",
  # "pandas>=2",
  # "pyarrow>=14",
  # "typer>=0.9",
  # "rich>=13",
]

[project.optional-dependencies]
viz = [
  # Optional visualization extras (v0.1): choose one later (streamlit/dash).
]
dev = [
  "pytest>=8",
  "ruff>=0.5",
  "mypy>=1.10",
  "pre-commit>=3.7",
]

[project.scripts]
hpc-oda = "hpc_oda_commons.qst.cli:app"

[tool.setuptools.packages.find]
where = ["src"]
TOML
)"
write_file "MANIFEST.in" "# Include non-Python artifacts in sdist/wheel.\nrecursive-include schemas *.json\nrecursive-include registry *.json *.sig\nrecursive-include recipes *.yml *.yaml *.toml *.txt\nrecursive-include datasets *\nrecursive-include docs *\n"
write_file ".gitignore" "# Python\n__pycache__/\n*.pyc\n.venv/\ndist/\nbuild/\n*.egg-info/\n\n# Project runtime state\n.hpc_oda/\n\n# Notebooks\n.ipynb_checkpoints/\n"
write_file ".gitattributes" "# Repo attributes (line endings, linguist hints, etc.).\n"
write_file ".editorconfig" "root = true\n\n[*]\nend_of_line = lf\ninsert_final_newline = true\ncharset = utf-8\nindent_style = space\nindent_size = 2\n"
write_file ".pre-commit-config.yaml" "$(yml_stub "Pre-commit hooks (format/lint/yaml). Add ruff, trailing whitespace, etc.")"
write_file "ruff.toml" "$(toml_stub "Ruff linting configuration (can also live in pyproject.toml).")"
write_file "mypy.ini" "$(ini_stub "Mypy type-checking configuration.")"
write_file "pytest.ini" "$(ini_stub "Pytest configuration (markers, testpaths).")"
write_file "tox.ini" "$(ini_stub "Tox configuration for multi-environment testing (optional).")"
write_file "noxfile.py" "$(py_stub "Nox sessions for lint/test/docs/release tasks (optional).")"
write_file "Makefile" "# Convenience targets (optional).\n.PHONY: test lint\n\ntest:\n\tpytest -q\n\nlint:\n\truff check .\n"

# -------- .github --------
write_file ".github/ISSUE_TEMPLATE/bug_report.yml" "$(yml_stub "Structured bug report template.")"
write_file ".github/ISSUE_TEMPLATE/feature_request.yml" "$(yml_stub "Structured feature request template.")"
write_file ".github/ISSUE_TEMPLATE/adapter_request.yml" "$(yml_stub "Template for requesting or proposing a new source adapter.")"
write_file ".github/ISSUE_TEMPLATE/model_request.yml" "$(yml_stub "Template for proposing a new model plugin.")"
write_file ".github/ISSUE_TEMPLATE/schema_evolution_request.yml" "$(yml_stub "SER template for proposing schema changes (RFC-like).")"
write_file ".github/ISSUE_TEMPLATE/benchmark_recipe.yml" "$(yml_stub "Template for proposing a new benchmark recipe.")"
write_file ".github/ISSUE_TEMPLATE/config.yml" "$(yml_stub "GitHub issue template configuration.")"
write_file ".github/PULL_REQUEST_TEMPLATE.md" "$(md_stub "Pull Request Template" "Checklist: tests, docs, schema/recipe updates, provenance considerations.")"
write_file ".github/dependabot.yml" "$(yml_stub "Dependabot config for dependency update PRs.")"
write_file ".github/CODEOWNERS" "# CODEOWNERS: assign reviewers by area (schemas/, recipes/, src/hpc_oda_commons/core/...).\n"
write_file ".github/workflows/ci.yml" "$(yml_stub "CI pipeline: lint + unit tests + build + golden-path smoke test.")"
write_file ".github/workflows/docs.yml" "$(yml_stub "Docs build and publish workflow.")"
write_file ".github/workflows/release.yml" "$(yml_stub "Release workflow: build artifacts and publish on tags.")"
write_file ".github/workflows/benchmark-smoke.yml" "$(yml_stub "Fast benchmark recipe smoke workflow (tiny synthetic).")"
write_file ".github/workflows/leaderboard.yml" "$(yml_stub "Generate static leaderboard artifacts on schedule or manually.")"

# -------- docs --------
write_file "docs/mkdocs.yml" "$(yml_stub "MkDocs configuration (or switch to Sphinx).")"
write_file "docs/index.md" "$(md_stub "Docs Home" "Docs landing page: install + 10-minute workflow + navigation.")"
write_file "docs/concepts/pillars.md" "$(md_stub "Pillars" "Explain Find/Compare/Run and how they map to components.")"
write_file "docs/concepts/schema.md" "$(md_stub "Schema" "Schema philosophy, versioning, and SER process.")"
write_file "docs/concepts/artifacts.md" "$(md_stub "Artifacts" "Describe Parquet tables, manifests, and result bundles.")"
write_file "docs/concepts/security-data-handling.md" "$(md_stub "Security & Data Handling" "Local-first processing and safe transformation policy guidance.")"
write_file "docs/concepts/benchmarks.md" "$(md_stub "Benchmarks" "Benchmark recipes, metric definitions, reproducibility expectations.")"
write_file "docs/how-to/install.md" "$(md_stub "Install" "Installation instructions and optional extras (viz/dev).")"
write_file "docs/how-to/quickstart.md" "$(md_stub "Quickstart" "Step-by-step minimal workflow: init → run-baseline → ingest → validate → run.")"
write_file "docs/how-to/ingest-slurmctld.md" "$(md_stub "Ingest slurmctld" "Guide for slurmctld parsing/mapping and safe transforms.")"
write_file "docs/how-to/add-adapter.md" "$(md_stub "Add an Adapter" "How to implement a SourceAdapter plugin and publish via entry points.")"
write_file "docs/how-to/add-model.md" "$(md_stub "Add a Model" "How to implement a ModelPlugin and provide recipes/tests.")"
write_file "docs/how-to/add-recipe.md" "$(md_stub "Add a Recipe" "How to define a benchmark recipe and metrics (MDL).")"
write_file "docs/how-to/contribute.md" "$(md_stub "Contribute" "Contribution paths and expected quality bar for PRs.")"
write_file "docs/reference/cli.md" "$(md_stub "CLI Reference" "Command reference for hpc-oda CLI (QST).")"
write_file "docs/reference/python-api.md" "$(md_stub "Python API" "Public Python APIs and stability guarantees.")"
write_file "docs/reference/schema-versions.md" "$(md_stub "Schema Versions" "List schema IDs/versions and changelog pointers.")"
write_file "docs/reference/recipes.md" "$(md_stub "Recipes Reference" "Built-in recipes and what they measure.")"
write_file "docs/assets/images/.gitkeep" "# Placeholder to keep images/ in git.\n"
write_file "docs/assets/diagrams/.gitkeep" "# Placeholder to keep diagrams/ in git.\n"

# -------- src package --------
write_file "src/hpc_oda_commons/__init__.py" "$(py_stub "Package init. Keep minimal; expose version and key entry points.")"
write_file "src/hpc_oda_commons/__main__.py" "$(cat <<'PY'
"""
Entrypoint for `python -m hpc_oda_commons` (delegates to CLI).
"""
from __future__ import annotations

from hpc_oda_commons.qst.cli import app

if __name__ == "__main__":
    app()
PY
)"
write_file "src/hpc_oda_commons/version.py" "$(py_stub "Single source of truth for package version (optional if using dynamic versioning).")"

# core
write_file "src/hpc_oda_commons/core/__init__.py" "$(py_stub "Stable core interfaces and canonical artifacts. Treat as API-stable zone.")"
write_file "src/hpc_oda_commons/core/types.py" "$(py_stub "Shared typing aliases and small dataclasses used across modules.")"
write_file "src/hpc_oda_commons/core/errors.py" "$(py_stub "Canonical exception types (validation, adapter, recipe, benchmark errors).")"
write_file "src/hpc_oda_commons/core/constants.py" "$(py_stub "Shared constants (default dirs, filenames, schema IDs).")"
write_file "src/hpc_oda_commons/core/paths.py" "$(py_stub "Project-relative path resolution utilities for QST projects.")"
write_file "src/hpc_oda_commons/core/artifacts.py" "$(py_stub "Read/write helpers for ODA tables (Parquet) + manifests + result bundles.")"
write_file "src/hpc_oda_commons/core/provenance.py" "$(py_stub "Hashing and provenance record creation (inputs/env/code/schema versions).")"

# schema
write_file "src/hpc_oda_commons/schema/__init__.py" "$(py_stub "Schema loading and validation entry points.")"
write_file "src/hpc_oda_commons/schema/ids.py" "$(py_stub "Schema identifier parsing and canonicalization (e.g., oda.job.v0.1.0).")"
write_file "src/hpc_oda_commons/schema/loader.py" "$(py_stub "Load bundled JSON Schemas by ID/version from /schemas.")"
write_file "src/hpc_oda_commons/schema/validator.py" "$(py_stub "JSONSchema validation + additional semantic checks glue.")"
write_file "src/hpc_oda_commons/schema/quality_rules.py" "$(py_stub "Pluggable data quality rules (v0.1 defaults live here).")"
write_file "src/hpc_oda_commons/schema/migration.py" "$(py_stub "Minimal migration helpers between schema versions (expand later).")"

# registry
write_file "src/hpc_oda_commons/registry/__init__.py" "$(py_stub "Registry API: search/filter/resolve for Find pillar.")"
write_file "src/hpc_oda_commons/registry/models.py" "$(py_stub "Metadata models for adapters/models/tools/recipes (registry entries).")"
write_file "src/hpc_oda_commons/registry/snapshot.py" "$(py_stub "Load bundled registry snapshot + optional update mechanism.")"
write_file "src/hpc_oda_commons/registry/index.py" "$(py_stub "In-memory indices and filtering logic (tags, schema compat, etc.).")"
write_file "src/hpc_oda_commons/registry/validate.py" "$(py_stub "Validate registry JSON against registry schema.")"

# plugins
write_file "src/hpc_oda_commons/plugins/__init__.py" "$(py_stub "Plugin discovery: entry points and contract definitions.")"
write_file "src/hpc_oda_commons/plugins/entrypoints.py" "$(py_stub "Discover installed plugins via importlib.metadata entry points.")"
write_file "src/hpc_oda_commons/plugins/contracts.py" "$(py_stub "ABCs/Protocols for adapters/models/tools/metrics.")"
write_file "src/hpc_oda_commons/plugins/metadata.py" "$(py_stub "Standard metadata assembly, normalization, and validation for discoverability.")"

# security
write_file "src/hpc_oda_commons/security/__init__.py" "$(py_stub "Security-related APIs: transformation policy and helpers.")"
write_file "src/hpc_oda_commons/security/policy.py" "$(py_stub "TransformationPolicy definition + safe defaults (local-first).")"
write_file "src/hpc_oda_commons/security/anonymize.py" "$(py_stub "Hashing/pseudonymization helpers for sensitive identifiers.")"
write_file "src/hpc_oda_commons/security/fuzz.py" "$(py_stub "Noise injection helpers (controlled; optional).")"
write_file "src/hpc_oda_commons/security/aggregate.py" "$(py_stub "Timestamp binning and aggregation helpers.")"
write_file "src/hpc_oda_commons/security/redaction.py" "$(py_stub "Field dropping/masking helpers.")"
write_file "src/hpc_oda_commons/security/scanners.py" "$(py_stub "Optional lightweight secret/PII pattern warnings (non-blocking by default).")"

# adapters
write_file "src/hpc_oda_commons/adapters/__init__.py" "$(py_stub "Official source adapters shipped with the package.")"
write_file "src/hpc_oda_commons/adapters/slurmctld/__init__.py" "$(py_stub "slurmctld adapter package.")"
write_file "src/hpc_oda_commons/adapters/slurmctld/adapter.py" "$(py_stub "SourceAdapter implementation for slurmctld logs (v0.1 vertical slice).")"
write_file "src/hpc_oda_commons/adapters/slurmctld/parser.py" "$(py_stub "Parsing logic for slurmctld logs (regex/state machine) and normalization.")"
write_file "src/hpc_oda_commons/adapters/slurmctld/mapping.py" "$(py_stub "Map parsed fields to oda.job schema fields.")"
write_file "src/hpc_oda_commons/adapters/slurmctld/labeling.py" "$(py_stub "Rules to derive failure labels (exit_code, messages, failure_reason).")"
write_file "src/hpc_oda_commons/adapters/slurmctld/fixtures.py" "$(py_stub "Small fixtures for tests/docs: sample log lines and expected parses.")"
write_file "src/hpc_oda_commons/adapters/slurmctld/README.md" "$(md_stub "slurmctld Adapter" "Adapter-specific notes, supported formats, limitations, examples.")"

write_file "src/hpc_oda_commons/adapters/xdmod/__init__.py" "$(py_stub "XDMoD adapter placeholder (expand in v0.2).")"
write_file "src/hpc_oda_commons/adapters/xdmod/adapter.py" "$(py_stub "Skeleton SourceAdapter for XDMoD job summaries (stub in v0.1).")"
write_file "src/hpc_oda_commons/adapters/xdmod/README.md" "$(md_stub "XDMoD Adapter" "Planned approach, required inputs, and mapping notes.")"

# models
write_file "src/hpc_oda_commons/models/__init__.py" "$(py_stub "Official baseline model plugins shipped with the package.")"
write_file "src/hpc_oda_commons/models/job_failure_baseline/__init__.py" "$(py_stub "Baseline model package for SLURM job failure prediction (v0.1).")"
write_file "src/hpc_oda_commons/models/job_failure_baseline/model.py" "$(py_stub "ModelPlugin implementation: train/infer for job failure baseline.")"
write_file "src/hpc_oda_commons/models/job_failure_baseline/features.py" "$(py_stub "Feature extraction from oda.job tables for the baseline model.")"
write_file "src/hpc_oda_commons/models/job_failure_baseline/calibrate.py" "$(py_stub "Optional threshold calibration utilities for classification.")"
write_file "src/hpc_oda_commons/models/job_failure_baseline/explain.py" "$(py_stub "Simple explanations: feature importances or coefficients extraction.")"
write_file "src/hpc_oda_commons/models/job_failure_baseline/README.md" "$(md_stub "Job Failure Baseline Model" "Model scope, assumptions, expected schema inputs/outputs, usage.")"

# tools
write_file "src/hpc_oda_commons/tools/__init__.py" "$(py_stub "Utility tools that aren’t models (feature helpers, reporting).")"
write_file "src/hpc_oda_commons/tools/featurize/__init__.py" "$(py_stub "Feature engineering helper subpackage.")"
write_file "src/hpc_oda_commons/tools/featurize/job_features.py" "$(py_stub "Shared job-level feature computations reusable across models.")"
write_file "src/hpc_oda_commons/tools/report/__init__.py" "$(py_stub "Report generation utilities.")"
write_file "src/hpc_oda_commons/tools/report/html.py" "$(py_stub "Lightweight HTML report builder for local results.")"

# benchmark
write_file "src/hpc_oda_commons/benchmark/__init__.py" "$(py_stub "Benchmark APIs (Compare pillar): recipes, runner, metrics, result bundles.")"
write_file "src/hpc_oda_commons/benchmark/recipe_schema.json" "$(json_stub "JSON Schema for benchmark recipes (placeholder; consider moving to /schemas).")"
write_file "src/hpc_oda_commons/benchmark/recipe.py" "$(py_stub "Recipe dataclass and YAML/TOML parsing for benchmark recipes.")"
write_file "src/hpc_oda_commons/benchmark/runner.py" "$(py_stub "Benchmark orchestration: load data → run model → metrics → write result bundle.")"
write_file "src/hpc_oda_commons/benchmark/metrics/__init__.py" "$(py_stub "Metric registry and metric implementations.")"
write_file "src/hpc_oda_commons/benchmark/metrics/classification.py" "$(py_stub "Classification metrics implementations (F1, precision, recall, AUROC).")"
write_file "src/hpc_oda_commons/benchmark/metrics/mdl.py" "$(py_stub "Minimal Metric Definition Language (MDL) parsing/validation.")"
write_file "src/hpc_oda_commons/benchmark/environment.py" "$(py_stub "Environment capture (pip/conda), hashing, and reproducibility metadata.")"
write_file "src/hpc_oda_commons/benchmark/results.py" "$(py_stub "Result bundle schema helpers and readers/writers.")"

# qst (CLI)
write_file "src/hpc_oda_commons/qst/__init__.py" "$(py_stub "Quickstart Toolkit entry points (Run pillar).")"
write_file "src/hpc_oda_commons/qst/cli.py" "$(py_stub "Root CLI app definition and subcommand registration (typer/rich recommended).")"
write_file "src/hpc_oda_commons/qst/config.py" "$(py_stub "Project config model (hpc-oda.toml) and defaults.")"
write_file "src/hpc_oda_commons/qst/project.py" "$(py_stub "Project init/layout, state dir (.hpc_oda) management.")"
write_file "src/hpc_oda_commons/qst/commands/__init__.py" "$(py_stub "CLI command implementations package.")"
write_file "src/hpc_oda_commons/qst/commands/init.py" "$(py_stub "Implements `hpc-oda init` project bootstrap.")"
write_file "src/hpc_oda_commons/qst/commands/browse.py" "$(py_stub "Implements `hpc-oda browse` (Find pillar via registry snapshot).")"
write_file "src/hpc_oda_commons/qst/commands/info.py" "$(py_stub "Implements `hpc-oda info` for adapters/models/recipes metadata display.")"
write_file "src/hpc_oda_commons/qst/commands/ingest.py" "$(py_stub "Implements `hpc-oda ingest ...` (v0.1: slurmctld).")"
write_file "src/hpc_oda_commons/qst/commands/validate.py" "$(py_stub "Implements `hpc-oda validate ...` schema + quality checks.")"
write_file "src/hpc_oda_commons/qst/commands/run_baseline.py" "$(py_stub "Implements `hpc-oda run-baseline` using included synthetic dataset.")"
write_file "src/hpc_oda_commons/qst/commands/run_model.py" "$(py_stub "Implements `hpc-oda run model ...` on ingested local data.")"
write_file "src/hpc_oda_commons/qst/commands/benchmark.py" "$(py_stub "Implements `hpc-oda benchmark ...` from recipes (Compare pillar).")"
write_file "src/hpc_oda_commons/qst/commands/registry_update.py" "$(py_stub "Implements `hpc-oda registry update` (optional network use).")"
write_file "src/hpc_oda_commons/qst/tui/__init__.py" "$(py_stub "Optional terminal UI helpers (tables/progress prompts).")"
write_file "src/hpc_oda_commons/qst/tui/render.py" "$(py_stub "Pretty rendering helpers (rich) for CLI output.")"

# viz (optional extras)
write_file "src/hpc_oda_commons/viz/__init__.py" "$(py_stub "Optional visualization entry points (install via extras).")"
write_file "src/hpc_oda_commons/viz/app.py" "$(py_stub "Minimal dashboard app launcher (streamlit/dash placeholder).")"
write_file "src/hpc_oda_commons/viz/panels.py" "$(py_stub "Common visualization panels: quality, metrics, feature importance.")"

# utils
write_file "src/hpc_oda_commons/utils/__init__.py" "$(py_stub "Small shared helpers (keep lean; avoid dumping ground).")"
write_file "src/hpc_oda_commons/utils/io.py" "$(py_stub "Small IO helpers not covered by core/artifacts.")"
write_file "src/hpc_oda_commons/utils/time.py" "$(py_stub "Timestamp parsing/binning helpers.")"
write_file "src/hpc_oda_commons/utils/logging.py" "$(py_stub "Standard logger configuration for library + CLI.")"

# -------- schemas --------
write_file "schemas/README.md" "$(md_stub "Schemas" "How schema versioning works and how to submit SERs for changes.")"
write_file "schemas/oda/job/v0.1.0.json" "$(json_stub "Core ODA schema for v0.1 vertical slice (SLURM job failure prediction). Replace with real JSON Schema.")"
write_file "schemas/oda/result/v0.1.0.json" "$(json_stub "Result bundle schema (leaderboard reads these bundles). Replace with real JSON Schema.")"
write_file "schemas/oda/registry/v0.1.0.json" "$(json_stub "Registry metadata schema for adapters/models/tools/recipes snapshot. Replace with real JSON Schema.")"

# -------- registry snapshot --------
write_file "registry/snapshot.json" "$(json_stub "Curated offline index of adapters/models/recipes for Find pillar. Populate via scripts/build_registry_snapshot.py.")"
write_file "registry/snapshot.sig" "PLACEHOLDER SIGNATURE\n# Optional signature/checksum for registry snapshot integrity.\n"
write_file "registry/README.md" "$(md_stub "Registry" "How the registry snapshot is generated, validated, and updated.")"

# -------- recipes --------
write_file "recipes/README.md" "$(md_stub "Benchmark Recipes" "Naming conventions, required fields, and MDL metric definitions.")"
write_file "recipes/job-failure/baseline_tiny.yml" "$(yml_stub "Fast CI recipe (tiny synthetic): baseline model on included dataset.")"
write_file "recipes/job-failure/baseline_medium.yml" "$(yml_stub "Scheduled recipe (medium synthetic): baseline model for regression/perf checks.")"
write_file "recipes/job-failure/alt_model_example.yml" "$(yml_stub "Example recipe comparing a second model plugin against baseline.")"
write_file "recipes/common/metrics_mdl_examples.yml" "$(yml_stub "Examples of Metric Definition Language (MDL) for supported metrics.")"
write_file "recipes/common/envs/cpu.yml" "$(yml_stub "Conda environment for CPU-only benchmarking (pin versions later).")"
write_file "recipes/common/envs/minimal.txt" "# Minimal pip requirements for smoke tests (placeholder).\n"

# -------- datasets --------
write_file "datasets/README.md" "$(md_stub "Datasets" "Dataset policy: prefer manifests + external hosting pointers; include only tiny synthetic in-repo.")"
write_file "datasets/synthetic/job-failure/tiny/data.parquet" "PLACEHOLDER PARQUET\n# Replace with a real Parquet file generated by datasets/synthetic/job-failure/generator.py.\n"
write_file "datasets/synthetic/job-failure/tiny/manifest.json" "$(json_stub "Manifest describing the tiny synthetic dataset (schema version, generation params, hashes).")"
write_file "datasets/synthetic/job-failure/generator.py" "$(py_stub "Synthetic data generator for v0.1 job-failure datasets (tiny/medium).")"
write_file "datasets/synthetic/shared/schema_examples.jsonl" "{\"_comment\":\"Example JSONL records illustrating schema fields (replace with real examples).\"}\n"
write_file "datasets/external/zenodo_links.yml" "$(yml_stub "Pointers to externally hosted datasets (Zenodo URLs/DOIs + checksums).")"
write_file "datasets/external/golden_datasets.yml" "$(yml_stub "Curated golden dataset references (if any) for v0.1 benchmarks.")"

# -------- leaderboard --------
write_file "leaderboard/README.md" "$(md_stub "Leaderboard" "How leaderboard artifacts are generated from result bundles and published.")"
write_file "leaderboard/generate.py" "$(py_stub "Collect result bundles and generate leaderboard.json + static HTML (GitHub Pages).")"
write_file "leaderboard/templates/index.html.j2" "$(jinja_stub "Jinja2 template for static leaderboard HTML.")"
write_file "leaderboard/templates/style.css" "$(css_stub "Minimal styling for static leaderboard pages.")"
write_file "leaderboard/public/leaderboard.json" "$(json_stub "Machine-readable leaderboard output (generated).")"
write_file "leaderboard/public/index.html" "$(html_stub "Human-readable static leaderboard page (generated).")"
write_file "leaderboard/public/assets/.gitkeep" "# Placeholder for leaderboard static assets.\n"

# -------- containers --------
write_file "containers/README.md" "$(md_stub "Containers" "How to run in containers on HPC (Docker/Apptainer), including reproducibility notes.")"
write_file "containers/Dockerfile" "$(docker_stub "Container recipe for reproducible environments (placeholder).")"
write_file "containers/apptainer.def" "$(apptainer_stub "Apptainer/Singularity definition for HPC sites (placeholder).")"
write_file "containers/env/environment.yml" "$(yml_stub "Conda env for container builds (pin later).")"
write_file "containers/env/constraints.txt" "# Pinned constraints for reproducibility (placeholder).\n"

# -------- scripts --------
write_file "scripts/build_registry_snapshot.py" "$(py_stub "Build registry snapshot JSON from official plugins + recipes; validate against registry schema.")"
write_file "scripts/validate_recipes.py" "$(py_stub "Validate recipes and MDL constraints (pre-commit/CI).")"
write_file "scripts/validate_schemas.py" "$(py_stub "Schema sanity checks: required metadata, examples, compatibility rules.")"
write_file "scripts/release_checklist.md" "$(md_stub "Release Checklist" "Human steps not automated by CI (verify docs, tag, announce, etc.).")"
write_file "scripts/dev_bootstrap.sh" "$(sh_stub "Developer bootstrap: create venv, install dev extras, run pre-commit (placeholder).")"

# -------- examples --------
write_file "examples/README.md" "$(md_stub "Examples" "Overview of notebooks and sample projects included for learning/testing.")"
write_file "examples/notebooks/00_quickstart.ipynb" "$(ipynb_stub "Walkthrough: init → run-baseline → ingest → validate → run.")"
write_file "examples/notebooks/01_slurmctld_ingest.ipynb" "$(ipynb_stub "Deep dive: parsing, mapping, transformations for slurmctld ingestion.")"
write_file "examples/notebooks/02_benchmark_compare.ipynb" "$(ipynb_stub "Compare models via benchmark recipes and inspect result bundles.")"
write_file "examples/projects/sample_project/hpc-oda.toml" "$(toml_stub "Example project config generated by `hpc-oda init`.")"
write_file "examples/projects/sample_project/README.md" "$(md_stub "Sample Project" "How to use the sample project directory and run commands end-to-end.")"

# -------- tests --------
write_file "tests/README.md" "$(md_stub "Tests" "Test strategy: unit vs integration vs golden-path checks in CI.")"
write_file "tests/conftest.py" "$(py_stub "Shared pytest fixtures for unit/integration tests.")"

write_file "tests/unit/test_schema_loader.py" "$(py_stub "Unit tests for schema loader and schema ID parsing.")"
write_file "tests/unit/test_validator.py" "$(py_stub "Unit tests for schema validation and data quality rules.")"
write_file "tests/unit/test_registry.py" "$(py_stub "Unit tests for registry snapshot loading and filtering/search.")"
write_file "tests/unit/test_recipe_parsing.py" "$(py_stub "Unit tests for recipe parsing and MDL validation.")"
write_file "tests/unit/test_result_bundle.py" "$(py_stub "Unit tests for result bundle schema and I/O.")"
write_file "tests/unit/test_security_policy.py" "$(py_stub "Unit tests for transformation policy behavior and ledgers.")"
write_file "tests/unit/test_plugins_entrypoints.py" "$(py_stub "Unit tests for plugin discovery via entry points.")"

write_file "tests/integration/test_cli_golden_path.py" "$(py_stub "Integration test: init → run-baseline → ingest → validate → run (golden path).")"
write_file "tests/integration/test_slurmctld_ingest.py" "$(py_stub "Integration test: parse fixture slurmctld log and produce schema-valid outputs.")"
write_file "tests/integration/test_benchmark_smoke.py" "$(py_stub "Integration test: run baseline_tiny recipe and validate outputs.")"

write_file "tests/fixtures/slurmctld.log" "# Fixture slurmctld log snippet for parser tests (replace with representative sample lines).\n"
write_file "tests/fixtures/expected_job_table.parquet" "PLACEHOLDER PARQUET\n# Replace with real expected Parquet output for regression testing.\n"
write_file "tests/fixtures/expected_manifest.json" "$(json_stub "Expected manifest output for fixture ingestion (ignore volatile fields in assertions).")"
write_file "tests/fixtures/recipes/baseline_tiny.yml" "$(yml_stub "Fixture recipe used by integration tests (baseline_tiny).")"

# -------- .devcontainer --------
write_file ".devcontainer/devcontainer.json" "$(json_stub "VSCode devcontainer configuration (optional).")"
write_file ".devcontainer/Dockerfile" "$(docker_stub "Devcontainer image (separate from runtime container; optional).")"

echo
echo "Done. Repo scaffold created at: ${ROOT}"
echo "NOTE: Files like *.parquet are placeholders (text) and must be replaced with real binary Parquet outputs."

