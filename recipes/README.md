# Benchmark Recipes

Recipes define reproducible benchmark runs for v0.1.

## Canonical Source

`recipes/` is the canonical source of truth.

Packaged copies under `src/hpc_oda_commons/recipes/` are synchronized from this
directory so installed wheels include built-in recipe assets.

Sync packaged copies from repo root:

`./.venv/bin/python scripts/sync_packaged_recipes.py`

Check drift only:

`./.venv/bin/python scripts/sync_packaged_recipes.py --check`

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
