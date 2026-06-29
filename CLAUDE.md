# Agent Guide

Instructions for AI agents working with hpc-oda-commons. (`AGENTS.md` is a
symlink to this file, so AGENTS-aware tools read the same guidance.)

**hpc-oda-commons** is a local-first CLI + standards toolkit for HPC Operational
Data Analytics (ODA), focused on SLURM job runtime prediction.

## First: establish intent

Are you **using** hpc-oda-commons (running it as a tool) or **developing** it
(changing its code)? Ask the user if it's unclear.

**Default to USING (read-only) until told otherwise.** Do not modify source,
create branches, open PRs, or push to any branch unless the user confirms they
are developing.

---

## If you are USING the tool

Follow **[`docs/agent-usage.md`](docs/agent-usage.md)** — installation, the
ingest → validate → benchmark → leaderboard workflow, the command reference, and
how to read results. Run CLI commands and interpret outputs; do not change code.

---

## If you are DEVELOPING the tool

You must follow the team's process and standards — these are enforced on `main`
(protected branch: required CI checks + review, no direct pushes):

- **[`CONTRIBUTING.md`](CONTRIBUTING.md)** — the workflow (issue → discuss →
  branch → small commits → green checks → PR → review → merge), the quality gate
  (Definition of Done), and coding standards. Read this before changing anything.
- **[`docs/architecture.md`](docs/architecture.md)** — data flow, package layout,
  and testing conventions.

Key guardrails:

- **Work from an agreed issue.** Non-trivial changes start with an issue and a
  plan that's been discussed; don't start coding against an unreviewed plan.
- **Never push to `main`.** Develop on a branch named `fix/…-<issue>` /
  `feat/…-<issue>` / `chore/…-<issue>` and land via PR (`Closes #<issue>`).
- **Run the full gate before pushing** — `ruff format . --check`, `ruff check .`,
  `make test`, and `HPC_ODA_OFFLINE=1 make test-integration` (CI runs all four).
  `make lint` alone is not sufficient.
- **Known limitations** live in [`docs/known-issues.md`](docs/known-issues.md).

Personal, per-developer agent preferences may live in a gitignored
`.claude/CLAUDE.md`, but anything that should bind the team belongs in the
tracked docs above.
