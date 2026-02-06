# Add an Adapter

Adapters convert source logs or datasets into ODA schema-aligned rows.

## Minimal contract (v0.1)

Implement a class that satisfies the `SourceAdapter` protocol:

- `metadata`: `AdapterMetadata` with `id`, `name`, `version`, schema versions, and supported sources
- `parse(path: Path) -> list[dict[str, Any]]`

See `src/hpc_oda_commons/adapters/slurmctld/adapter.py` for a reference implementation.

## Safe transformations

If you transform sensitive fields, use the helpers in:

- `hpc_oda_commons.kernel.transformations`

Record each transformation in the manifest transformation ledger.
