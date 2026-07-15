## Summary

Describe what this change does and why.

## Scope

- [ ] Feature (`feat/*`)
- [ ] Fix (`fix/*`)
- [ ] Chore (`chore/*`)

## DoD Gates Impact (v0.2 runtime prediction)

- [ ] DoD-1 (install + `hpc-oda --help`) unaffected or updated tests accordingly
- [ ] DoD-2 (`run-baseline` offline result bundle) unaffected or updated tests accordingly
- [ ] DoD-3 (slurmctld ingest → schema-valid Parquet + manifest) unaffected or updated tests accordingly
- [ ] DoD-4 (benchmark `hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml` → metrics + provenance) unaffected or updated tests accordingly
- [ ] DoD-5 (datasets `prepare` → schema-valid table → benchmark) unaffected or updated tests accordingly

## Checklist

- [ ] `ruff format . --check` passes
- [ ] `ruff check .` passes
- [ ] `make test` passes
- [ ] `HPC_ODA_OFFLINE=1 make test-integration` passes
- [ ] Docs updated if CLI behavior/output paths changed:
  - [ ] README quickstart
  - [ ] docs/how-to/quickstart.md
  - [ ] docs/reference/cli.md (if applicable)
- [ ] No sensitive data committed (no real logs, credentials, tokens)
- [ ] Any new files are properly added to packaging (schemas/recipes/registry/datasets)

## Notes for Reviewers

Anything tricky? Any follow-ups?