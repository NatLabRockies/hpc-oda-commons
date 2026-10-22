# Add a Model

Models are in-repo Python classes, one folder each under `src/hpc_oda_commons/models/`. The
registry, the model cards and the benchmark's recipes are all generated from that folder and
the tables below, so a new model needs no hand-written registry entry.

## Minimal Steps

1. **The class.** Write it in `src/hpc_oda_commons/models/<name>/model.py`. Name the folder
   for the model's method, not a task: its id is `model.<name>`, and recipes choose what it
   predicts.
2. **`model.yml`** beside it: `name` (the title), `version`, `object` (the class name) and a
   `description` of the method. Describe only the method: what the model is used for, its
   dependencies and its scores are derived from its recipes, its imports and its results.
   [`models/baseline/model.yml`](../../src/hpc_oda_commons/models/baseline/model.yml) is an
   example.
3. **A runner.** Add an entry to `RUNNERS` in `src/hpc_oda_commons/benchmark/runner.py` for
   each split method the model supports, naming the runner function and the config dataclass
   it builds. The model card's "How it runs" section is generated from this table.
4. **A bundled recipe.** Add at least one under `src/hpc_oda_commons/recipes/job-runtime/` or
   `job-power/`. The registry takes the model's tasks from its recipes and refuses a model
   with none.
5. **The benchmark.** To run it on the published datasets and in `hpc-oda recipes write`:
   - runtime: add its name to `RUNTIME_MODELS` in
     `src/hpc_oda_commons/benchmarking/hpc/matrix.py`;
   - power: add `recipes/job-power/<name>_rolling_{avg,peak}.yml` (copy another model's;
     `recipes write` copies these for your dataset), and the Eagle, Kestrel and PM100
     variants to run it there.
6. **Tests** that exercise the model's public API (e.g. `fit()`/`predict()` for simple
   models, or `evaluate()` for rolling-window models), and add a rolling model to
   `tests/unit/test_power_targets.py` (below).
7. **The card.** Run `hpc-oda models cards` and commit `docs/models/<name>.md`. A unit test
   fails until you do.

## Feature eligibility

Runtime models may only use **submission-time** columns. The shared allowlist lives in
`models/feature_policy.py` (`RUNTIME_PREDICTION_FEATURE_FIELDS`); `RollingTabularModel`
and the TF-IDF kNN vectorizer both filter through it, and the embedding serializer enforces
the same policy with its own `FORBIDDEN_FIELDS` guard. A model that picks its own columns
must filter through the allowlist too — a normalized table can carry `job_state`,
`exit_code`, or `*_alloc` columns, none of which exist when the job is queued.

Admit a dataset-specific column with `extra_feature_fields` on the model config rather than
by widening the shared allowlist, unless the field is genuinely cross-site.

Build the feature set with `feature_allowlist(extra, target=...)` rather than the raw
`RUNTIME_PREDICTION_FEATURE_FIELDS` set: it guarantees the model's own target is never a
feature, and rejects a config that names it as an extra.

## Targets

A model predicts the column the recipe's metrics name (#204), `runtime_seconds` by default.
To support that:

1. Give the config a `target_field: str = "runtime_seconds"` and set `self.target_field`
   from it. Read the target only through `self.target_field`, never a literal column name.
2. In the runner, pass `target_field=_target_for(metric_defs)` when building the config, and
   go through `_run_rolling_model_evaluate`, which checks the recipe's target against
   `model.target_field` before evaluating.
3. A model that can only predict one column (like the fixed UoPC adaptation) calls
   `_require_target(<its column>, metric_defs, model=...)` instead, so a recipe naming any
   other target fails rather than reporting this column's errors under that name.

`tests/unit/test_power_targets.py` runs every rolling runner on a power target whose values
cannot be confused with runtime; add a new rolling model to its `RUNNERS`.

## Reference Implementations

The [model cards](../models/README.md) list every model; each card links to its source. Good
starting points:

- **Simplest:** `models/baseline/`, a `fit()`/`predict()` class whose rolling loop lives in
  the runner.
- **A rolling tabular regressor:** subclass `RollingTabularModel` in
  `models/rolling_tabular/base.py`. XGBoost, random forest and MLP share that base and differ
  only in the estimator they plug in; MoE XGBoost and the signature memorizer override its
  fit/predict seam.
- **Fully custom rolling state:** `models/tfidf_knn/`, or `models/embedding_knn/` for a model
  that reads a precomputed embedding.
- **More than one protocol:** `models/uopc/` runs under a fixed split, the UoPC paper's date
  cutoff, and the shared rolling windows.

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
