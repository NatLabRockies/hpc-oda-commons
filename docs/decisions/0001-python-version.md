# ADR 0001 — Supported Python Version for v0.1

**Status:** Accepted  
**Date:** 2026-02-03  
**Scope:** v0.1 vertical slice (SLURM job runtime prediction)

## Context

hpc-oda-commons targets HPC environments where Python availability varies across sites.  
The v0.1 release must run on common login nodes and developer workstations without requiring unusually new system Python installations.

We also want:
- reasonable typing support
- stable third-party library compatibility (PyArrow, jsonschema, typer/rich, etc.)
- a low-friction install experience

## Decision

For v0.1, the project will support:

- **Python `>=3.9`**

This is recorded in:
- `pyproject.toml` → `requires-python = ">=3.9"`

## Rationale

- Python 3.9 is commonly available on HPC systems (often via modules/conda) and is modern enough for strong typing and ecosystem compatibility.
- Avoids pushing sites to upgrade system Python.
- Keeps dependency choices broad and stable.

## Consequences

- Code should avoid features that require Python 3.10+ unless backported or optional.
- When reading TOML:
  - prefer stdlib `tomllib` when available (Python 3.11+)
  - provide a fallback dependency (`tomli`) for Python 3.9–3.10
- CI must test at least Python 3.9 and one newer version (e.g., 3.11) to ensure compatibility.

## Revisit Criteria

Revisit this decision in v0.2+ if:
- key dependencies require Python >=3.10
- HPC community baseline shifts to newer versions
- typing/modeling requirements materially benefit from 3.10+ features
