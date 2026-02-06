# Job Runtime Baseline Model

A deterministic baseline model for runtime prediction.

## Behavior (v0.1)

- **Fit:** compute mean of `runtime_seconds` from training rows.
- **Predict:** return the same mean for every row.

## Inputs

- Requires `runtime_seconds` in the input rows.

## Outputs

- Produces a list of runtime predictions (floats).
