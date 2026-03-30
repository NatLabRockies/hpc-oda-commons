# Schema Versions

All schemas follow the naming convention `oda.<type>.v<MAJOR>.<MINOR>.<PATCH>` and are stored as JSON Schema (Draft 2020-12) files under `src/hpc_oda_commons/schemas/oda/`.

## v0.1.0

| Schema ID | Purpose | Key Required Fields |
|-----------|---------|---------------------|
| `oda.job.v0.1.0` | Canonical HPC job record | `job_id`, `start_time`, `end_time`, `runtime_seconds` |
| `oda.result.v0.1.0` | Benchmark result output | `schema_version`, `recipe_id`, `problem_domain`, `created_at`, `metrics`, `provenance` |
| `oda.manifest.v0.1.0` | Data artifact lineage | `schema_version`, `created_at`, `input_schema_version`, `artifact`, `provenance` |
| `oda.mapping.v0.1.0` | Field mapping specification | `schema_version`, `kind`, `output_schema_version`, `fields` |
| `oda.recipe.v0.1.0` | Benchmark recipe definition | `recipe_id`, `problem_domain`, `schema_version`, `dataset`, `model`, `metrics`, `split` |
| `oda.mdl.v0.1.0` | Metric Definition Language | `name` (mae, rmse, mape, r2), `target` |
| `oda.registry.v0.1.0` | Registry entry catalogue | `id`, `entry_type`, `name`, `version`, `description`, `problem_domain` |

The job schema uses `additionalProperties: true`, so sites can include extra columns without breaking validation.

Schema IDs follow the pattern `oda.<type>.v<MAJOR>.<MINOR>.<PATCH>`. Schema files are stored as JSON Schema (Draft 2020-12) under `src/hpc_oda_commons/schemas/oda/`.
