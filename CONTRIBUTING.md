# Contributing

This document describes how we plan, build, and merge changes to
hpc-oda-commons. The goal is a lightweight, traceable process that keeps `main`
green and every change tied to a discussed plan.

## TL;DR

Issue (with subtasks) → discuss → branch → small tagged commits → green checks →
PR → review → merge. One issue per unit of work; everything references the issue.

---

## 1. Development environment

```bash
pip install -e ".[dev]"
```

| Command | What it runs |
|---------|--------------|
| `make test` | Unit tests (fast) |
| `make test-integration` | Integration tests (requires `HPC_ODA_OFFLINE=1`) |
| `make lint` | `ruff check .` |
| `make format` | `ruff format .` then `ruff check . --fix` |

CI additionally runs `ruff format . --check` (the formatter, not just the
linter) and the unit suite on multiple Python versions, so see the quality gate
in §6 before pushing.

---

## 2. Workflow

### 2.1 Open an issue

Every change starts with an issue that describes **what** is changing and
**why**. Break the work into **subtasks** as a GitHub task list so progress
tracks automatically:

```markdown
- [ ] Subtask A — …
- [ ] Subtask B — …
```

For large or ambiguous work (architecture changes, anything affecting
reproducibility or public schemas), include a short design note / RFC in the
issue *before* coding, so the approach — not just the intent — is agreed.

### 2.2 Discuss and get a go

The team reviews and discusses the plan on the issue. When the approach is
agreed, mark it ready to develop (a `ready-to-develop` label or an explicit
"go" comment) so it's unambiguous that branching can start.

Weekly sync-ups are for **prioritization** — deciding what to focus on — not for
plan approval. Plan correctness is settled on the issue (above) so work isn't
blocked waiting for a meeting.

### 2.3 Branch

Branch from up-to-date `main`, named by change type with the issue number:

```
fix/<topic>-<issue>      e.g. fix/partial-null-validation-8
feat/<topic>-<issue>     e.g. feat/recipe-output-dir-4
chore/<topic>-<issue>
```

### 2.4 Commit

- Keep commits **small and focused** — ideally one subtask per commit.
- Reference the subtask(s) in the commit so history maps back to the plan.
- Write clear messages: a concise imperative summary line, then a body
  explaining the *what* and *why* when it isn't obvious.

### 2.5 Open a PR

Open a PR when development is finished, referencing the issue and using a
closing keyword so the merge auto-closes it:

```
Closes #8
```

The PR description is the running log of the change; you generally don't need a
comment-per-commit on the issue. Comment on the issue only for **decisions or
blockers** worth recording for watchers.

---

## 3. Merge strategy

Choose by how much commit granularity is worth keeping on `main`:

- **Rebase-merge (default)** — preserves the per-subtask commits while keeping
  `main` history linear. Use for multi-subtask PRs so §2.4's granularity
  survives.
- **Squash-merge** — collapses to one commit. Use only for single-commit fixes
  where the intermediate history adds nothing.
- **Merge commit** — reserve for branches that must preserve multiple authors'
  commits as-is (e.g. integrating someone else's work).

---

## 4. Quality gate (Definition of Done)

A change is "finished" (ready for PR) when **all** of the following hold:

- All issue subtasks are complete.
- Tests are added or updated for the change; behavioral changes update the
  relevant docs.
- All of these pass **locally**, matching CI:
  ```bash
  ruff format . --check
  ruff check .
  make test
  HPC_ODA_OFFLINE=1 make test-integration
  ```
- CI is **green** on the PR before merge.

Run the full set before pushing — `make lint` alone does **not** cover the
formatter check that CI enforces.

---

## 5. Code review and merge

- Changes merge via the protected `main` branch, and only with CI green (§4).
- **Contributors:** a PR needs one approving review before it can merge. You
  can't approve your own PR, so request a review — the maintainer is the default
  reviewer.
- **Maintainer:** as repository admin you may override the review requirement and
  merge your own PRs so solo/primary development isn't blocked. The override also
  bypasses the required-checks gate, so keep CI green when you use it.

Branch protection enforces this rather than relying on the honor system — see §7.

---

## 6. Code standards

- **No dead code or scaffolding** — every function is reachable from a
  user-facing entry point or a documented API. No placeholders or
  `NotImplementedError` stubs.
- **Single source of truth** — shared logic lives in one canonical module; don't
  duplicate across files.
- **Configuration integrity** — every config/recipe parameter must influence
  runtime behavior.
- **Proportional complexity** — match the solution's complexity to the problem.
- **No sensitive data** — never commit real site logs, paths, or credentials.
  Use synthetic/redacted fixtures only. Generated outputs (`data/`, `runs/`,
  `reports/`, root `recipes/`) are gitignored.
- **Ruff is the source of truth** for formatting and linting (line length 100,
  Python 3.9+).
- **Known limitations** are tracked in `docs/known-issues.md` and linked to
  their issue.

---

## 7. Branch protection (enforced on `main`)

`main` is a protected branch with these rules in effect:

- **Required status checks** must pass before merge: Lint (ruff), Unit tests
  (3.9 and 3.11), Golden-path integration.
- **Required review:** one approving review for contributors (non-admins).
- **No direct pushes:** changes land via PR.
- **Admin override:** repository admins (the maintainer) are exempt and may merge
  without a separate review, so primary development isn't blocked. The override
  also bypasses the required checks, so admins are expected to keep CI green (§4).

To change these rules, update the branch protection settings on `main`.
