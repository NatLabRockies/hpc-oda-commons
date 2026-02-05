# Contributing to hpc-oda-commons

Thanks for contributing! This project is building a community hub for HPC Operational Data Analytics with a v0.1 vertical slice focused on **SLURM job runtime prediction**.

This document defines contribution expectations and repo hygiene rules.

---

## 1) Branching and Merging

Even if you are a solo developer, use PR-style discipline so the repository stays OSS-ready.

### Branch naming convention
- `feat/<topic>` — new feature work
- `fix/<topic>` — bug fix
- `chore/<topic>` — maintenance, refactors, tooling

Examples:
- `feat/runtime-baseline-model`
- `fix/slurmctld-parser-timestamps`
- `chore/ci-speedups`

### Branch lifecycle
- Keep branches short-lived.
- Merge after each increment that moves a DoD gate forward.

### Treat merges like PRs
- Use the PR template checklist (see `.github/PULL_REQUEST_TEMPLATE.md`).
- Keep commits small and descriptive.

---

## 2) Local Development Setup

### Install
```bash
pip install -e ".[dev]"
```

### Enable pre-commit
```bash
pre-commit install
```

### Run checks
```bash
make lint
make test
make test-integration
```

###  Code Style and Quality
#### Formatting and linting
- Ruff is the single source of truth for formatting and linting.
- Pre-commit runs Ruff automatically.
- CI will reject code that fails Ruff checks.

#### Tests
- Add unit tests for new logic.
- Update or add integration tests when CLI behavior changes.
- Golden-path tests (DoD-1..DoD-4) must remain passing.

###  Docs in Sync with CLI (Hard Rule)

If you add, rename, or change a CLI command (or its output paths), you must update:
- README.md quickstart section
- docs/how-to/quickstart.md
- docs/reference/cli.md (if applicable)

CLI is the primary user interface for v0.1, so docs drift is considered a release blocker.

### Contributions Types (v0.1)
v0.1 is focused on runtime prediction, but contributions are welcome in these categories:
- slurmctld ingestion improvements (parser, mapping, validation)
- baseline runtime model improvements (deterministic, explainable, fast)
- benchmark recipes for runtime prediction
- schema clarifications (non-breaking during v0.1 freeze)
- documentation and examples

### Schema Evolution Requests (SER)
Schema changes are proposed via a Schema Evolution Request:
1. Open an issue using the SER template.
2. Describe compatibility impact and migration plan.
3. Update schema docs under `docs/concepts/schema.md`.

### Sensitive Data Policy
- Do not commit real site logs or sensitive data.
- Use synthetic or heavily redacted fixtures only.
- The repository assumes local-first processing; no uploads or telemetry in v0.1.
