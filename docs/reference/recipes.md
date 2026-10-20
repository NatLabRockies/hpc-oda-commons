# Recipes Reference

## Built-in Recipes (v0.1)

| Recipe | Model | Split | Purpose |
|--------|-------|-------|---------|
| `baseline_tiny.yml` | Baseline (mean predictor) | Fixed 80/20 | CI smoke tests, offline demos |
| `xgb_hourly_recent.yml` | XGBoost | Rolling (1000 windows, 6h, 100d) | Full XGBoost benchmark |
| `alt_model_example.yml` | XGBoost | Rolling (24 windows, 6h, 30d) | Alternate config example |
| `mlp_rolling.yml` | MLP | Rolling (20 windows, 6h, 7d) | Feed-forward neural network example |
| `embedding_knn_rolling.yml` | Embedding + kNN | Rolling (20 windows, 6h, 7d) | Embedding-space kNN (needs an embedded dataset; see `hpc-oda embed`) |
| `uopc_maxpcon.yml` | UoPC (power) | Fixed | Per-user online power prediction example |
| `job-power/uopc_paper_reproduction.yml` | UoPC (power) | Cutoff (2024-02-01, θ=500, k=20) | Our UoPC reproduction on F-DATA: per requested node, `balanced` features — see [UoPC reproduction](../benchmarking/power/uopc.md) |
| `job-power/uopc_paper_reproduction_paper_setup.yml` | UoPC (power) | Cutoff, `node_count: allocated`, `zscore` | The authors' setup, for comparison with the paper only (#228) |
| `job-power/uopc_paper_reproduction_unpadded.yml` | UoPC (power) | Cutoff, authors' setup + `max_alloc_ratio: 12` | The authors' setup without jobs allocated >12× their request, which the paper's data lacks (#222) |
| `job-power/uopc_paper_sensitivity.yml` | UoPC (power) | Cutoff, θ × k sweep | The paper's sensitivity grid on our settings; headline at θ=500, k=20 |
| `job-power/uopc_paper_sensitivity_smoke.yml` | UoPC (power) | Cutoff, 1 × 2 sweep | Quick end-to-end check of the sweep |
| `job-power/<model>_rolling_{avg,peak}.yml` | Eight models (all but MLP) | Rolling (89 windows, 24h, 60d) | Average or peak power per node on one shared protocol — see [Power prediction benchmark](../benchmarking/power/results.md) |
| `job-power/<model>_rolling_avg_{eagle,kestrel}.yml` | Eight models (all but MLP) | Rolling (89 windows, 24h, 60d) | Average power per node on NLR Eagle (Jul–Sep 2023) and Kestrel (Oct–Dec 2025), on tables cut with `hpc-oda datasets slice`; UoPC and embedding kNN read them with an embedding from `hpc-oda embed` — see [Power prediction on Eagle and Kestrel](../benchmarking/power/results.md#eagle-and-kestrel) |
| `job-power/<model>_rolling_{avg,peak}_pm100.yml` | Eight models (all but MLP) | Rolling (89 windows, 24h, 60d) | Average and peak power per node on PM100 (Marconi100, Jul–Oct 2020); UoPC and embedding kNN read it with an embedding from `hpc-oda embed` — see [PM100](../benchmarking/power/results.md#pm100) |
| `moe_xgboost_rolling.yml` | MoE XGBoost | Rolling (20 windows, 6h, 7d) | Mixture-of-experts routing example |
| `kestrel_moe_best_rolling.yml` | MoE XGBoost | Rolling (120 windows, 6h, 120d) | The best measured configuration — see [Reproducing the reference result](#reproducing-the-reference-result) |

Bundled recipes are shipped with the package at `src/hpc_oda_commons/recipes/job-runtime/` (and `job-power/` for the paper-protocol power recipes).

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
schema_version: oda.job.v0.2.0

# Dataset to evaluate against
dataset:
  id: hpc_oda_commons/datasets/synthetic/job-runtime/tiny
  table_path: hpc_oda_commons/datasets/synthetic/job-runtime/tiny/data.parquet
  manifest_path: hpc_oda_commons/datasets/synthetic/job-runtime/tiny/manifest.json

# Model to evaluate
model:
  id: model.job_runtime_baseline
  version: "0.1.0"

# Metrics to compute (v0.1 requires at least mae and rmse; other supported
# names are mape, r2, and underprediction_ratio)
metrics:
  - name: mae
    target: runtime_seconds
  - name: rmse
    target: runtime_seconds

# Train/test split strategy
split:
  method: fixed          # or "rolling" or "cutoff"
  train_fraction: 0.8    # for fixed splits only
  seed: 42               # for fixed splits only

# Output configuration
run:
  output_dir: runs
  overwrite: false
```

### Split Methods

**`fixed`** -- Deterministic train/test split. Used with `model.job_runtime_baseline` and the UoPC adaptation (`model.job_power_uopc`).
- `train_fraction` (float, required): fraction of data for training (e.g., `0.8`)
- `seed` (int, required): random seed for reproducibility

**`cutoff`** -- Every job submitted on or after a date is a test job; everything earlier is history only. Used with `model.job_power_uopc` to run the UoPC paper protocol ([UoPC reproduction](../benchmarking/power/uopc.md)).
- `test_start` (ISO date, required): the cutoff, e.g. `"2024-02-01"` (quote it, so YAML keeps it a string)
- `theta` (int, default `500`) / `k` (int, default `20`; the paper's is `5`): history size and neighbour count; with a sweep they name the headline cell
- `theta_values` / `k_values` (lists of int, optional): run the θ × k sensitivity grid instead of one reproduction; the headline `theta`/`k` must be in the grid

**`rolling`** -- Sliding windows that simulate production retraining. Used with the rolling models (`model.job_runtime_baseline`, `model.job_runtime_xgboost`, `model.job_runtime_random_forest`, `model.job_runtime_tfidf_knn`, `model.job_runtime_mlp`, `model.job_runtime_embedding_knn`, `model.job_runtime_moe_xgboost`, `model.job_runtime_signature_memorizer`) and with `model.job_power_uopc`, which then reads `theta`, `k` and `embedding_field` (see [Predict job power](../how-to/predict-power.md#uopc-on-the-same-windows)). Rolling recipes may report `mae`, `rmse`, `mape`, `r2` and `underprediction_ratio`.
- `n_windows` (int, required): number of windows to evaluate
- `test_window_hours` (int, default `6`): duration of each test window in hours
- `training_lookback_days` (int, default `100`): days of history per training window
- `window_n_jobs` (int, default `1`): worker threads for the independent per-window fits of the fitted tabular models (`xgboost`, `random_forest`, `mlp`). `1` is sequential; `>1` runs windows concurrently with BLAS pinned per worker (results are unchanged except for the floating-point caveat in [known-issues](../known-issues.md)).
- `log_target` (bool, default `false`): train on `log1p(target)` and invert with `expm1` before scoring. Supported by `xgboost`, `random_forest`, `mlp`, `tfidf_knn`, and `embedding_knn`. Metrics stay in the target's units. Improves typical-job accuracy on heavy-tailed workloads at the cost of MAE/RMSE — see [the reference](../hpc-oda-commons-reference.md) for measured numbers.
- `embedding_field` (string, default `embedding`): embedding-kNN and rolling UoPC — the column holding each job's embedding vector.
- `sims_block_bytes` (int, default `2147483648`): embedding-kNN only — peak bytes for one dense similarity block; the query is streamed in blocks of this budget so per-window memory stays bounded on large corpora.
- `time_decay_rate` (float, default `0.0`): exponential recency weight on training rows, in units of 1/day — `0.05` is roughly a two-week half-life. Supported by the rolling tabular models; composes with `objective`.
- `objective` (string, default `reg:squarederror`): XGBoost and MoE XGBoost only — the loss the trees are fitted against. `reg:absoluteerror` fits the metric the leaderboard ranks on; on heavy-tailed runtimes the two are not close. Trades RMSE for MAE and median AE.

`model.job_runtime_moe_xgboost` adds routing knobs on top of those:

- `enable_power_users` (bool, default `true`): whether the heaviest users get their own experts in addition to the wallclock bins. `false` routes every row by bin alone. There is no value of `power_user_percentile` that selects nobody, which is why this switch exists.
- `power_user_percentile` (float, default `0.99`): quantile of per-user job count at or above which a user is a power user. Inert when `enable_power_users` is `false`.
- `min_expert_rows` (int, default `100`): training rows a route needs before it gets its own expert; below it, its test rows fall back to the window-wide expert. Coverage never depends on routing.
- `n_wallclock_bins` (int, default `5`): how many requested-wallclock clusters to detect per training window. Each detected cluster becomes a bin, plus one open bin above the largest, so k clusters yield up to k+1 bins.
- `wallclock_bin_edges_hours` (list of floats, optional): pin the bin edges instead of deriving them per window.
- `estimator_n_jobs` (int, default `1`): threads inside each expert's fit.

### Validation Rules
- `metrics` must include at least `mae` and `rmse`
- All metrics must target the same field (e.g., `runtime_seconds`). **That field is what the model predicts**, not a label: the target-configurable models are trained on it, and a model that cannot predict it (e.g. the fixed UoPC adaptation, which only predicts `maxpcon`) fails the run. See [Predict job power](../how-to/predict-power.md).
- For `rolling`, `n_windows` must be positive

## Reproducing the reference result

`kestrel_moe_best_rolling.yml` encodes the best job-runtime configuration measured to date. Three commands reproduce it from a fresh clone:

```bash
# 1. Prepare the canonical table -> data/datasets/nlr_kestrel/data.parquet
hpc-oda datasets prepare src/hpc_oda_commons/datasets/descriptors/job-runtime/nlr_kestrel.yml

# 2. Slice to the benchmark window -> data/windows/nlr_kestrel/{data.parquet,slice.json}
hpc-oda bench-matrix slice --dataset nlr_kestrel --extra-lookback-days 60 --out data/windows

# 3. Run it
hpc-oda benchmark src/hpc_oda_commons/recipes/job-runtime/kestrel_moe_best_rolling.yml -v
```

**Why `--extra-lookback-days 60`.** A dataset card sizes its window as `train_days` + `test_days` — 60 + 30 for `nlr_kestrel`, giving 2025-03-29..2025-06-26. This recipe asks for `training_lookback_days: 120`, so without the extension the earliest rolling windows would train on truncated history and quietly score differently. The option moves the *lower* bound back by the shortfall (`training_lookback_days − train_days`) and leaves the test region alone, so the run still scores exactly the rows the card window defines. The `slice.json` written beside the parquet records which window you got. Since #145, 60 is also what `bench-matrix slice` derives for this card on its own, so the flag here is an explicit restatement rather than a requirement — it keeps the command correct even if the fleet split changes.

**What reproduces.** The configuration and the ranking of arms reproduce exactly. The absolute numbers reproduce only to within environment variance: fitted-model output depends on CPU architecture and the BLAS/SIMD build, not only on code and data — see [known-issues](../known-issues.md) (MAJOR). On macOS/arm64 with xgboost 3.2.0 this recipe scores MAE 11,527.4, median AE 1,374.3, RMSE 33,974.5 over 254,338 rows.

## Custom Recipes

To create a custom recipe, copy a bundled one and modify it:

```bash
cp src/hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml my_recipe.yml
# Edit my_recipe.yml: change dataset.table_path, split params, etc.
hpc-oda benchmark my_recipe.yml
```

Custom recipes can live anywhere on disk. The `hpc-oda benchmark` command accepts any file path.
