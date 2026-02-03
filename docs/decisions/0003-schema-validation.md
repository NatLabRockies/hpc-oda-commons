# ADR 0003 — Schema Strategy and Validation Approach for v0.1

**Status:** Accepted  
**Date:** 2026-02-03  
**Scope:** v0.1 vertical slice (SLURM job runtime prediction)

## Context

A core goal of hpc-oda-commons is standardization and comparability.  
This requires:
- a versioned schema for operational data artifacts
- reproducible validation of ingested datasets and result bundles
- a clear path for schema evolution (SER later)

We need a schema approach that is:
- tool-friendly
- language-agnostic
- easy to validate automatically
- compatible with being versioned and stored in-repo

## Decision

For v0.1:

1. **Primary schema format is JSON Schema**, stored on disk under `schemas/`.
2. Validation is performed in Python using **jsonschema** (or equivalent JSON Schema validator).
3. **Pydantic models are deferred** in v0.1 and may be introduced later as an optional developer convenience, not as the canonical schema.

## Rationale

- JSON Schema is widely supported and can be versioned and validated consistently.
- It encourages cross-language compatibility and long-term ecosystem growth.
- Keeping the canonical definition as JSON Schema avoids coupling “the schema” to a Python-only representation.
- Deferring Pydantic reduces v0.1 complexity and prevents duplication of schema definitions.

## Consequences

- v0.1 will include:
  - `schemas/oda/job/v0.1.0.json` (job schema sufficient for runtime prediction)
  - `schemas/oda/result/v0.1.0.json` (result bundle schema)
  - `schemas/oda/registry/v0.1.0.json` (registry snapshot schema)
- The code will provide:
  - schema loading by ID/version
  - validation with helpful error messages
  - minimal semantic checks beyond JSON Schema where needed (e.g., start_time <= end_time)

## Revisit Criteria

Revisit in v0.2+ if:
- developers need stronger internal typing guarantees (Pydantic may be added)
- schema complexity grows enough to benefit from codegen or additional tooling
- multiple language implementations require additional schema packaging formats
