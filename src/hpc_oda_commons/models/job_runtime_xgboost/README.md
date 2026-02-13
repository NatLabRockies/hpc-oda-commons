# Job Runtime XGBoost Model (Increment 1-2 Scaffold)

This package is the first alternate model scaffold for runtime prediction.

## Increment 1 Scope

- Adds model configuration surface and dependency checks for:
  - `xgboost`
  - `scikit-learn` (imported as `sklearn`)
- Defines public methods:
  - `fit()`
  - `predict()`
  - `evaluate_hourly()`

These methods intentionally raise `NotImplementedError` in Increment 1. The
next increments will implement automatic categorical preprocessing (one-hot +
dimensionality reduction), rolling hourly splits, and daily preprocessing
refresh behavior.

## Increment 2 Scope

- Adds automatic preprocessing analysis:
  - categorical feature profiling (cardinality, null rate, category frequencies),
  - one-hot configuration with infrequent-category handling,
  - TruncatedSVD component selection to satisfy target explained-variance coverage.
- Adds diagnostics emission for reproducibility:
  - `JobRuntimeXGBoostModel.analyze_preprocessing(..., diagnostics_path=...)`
  - standalone utilities in `preprocessing.py`.

Model training/evaluation loops remain deferred to later increments.

## Increment 3 Scope

- Adds rolling split engine with strict semantics:
  - train rows: `end_time < split_time`
  - test rows: `split_time <= submit_time < split_time + 1h`
- Adds day-keyed preprocessing cache to support daily OHE/SVD refits.
- Exposes helpers:
  - `build_hourly_rolling_splits(...)`
  - `materialize_split_rows(...)`
  - `DailyPreprocessingCache`
  - `JobRuntimeXGBoostModel.build_hourly_split_plan(...)`

## Increment 4 Scope

- Implements `JobRuntimeXGBoostModel.evaluate_hourly(...)`:
  - trains one XGBoost regressor per split hour,
  - reuses day-keyed preprocessing artifacts (one-hot + SVD),
  - computes per-hour metrics and global MAE/RMSE over concatenated predictions.
- Returns payload shaped for future benchmark integration:
  - top-level `mae`, `rmse`, `definitions`,
  - `hourly` entries with status, split metadata, feature info, and per-hour metrics,
  - `summary` including scored/skipped hours and preprocessing refit count.
