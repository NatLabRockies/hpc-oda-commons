# Benchmark Recipes

Recipes define reproducible benchmark runs for v0.1.

## Requirements (v0.1)

Recipes must conform to:
1. `oda.recipe.v0.1.0`
2. metric definitions in `oda.mdl.v0.1.0`

Required fields:
1. `recipe_id`
2. `problem_domain`
3. `schema_version`
4. `dataset` (with `id` + `table_path`)
5. `model` (with `id` + `version`)
6. `metrics` (must include `mae` and `rmse` for runtime prediction)

## Example

- `recipes/job-runtime/baseline_tiny.yml`
- `recipes/job-runtime/xgb_hourly_recent.yml`
