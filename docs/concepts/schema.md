# Schema

The v0.1 vertical slice uses versioned JSON Schemas to define canonical artifacts:
1. ODA job tables: `oda.job.v0.1.0`
2. Result bundles: `oda.result.v0.1.0`
3. Registry snapshot: `oda.registry.v0.1.0`

## Versioning
Schema IDs follow the pattern: `oda.<name>.v<MAJOR>.<MINOR>.<PATCH>`.
1. PATCH: backwards compatible clarifications.
2. MINOR: additive changes only.
3. MAJOR: breaking changes.

## Schema Evolution Requests (SER)
Schema changes are proposed through a Schema Evolution Request (SER).
1. Create an issue using the SER template.
2. Describe the change, compatibility impact, and migration plan.
3. Update schema files and add a migration note if required.

During v0.1 the core job schema is treated as frozen except for non-breaking fixes.
