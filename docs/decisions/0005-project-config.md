# ADR 0005 — Project Configuration Format for v0.1 (`hpc-oda.toml`)

**Status:** Superseded
**Date:** 2026-02-03  
**Scope:** v0.1 vertical slice (SLURM job runtime prediction)

## Context

The CLI needs a stable local project configuration format to support:
- ingestion configuration (paths, transforms, adapter parameters)
- default output locations
- selection of schema versions and recipes
- reproducible local runs

The configuration should be:
- human-editable
- stable and easy to validate
- friendly to both operators and researchers

## Decision

For v0.1:

- The project config file is **TOML** named **`hpc-oda.toml`**.

Parsing approach:
- Use `tomllib` when available (Python 3.11+).
- For Python 3.9–3.10, use `tomli` as a small dependency fallback.

## Rationale

- TOML is readable, supports nested structures cleanly, and is commonly used in Python tooling.
- `hpc-oda.toml` is explicit and avoids ambiguity with other project config files.

## Consequences

- `hpc-oda init` will create a default `hpc-oda.toml`.
- Code should define a minimal config schema/validation strategy (lightweight in v0.1).
- The config file becomes a stable user-facing interface and should be versioned carefully.

## Superseded

As of v0.1 cleanup, `hpc-oda.toml` was removed because it was written by `init` but never read by any code. Project-level configuration will be re-introduced end-to-end when a concrete use case requires it.
