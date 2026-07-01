# Schema Versions

All schemas follow the naming convention `oda.<type>.v<MAJOR>.<MINOR>.<PATCH>` and are stored as JSON Schema (Draft 2020-12) files under `src/hpc_oda_commons/schemas/oda/`.

## Current: `oda.job.v0.2.0`

`oda.job.v0.2.0` is the current canonical job schema. It is the version emitted
by ingestion and required by the bundled recipes.

| Schema ID | Purpose | Key Required Fields |
|-----------|---------|---------------------|
| `oda.job.v0.2.0` | Canonical HPC job record | `job_id`, `start_time`, `end_time`, `runtime_seconds` |

The optional `submit_time` field is also part of the schema (used by rolling
splits). The job schema uses `additionalProperties: true`, so sites can include
extra columns without breaking validation.

In v0.2.0 the timestamp columns (`start_time`, `end_time`, and the optional
`submit_time`) are stored as **native Arrow `timestamp(us, tz=UTC)`**, not as
ISO-8601 strings. The v0.2.0 JSON Schema therefore gives these fields no
`type`/`format`; instead their column type is validated **structurally** by
`collect_job_table_type_issues` (in `src/hpc_oda_commons/schema/validator.py`).
Validation rejects legacy v0.1.0 string timestamp tables against the v0.2.0
schema.

## v0.1.0

`oda.job.v0.1.0` is retained as **legacy only** (its timestamp columns are
ISO-8601 strings). All other schema types remain at v0.1.0.

| Schema ID | Purpose | Key Required Fields |
|-----------|---------|---------------------|
| `oda.job.v0.1.0` | Canonical HPC job record (legacy, string timestamps) | `job_id`, `start_time`, `end_time`, `runtime_seconds` |
| `oda.result.v0.1.0` | Benchmark result output | `schema_version`, `recipe_id`, `problem_domain`, `created_at`, `metrics`, `provenance` |
| `oda.manifest.v0.1.0` | Data artifact lineage | `schema_version`, `created_at`, `input_schema_version`, `artifact`, `provenance` |
| `oda.mapping.v0.1.0` | Field mapping specification | `schema_version`, `kind`, `output_schema_version`, `fields` |
| `oda.recipe.v0.1.0` | Benchmark recipe definition | `recipe_id`, `problem_domain`, `schema_version`, `dataset`, `model`, `metrics`, `split` |
| `oda.mdl.v0.1.0` | Metric Definition Language | `name` (mae, rmse, mape, r2, underprediction_ratio), `target` |
| `oda.registry.v0.1.0` | Registry entry catalogue | `id`, `entry_type`, `name`, `version`, `description`, `problem_domain` |

Schema IDs follow the pattern `oda.<type>.v<MAJOR>.<MINOR>.<PATCH>`. Schema files are stored as JSON Schema (Draft 2020-12) under `src/hpc_oda_commons/schemas/oda/`.
