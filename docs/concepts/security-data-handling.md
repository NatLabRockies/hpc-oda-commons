# Security & Data Handling

This project is **local-first**: ingestion and benchmarking are designed to run
without sending data off-cluster.

## Safe Transformation Policy (v0.1)

Before sharing artifacts, operators should apply explicit transformations to
sensitive fields. For v0.1 we support simple, deterministic helpers:

- `hash_identifier(value, salt=...)` — pseudonymize identifiers
- `bin_timestamp(value, interval_seconds=...)` — reduce timestamp precision
- `redact_value(value, replacement=...)` — remove or replace sensitive values

All transformations should be recorded in the manifest transformation ledger.

## Recommended Practice

- Keep raw logs private and ingest locally.
- Store only transformed/parquet outputs in shared artifacts.
- Record transformations in the manifest so downstream users can interpret data.
