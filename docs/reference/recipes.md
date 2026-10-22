# Recipes Reference

A recipe is a YAML file that names one model, one dataset, the metrics and the split.
`hpc-oda benchmark <recipe>` runs it and writes a result bundle. Recipes are validated against
`oda.recipe.v0.1.0` ([recipe/v0.1.0.json](../../src/hpc_oda_commons/schemas/oda/recipe/v0.1.0.json)),
and each metric against `oda.mdl.v0.1.0`.

## Where recipes come from

- **For a dataset of your own,** `hpc-oda recipes write` writes every model's recipes on the
  benchmark's protocol. See [Benchmark your own data](../how-to/benchmark-your-data.md).
- **Bundled recipes** ship in `src/hpc_oda_commons/recipes/`: `job-runtime/` holds the runtime
  examples, and `job-power/` every power recipe, including the UoPC paper protocol.
  `hpc-oda browse --type recipe` lists them. Each [model card](../models/README.md) lists its
  model's recipes, and each [dataset card](../datasets/cards/README.md) the recipes that read
  its dataset.
- **By hand:** copy a bundled recipe and change it. A recipe can live anywhere on disk.

## An example

`job-runtime/baseline_tiny.yml`, the smoke-test recipe:

```yaml
recipe_id: recipe.job_runtime.baseline_tiny
problem_domain:
  - job-runtime-prediction
schema_version: oda.job.v0.2.0     # the input table's schema

dataset:
  id: hpc_oda_commons/datasets/synthetic/job-runtime/tiny
  table_path: hpc_oda_commons/datasets/synthetic/job-runtime/tiny/data.parquet
  manifest_path: hpc_oda_commons/datasets/synthetic/job-runtime/tiny/manifest.json

model:
  id: model.baseline
  version: "0.1.0"

metrics:                           # at least mae and rmse, all on one target column
  - name: mae
    target: runtime_seconds
  - name: rmse
    target: runtime_seconds

split:
  method: fixed
  train_fraction: 0.8
  seed: 42

run:
  output_dir: runs
  overwrite: false
```

## `dataset`

| Key | Meaning |
|---|---|
| `id` | The dataset's short name, such as `lassen`. Its registry id, `dataset.lassen`, is read the same way. The result names the dataset by the folder `table_path` is in. |
| `table_path` | The prepared table to read. |
| `manifest_path` | Optional: its manifest. |
| `window` | Optional: read only these days, `{start, end, by}`. `start` and `end` are inclusive UTC dates (`YYYY-MM-DD`). With `by: overlap` (the default), a job is read if its submit-to-end interval overlaps the days; with `by: submit`, if it was submitted in them. |
| `require_nonnull` | Optional: read only rows that have every one of these columns, such as a power target. |

`window` and `require_nonnull` filter the table as it is read, so a recipe can read a whole
prepared table without a sliced copy on disk. The result records the window it read. The
benchmark's power recipes declare theirs this way.

## `model`

`id` is the model's registry id, `model.<name>`, and `version` its version. The ids from before
#249 (such as `model.job_runtime_xgboost`) are still accepted and read as the new ones.
`hpc-oda browse --type model` lists the models.

## `metrics`

Each metric has a `name` and a `target`. The names are `mae`, `rmse`, `mape`, `r2` and
`underprediction_ratio`; every recipe needs `mae` and `rmse`. All metrics share one `target`,
and **that column is what the model predicts**: `runtime_seconds` for runtime, or a power column
such as `avgpcon_per_node`. A model that can't predict it fails the run
([Predict job power](../how-to/predict-power.md)).

## `split`

`method` is `fixed`, `rolling` or `cutoff`; without a `split`, the run uses `fixed`. Which
methods a model supports, the keys each reads and their defaults are on its
[model card](../models/README.md), under "How it runs". What the keys mean:

**`fixed`:** a deterministic train/test split.

- `train_fraction`: the share of rows used for training.
- `seed`: the random seed.

**`rolling`:** walk forward through time. Each test window holds the jobs submitted in it, and
the model trains on the jobs that ended in the lookback before it, as a model retrained in
production would ([Benchmarks](../concepts/benchmarks.md)).

- `n_windows`: how many test windows, ending at the table's last submit.
- `test_window_hours`: each test window's length.
- `training_lookback_days`: the history each window trains on.
- `window_n_jobs`: windows fitted at once. `1` is sequential; more runs windows in parallel
  with the same results, up to floating-point detail ([known issues](../known-issues.md)).
- `log_target`: train on `log1p(target)` and predict with `expm1`. Scores stay in the
  target's units. It helps typical jobs on heavy-tailed workloads, at some cost in MAE and RMSE.
- `time_decay_rate`: weight recent training rows more, per day. `0.05` is roughly a two-week
  half-life.
- `objective`: for the XGBoost models, the loss the trees fit. `reg:absoluteerror` fits the
  metric the leaderboard ranks on.
- `target_encode_min_cardinality`, `target_encode_smoothing`: for the rolling tabular models,
  target-encode columns with at least this many distinct values instead of one-hot encoding
  them, shrinking rare categories toward the window median. `0` turns it off.
- `embedding_field`: for the embedding models, the column holding each job's embedding.
- `sims_block_bytes`: for embedding kNN, the memory for one block of similarities. Larger
  queries are streamed in blocks of this size.
- For MoE XGBoost, the routing: `enable_power_users`, `power_user_percentile`,
  `min_expert_rows`, `n_wallclock_bins`, `wallclock_bin_edges_hours` and `estimator_n_jobs`.
  Its [card](../models/moe_xgboost.md) describes them.

**`cutoff`:** every job submitted on or after a date is a test job; everything earlier is
history only. It runs the UoPC paper's protocol ([UoPC](../benchmarking/power/uopc.md)).

- `test_start`: the cutoff, an ISO date. Quote it, so YAML keeps it a string.
- `theta`, `k`: the history size and the number of neighbours.
- `theta_values`, `k_values`: run the θ × k sensitivity grid instead. The headline `theta`
  and `k` must be in it.
- `node_count`: `requested` or `allocated`, the nodes power is divided by.
- `max_alloc_ratio`: leave out jobs allocated more than this many times the nodes they asked
  for.

For UoPC, under `cutoff` or `rolling`:

- `uopc_features`: `balanced`, `zscore` or `embedding`, the features neighbours are found by.
- `predictor`: `median`, `mean` or `vote`, how the neighbours' power becomes a prediction.

## `run`

| Key | Meaning |
|---|---|
| `output_dir` | Where the result bundle goes (default `runs`). |
| `overwrite` | Replace an existing bundle of the same name. |
| `extras` | `save_predictions: true` writes `predictions.parquet` into the bundle; `save_model: true` writes `model/last_model.pkl`, the model (or, for some models, its settings) from the last window. Not every model supports it. |

## Validation rules

`hpc-oda benchmark` checks a recipe before it runs:

- the schema: required keys and value types;
- `mae` and `rmse` are among the metrics, and every metric has the same, non-empty target;
- `node_count` and `max_alloc_ratio` only with `method: cutoff`;
- `uopc_features` and `predictor` only for `model.uopc`, under `cutoff` or `rolling`;
- for `cutoff`, `test_start` is a valid date;
- for `rolling`, `n_windows` is a positive integer, and `test_window_hours` and
  `training_lookback_days`, if given, are too.

`python scripts/validate_recipes.py` checks every bundled recipe; CI runs it.
