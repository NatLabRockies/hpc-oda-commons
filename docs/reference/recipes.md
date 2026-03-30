# Recipes Reference

## Built-in Recipes (v0.1)

| Recipe | Model | Split | Purpose |
|--------|-------|-------|---------|
| `baseline_tiny.yml` | Baseline (mean predictor) | Fixed 80/20 | CI smoke tests, offline demos |
| `xgb_hourly_recent.yml` | XGBoost | Rolling hourly (1000h, 100d) | Full XGBoost benchmark |
| `alt_model_example.yml` | XGBoost | Rolling hourly (24h, 30d) | Alternate config example |

Recipes are located at `src/hpc_oda_commons/recipes/job-runtime/` and bundled with the package.

## Recipe Schema (`oda.recipe.v0.1.0`)

Recipes are YAML files validated against `oda.recipe.v0.1.0`. Metric definitions use the Metric Definition Language (MDL) schema `oda.mdl.v0.1.0`.

### Annotated Example

```yaml
# Unique identifier for this recipe
recipe_id: recipe.job_runtime.baseline_tiny

# Problem domain(s) this recipe targets
problem_domain:
  - job-runtime-prediction

# Input data schema version required
schema_version: oda.job.v0.1.0

# Dataset to evaluate against
dataset:
  id: hpc_oda_commons/datasets/synthetic/job-runtime/tiny
  table_path: hpc_oda_commons/datasets/synthetic/job-runtime/tiny/data.parquet
  manifest_path: hpc_oda_commons/datasets/synthetic/job-runtime/tiny/manifest.json

# Model to evaluate
model:
  id: model.job_runtime_baseline
  version: "0.1.0"

# Metrics to compute (v0.1 requires at least mae and rmse)
metrics:
  - name: mae
    target: runtime_seconds
  - name: rmse
    target: runtime_seconds

# Train/test split strategy
split:
  method: fixed          # or "rolling_hourly"
  train_fraction: 0.8    # for fixed splits only
  seed: 42               # for fixed splits only

# Output configuration
run:
  output_dir: runs
  overwrite: false
```

### Split Methods

**`fixed`** -- Random train/test split. Used with `model.job_runtime_baseline`.
- `train_fraction` (float, required): fraction of data for training (e.g., `0.8`)
- `seed` (int, required): random seed for reproducibility

**`rolling_hourly`** -- Sliding hourly windows that simulate production retraining. Used with `model.job_runtime_xgboost`.
- `n_recent_hours` (int, required): number of hourly windows to evaluate
- `training_lookback_days` (int, default `100`): days of history per training window

### Validation Rules
- `metrics` must include at least `mae` and `rmse`
- All metrics must target the same field (e.g., `runtime_seconds`)
- For `rolling_hourly`, `n_recent_hours` must be positive
