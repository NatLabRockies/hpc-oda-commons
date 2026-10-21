## Summary

Describe what this change does and why.

## Scope

- [ ] Feature (`feat/*`)
- [ ] Fix (`fix/*`)
- [ ] Chore (`chore/*`)

## DoD Gates Impact

- [ ] DoD-1 (install + `hpc-oda --help`) unaffected or updated tests accordingly
- [ ] DoD-2 (`run-baseline` offline result bundle) unaffected or updated tests accordingly
- [ ] DoD-3 (slurmctld ingest → schema-valid Parquet + manifest) unaffected or updated tests accordingly
- [ ] DoD-4 (benchmark `hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml` → metrics + provenance) unaffected or updated tests accordingly
- [ ] DoD-5 (datasets `prepare` → schema-valid table → benchmark) unaffected or updated tests accordingly

## Checklist

- [ ] `ruff format . --check` passes
- [ ] `ruff check .` passes
- [ ] `python scripts/validate_recipes.py` passes
- [ ] `make test` passes
- [ ] `HPC_ODA_OFFLINE=1 make test-integration` passes
- [ ] Generated pages regenerated if their sources changed (`make docs-cli`,
      `hpc-oda models cards`, `hpc-oda datasets cards`; see CONTRIBUTING.md)
- [ ] Docs updated if CLI behavior or output paths changed (docs/how-to/quickstart.md,
      docs/agent-usage.md)
- [ ] No sensitive data committed (no real logs, credentials, tokens)
- [ ] Any new files are properly added to packaging (schemas/recipes/registry/datasets)

## Notes for Reviewers

Anything tricky? Any follow-ups?