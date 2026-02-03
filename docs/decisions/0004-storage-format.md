# ADR 0004 — Canonical Storage Format for ODA Tables in v0.1

**Status:** Accepted  
**Date:** 2026-02-03  
**Scope:** v0.1 vertical slice (SLURM job runtime prediction)

## Context

Operational datasets can be large, and we want:
- a standard artifact format for datasets and intermediate tables
- efficient IO and storage
- compatibility with data science workflows
- portability across HPC sites

v0.1 needs a canonical format for:
- ingested job tables
- tiny synthetic dataset artifacts
- fixture/expected outputs used in tests (as appropriate)

## Decision

For v0.1:

- The canonical table artifact format is **Parquet**.
- Parquet read/write will be implemented using **PyArrow**.
- Pandas support may be used as a convenience layer but is not required as the canonical representation.

## Rationale

- Parquet is columnar, compressed, and broadly supported.
- PyArrow is the reference-quality implementation and aligns with Parquet as a standard.
- Parquet works well for both small synthetic datasets and larger real datasets.

## Consequences

- Ingest outputs and benchmark inputs will use Parquet by default.
- Tests should avoid committing large Parquet files; only a tiny artifact may be committed for offline workflows if desired.
- Where feasible, tests should generate Parquet artifacts on the fly from fixtures to reduce binary files in git.

## Revisit Criteria

Revisit in v0.2+ if:
- Arrow IPC or other formats provide meaningful advantages for specific workflows
- constraints from HPC environments limit PyArrow availability (rare, but possible)
