# Add a Recipe

Recipes define reproducible benchmarks and must conform to:

- `oda.recipe.v0.1.0`
- metric definitions in `oda.mdl.v0.1.0`

See `recipes/job-runtime/baseline_tiny.yml` for a reference recipe.

Minimum required fields (v0.1):
- `recipe_id`
- `problem_domain`
- `schema_version`
- `dataset` (with `id` + `table_path`)
- `model` (with `id` + `version`)
- `metrics` (must include `mae` and `rmse` for runtime prediction)

Split notes (v0.1):
- `fixed` split requires `train_fraction` and `seed`
- `rolling_hourly` split requires `n_recent_hours` and accepts optional
  `training_lookback_days` (default `100`)
