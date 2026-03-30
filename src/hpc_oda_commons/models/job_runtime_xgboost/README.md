# Job Runtime XGBoost Model

This model is the alternate runtime predictor for `oda.job.v0.1.0` benchmark
recipes. It trains XGBoost regressors in a rolling evaluation loop and
reports global and per-window regression metrics.

## Preprocessing Pipeline

The model automatically prepares mixed-type job features before training:

- Detects categorical columns and profiles cardinality/frequency patterns.
- Applies one-hot encoding with infrequent-category handling to control feature
  growth.
- Applies `TruncatedSVD` over the sparse one-hot matrix to keep a compact,
  variance-preserving representation.
- Combines reduced categorical features with numeric features.

For reproducibility and tuning support, preprocessing diagnostics can be
generated via:

- `JobRuntimeXGBoostModel.analyze_preprocessing(...)`
- helpers in `preprocessing.py`

## Rolling Evaluation Behavior

The benchmark path uses strict rolling splits:

- Train rows: `split_time - training_lookback_days <= end_time < split_time`
- Test rows: `split_time <= submit_time < split_time + test_window_hours`

A new XGBoost regressor is trained at each split. One-hot/SVD preprocessing
artifacts are refreshed once per day (at the first split of each day) and then
reused for subsequent windows in that day.

## How To Run

Prerequisites:

- install dependencies (from repo root):

```bash
pip install -e ".[dev]"
```

Run the default rolling XGBoost recipe:

```bash
HPC_ODA_OFFLINE=1 hpc-oda benchmark hpc_oda_commons/recipes/job-runtime/xgb_hourly_recent.yml
```

Run a faster local variant (smaller rolling window):

```bash
HPC_ODA_OFFLINE=1 hpc-oda benchmark hpc_oda_commons/recipes/job-runtime/alt_model_example.yml
```

The benchmark writes a result bundle under `runs/benchmark-*/` containing:

- `result.json`
- `metrics.json` (includes per-window details and summary)
- `provenance.json`

## Recipe Requirements

For this model in v0.1, use:

- `model.id: model.job_runtime_xgboost`
- `split.method: rolling`
- `split.n_windows: <positive integer>`
- `split.test_window_hours: <positive integer>` (optional, default `6`)
- `split.training_lookback_days: <positive integer>` (optional, default `100`)

Supported benchmark metrics for rolling mode are `mae` and `rmse`.
