# Tests

This document summarizes the test strategy for **hpc-oda-commons**.

## Test Types

- **Unit tests** (`tests/unit/`):
  - Run fast and validate individual modules (schemas, parsers, models, helpers).
  - Should be deterministic and avoid network access.
- **Integration tests** (`tests/integration/`):
  - Exercise CLI “golden paths” end-to-end (init → ingest → validate → benchmark → leaderboard).
  - Must run offline with `HPC_ODA_OFFLINE=1`.

## Fixture Hygiene

- **Do not rely on gitignored files** (e.g., `*.log`, `*.parquet`) for tests.
- Prefer generating small fixtures at runtime in `tmp_path` or via helpers in `tests/conftest.py`.
- If a binary fixture is required, explicitly allowlist it in `.gitignore` and commit it.

## Recommended Commands

- Fast unit suite:
  - `pytest -q tests/unit`
- Full suite:
  - `pytest -q`
- Offline integration:
  - `HPC_ODA_OFFLINE=1 pytest -q -m integration`

## Optional Native XGBoost Integration Lane

Some restricted sandboxes block OpenMP shared-memory primitives used by native
XGBoost builds. The native CLI XGBoost integration test is therefore opt-in.

- Run native XGBoost integration:
  - `HPC_ODA_ENABLE_NATIVE_XGBOOST_IT=1 HPC_ODA_OFFLINE=1 pytest -q -m integration -k native_cli`
