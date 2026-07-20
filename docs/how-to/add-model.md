# Add a Model

In v0.1, models are implemented as in-repo Python classes and referenced by
registry metadata and recipes.

## Minimal Steps

1. Implement a model class under `src/hpc_oda_commons/models/`.
2. Add a registry entry in `src/hpc_oda_commons/registry/snapshot.json`.
3. Add a recipe in `src/hpc_oda_commons/recipes/`.
4. Add unit tests that exercise the model's public API (e.g., `fit()`/`predict()` for simple models, or `evaluate()` for rolling-window models).

## Required Metadata

The registry entry should include:
1. `id`
2. `name`
3. `version`
4. `problem_domain`
5. `input_schema_version`
6. `output_schema_version`
7. `supported_sources`

## Reference Implementations

The toolkit ships seven models, each illustrating a different complexity level:

| Model | Package | Interface |
|-------|---------|-----------|
| `model.job_runtime_baseline` | `models/job_runtime_baseline/` | Simple `fit()`/`predict()` class, rolling loop in runner |
| `model.job_runtime_xgboost` | `models/job_runtime_xgboost/` | Thin subclass of `RollingTabularModel` (`models/rolling_tabular/`) with OHE+SVD preprocessing and daily cache |
| `model.job_runtime_random_forest` | `models/job_runtime_random_forest/` | Thin subclass of `RollingTabularModel` |
| `model.job_runtime_mlp` | `models/job_runtime_mlp/` | Thin subclass of `RollingTabularModel` |
| `model.job_runtime_tfidf_knn` | `models/job_runtime_tfidf_knn/` | `evaluate()` with TF-IDF vectorization; hashes once, scores window slices in parallel (`window_n_jobs`) |
| `model.job_runtime_embedding_knn` | `models/job_runtime_embedding_knn/` | `evaluate()` over a precomputed embedding column; selectable dense top-k backend (`backends.py`) |
| `model.job_power_uopc` | `models/job_power_uopc/` | Per-user kNN job-power model on a fixed split |

For a minimal starting point, see `models/job_runtime_baseline/`. For a new
rolling tabular regressor, subclass `RollingTabularModel` in
`models/rolling_tabular/base.py` -- the `xgboost`, `random_forest`, and `mlp`
models share that base and differ only in the estimator they plug in. For a
rolling-evaluation model with fully custom internal state, see
`models/job_runtime_tfidf_knn/`.

## Running Alternate Models

```bash
hpc-oda benchmark -v src/hpc_oda_commons/recipes/job-runtime/xgb_hourly_recent.yml
```

For faster local test cycles, copy the recipe and reduce the rolling window:

```yaml
split:
  method: rolling
  n_windows: 24
  test_window_hours: 6
  training_lookback_days: 30
```
