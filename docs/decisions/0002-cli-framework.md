# ADR 0002 — CLI Framework for v0.1

**Status:** Accepted  
**Date:** 2026-02-03  
**Scope:** v0.1 vertical slice (SLURM job runtime prediction)

## Context

The CLI is the primary user interface for v0.1. It must support the 10-minute workflow:

- `hpc-oda init`
- `hpc-oda browse`
- `hpc-oda info`
- `hpc-oda run-baseline` (offline)
- `hpc-oda ingest slurmctld ...`
- `hpc-oda validate ...`
- `hpc-oda benchmark ...`

We need:
- clear help text and subcommands
- nice tables/progress output
- simple implementation
- widely adopted libraries

## Decision

For v0.1:

- Use **Typer** for CLI command structure and argument parsing.
- Use **Rich** for terminal formatting (tables, progress, readable output).

The canonical entrypoint will be the `hpc-oda` console script defined in `pyproject.toml`.

## Rationale

- Typer provides a clean, modern developer experience and maps well to subcommand-driven CLIs.
- Rich significantly improves usability (tables and progress) with minimal code.
- Both are widely used and stable.

## Consequences

- CLI output should remain stable and predictable because it becomes part of the “golden path” tests and docs.
- Commands should be designed for non-interactive automation as well as interactive use.
- Any optional interactive flows must have non-interactive flags for CI and scripted usage.

## Revisit Criteria

Revisit in v0.2+ if:
- plugin-based command extension becomes a major requirement
- a different CLI framework is needed for advanced TUI features
