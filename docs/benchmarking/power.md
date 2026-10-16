# Power prediction — every model on one protocol

Every runtime model predicting **power per node**, scored next to UoPC on the same
rolling windows and rows ([#204](https://github.com/NatLabRockies/hpc-oda-commons/issues/204)).
How to run any model on power: [Predict job power](../how-to/predict-power.md).

## Protocol

- **Data:** `dataset.job_power.fdata_fugaku_uopc`, the five F-DATA months the UoPC paper
  uses (Fugaku, Dec 2023–Apr 2024).
- **Targets:** `avgpcon_per_node` and `maxpcon_per_node`, watts per requested node.
  Not per allocated node as in the paper: F-DATA's allocated count can be padded
  ([why](../how-to/predict-power.md#per-node-power)).
- **Split:** 89 daily windows ending at the last submit, so testing starts around
  2024-02-01, the paper's test period; 60 days of training lookback.
- **Models:** the nine in `recipes/job-power/*_rolling_{avg,peak}.yml`, all with their
  default configuration. UoPC runs at θ = 500, k = 5.
- **Metrics:** MAE and RMSE (W/node), MAPE, R², over all scored rows.
- **Same rows for everyone.** UoPC predicts the window mean for users with fewer than k
  training jobs, as the rolling baseline would, and reports how many in `rows_fallback`.

This differs from the [UoPC paper reproduction](uopc.md) on purpose: the paper scores each
job against everything its user finished before submission (an online protocol), and
divides by allocated nodes, while here every model, UoPC included, retrains once per day
on the previous 60 days and divides by requested nodes.

## Results

<!-- results:power-rolling -->
