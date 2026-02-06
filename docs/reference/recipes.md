# Recipes Reference

## Built-in Recipes (v0.1)
1. `hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml`
   Tiny synthetic runtime prediction benchmark (offline).

Bundled copy (for packaged installs):
`src/hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml`

## Recipe Schema (v0.1)

Recipes follow `oda.recipe.v0.1.0`. Metric definitions use the
Metric Definition Language (MDL) schema `oda.mdl.v0.1.0`.

Required fields in v0.1:
- `recipe_id`
- `problem_domain`
- `schema_version`
- `dataset` (with `id` + `table_path`)
- `model` (with `id` + `version`)
- `metrics` (must include `mae` and `rmse` for runtime prediction)
