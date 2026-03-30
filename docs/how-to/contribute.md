# Contributing

## Development Setup

```bash
git clone <repo-url>
cd hpc-oda-commons
pip install -e ".[dev]"
```

## Running Tests

```bash
make test                        # Unit tests
HPC_ODA_OFFLINE=1 make test-integration  # Integration tests
pytest tests/unit/test_foo.py    # Single file
```

## Linting and Formatting

Ruff is the single source of truth for style. Run before committing:

```bash
make format     # Auto-format + fix import order
make lint       # Check for violations
make precommit  # Run all pre-commit hooks
```

## Branch Naming

- `feat/<topic>` -- new features
- `fix/<topic>` -- bug fixes
- `chore/<topic>` -- maintenance, docs, CI

## Contribution Paths

1. **Improve ingestion** -- enhance slurmctld parsing, add new adapters
2. **Add models** -- implement new prediction models ([guide](add-model.md))
3. **Add recipes** -- create benchmark recipes ([recipe format](../reference/recipes.md))
4. **Improve docs** -- expand guides, add examples

## Schema Changes

Schema changes require a Schema Evolution Request (SER) -- open an issue describing the compatibility impact and migration plan.

## What to Update When

If CLI commands or output paths change, update:
- `README.md`
- `docs/how-to/quickstart.md`
- `docs/reference/cli.md`
