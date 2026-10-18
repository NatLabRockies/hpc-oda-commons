# Power prediction — every model on one protocol

Every runtime model predicting **power per node**, scored next to UoPC on the same
rolling windows and rows ([#204](https://github.com/NatLabRockies/hpc-oda-commons/issues/204)).
How to run any model on power: [Predict job power](../how-to/predict-power.md). The same
split on NLR Eagle and Kestrel: [Power prediction on Eagle and Kestrel](power-nlr.md).

## Protocol

- **Data:** `dataset.job_power.fdata_fugaku_uopc`, the five F-DATA months the UoPC paper
  uses (Fugaku, Dec 2023–Apr 2024).
- **Targets:** `avgpcon_per_node` and `maxpcon_per_node`, watts per requested node.
  Not per allocated node as in the paper: F-DATA's allocated count can be padded
  ([why](../how-to/predict-power.md#per-node-power)).
- **Split:** 89 daily windows ending at the last submit, so testing starts around
  2024-02-01, the paper's test period; 60 days of training lookback.
- **Models:** the eight in `recipes/job-power/*_rolling_{avg,peak}.yml`, all with their
  default configuration. UoPC runs at θ = 500, k = 5. MLP is left out, as it is from the
  runtime fleet run ([methodology](methodology.md)): it measured weaker than the other
  rolling-tabular models across the board on runtime, and here it cost ~130 s per window
  (over 3 h per target). `model.job_runtime_mlp` still predicts power when a recipe names
  it.
- **Metrics:** MAE and RMSE (W/node), MAPE, R², over all scored rows.
- **Same rows for everyone.** UoPC predicts the window mean for users with fewer than k
  training jobs, as the rolling baseline would, and reports how many in `rows_fallback`.

This differs from the [UoPC paper reproduction](uopc.md) on purpose: the paper scores each
job against everything its user finished before submission (an online protocol), and
divides by allocated nodes, while here every model, UoPC included, retrains once per day
on the previous 60 days and divides by requested nodes.

## Results

<!-- results:power-rolling -->

Run on 2026-10-16 and 17 on an Apple M3 Max (14 cores, 38 GB), one recipe at a time.
Every model scored the same 1,510,726 jobs, in the 85 of 89 daily windows that have test
jobs. UoPC predicted the window mean for 12,928 of them (0.86%), users with fewer than k = 5
training jobs. Best value in each column in bold.

**Average power (`avgpcon_per_node`, W per node)**

| Model | MAE | RMSE | MAPE | R² | Wall time |
|---|---:|---:|---:|---:|---:|
| MoE XGBoost | **7.19** | 14.75 | **10.07%** | 0.775 | 3.0 h |
| XGBoost | 7.68 | **13.54** | 11.05% | **0.810** | 2.6 h |
| Random Forest | 7.78 | 14.71 | 11.10% | 0.776 | 2.4 h |
| Embedding + kNN | 8.03 | 17.83 | 11.11% | 0.671 | 3.4 h |
| UoPC (θ = 500, k = 5) | 8.01 | 18.13 | 11.36% | 0.660 | 4 min |
| TF-IDF + kNN | 13.62 | 24.46 | 18.48% | 0.382 | 65 min |
| Signature memorizer | 15.47 | 25.02 | 20.88% | 0.353 | 28 min |
| Baseline (window mean) | 25.57 | 31.17 | 35.51% | −0.004 | 4 min |

**Peak power (`maxpcon_per_node`, W per node)**

| Model | MAE | RMSE | MAPE | R² | Wall time |
|---|---:|---:|---:|---:|---:|
| MoE XGBoost | **7.72** | 16.58 | **10.43%** | 0.746 | 67 min† |
| XGBoost | 7.98 | **14.69** | 11.43% | **0.801** | 34 min† |
| Random Forest | 7.98 | 15.54 | 11.17% | 0.777 | 71 min† |
| Embedding + kNN | 8.23 | 19.09 | 11.15% | 0.663 | 3.5 h |
| UoPC (θ = 500, k = 5) | 8.60 | 20.04 | 11.73% | 0.629 | 5 min |
| TF-IDF + kNN | 14.38 | 26.66 | 18.90% | 0.343 | 1.5 h |
| Signature memorizer | 15.86 | 26.77 | 19.43% | 0.338 | 29 min |
| Baseline (window mean) | 26.05 | 32.95 | 34.62% | −0.003 | 6 min |

† Read every day's preprocessing from the store (#213); see the wall-time note below.

**The tree models predict power best.** MoE XGBoost has the lowest MAE and MAPE on both
targets. Plain XGBoost has the lowest RMSE and the highest R², so it makes fewer large
misses. The three tree models are within about a point of MAPE of each other.

**UoPC is close on typical jobs and further behind on large errors.** Its MAPE is within
1.3 points of the best on both targets, but its RMSE is about a third higher than
XGBoost's and its R² is about 0.65 against about 0.8. Embedding + kNN, the other model that
reads F-DATA's job embedding, lands with it. Both predict from a job's nearest neighbours, while the tree
models also use the submission fields directly.

**Peak is a little harder than average.** MAE is higher for every model, and MAPE is up to
0.4 points higher for the five strongest.

**This is not the paper's number.** UoPC scores 9.93% MAPE in the [paper
reproduction](uopc.md) and 11.36% here. The two protocols differ: there each job is
predicted from all its user's earlier jobs, per allocated node; here every model retrains
once a day on the previous 60 days, per requested node.

**Wall times are not comparable between models.** The rolling-tabular models spend most of
their time building each day's OHE + SVD preprocessing, one day at a time. The average-power
runs of XGBoost and MoE XGBoost built it themselves at ~100 s per day. Random Forest
(average) filled the store at ~55 s per day. The three peak runs read it back. That is why
XGBoost took 2.6 h on average power and 34 minutes on peak. The kNN models, UoPC and the
baselines don't use that preprocessing.

### How the runs were done

- **One run at a time.** Two F-DATA rolling runs at once don't fit in 38 GB: a run peaks at
  22–36 GB. `window_n_jobs` (windows trained in parallel, execution-only and not part of
  the results) was 4 for the XGBoost-family runs. Window workers are threads, so a run uses
  one to three and a half cores.
- **Runs that died and were rerun.** XGBoost (average and peak) and MoE XGBoost (average)
  were each killed once by macOS when memory and swap ran out. They had 12 window workers,
  and for the first two another run was going at the same time. They were rerun from the
  start with 4 workers, one at a time; the tables show the reruns. The signature memorizer
  (average) first failed on F-DATA's array-valued embedding column. That was fixed in
  97b9e72, which only affects that failure, and the run was redone.
- **Code changed during the campaign, results did not.** The bundles span three source
  hashes: before 97b9e72, after it, and after the preprocessing store (#213). The store's
  results are byte-identical to building each day ([#214](https://github.com/NatLabRockies/hpc-oda-commons/pull/214)).
  MoE XGBoost (average) started on the earlier code and finished after the store was
  merged. Its bundle records the later commit because a bundle reads the checkout when it
  is written, not when the run starts ([#215](https://github.com/NatLabRockies/hpc-oda-commons/issues/215)).
- **MLP was dropped** after 3 of 89 windows of its average-power run, at ~130 s per window.
  See Protocol.

Reproduce any row with `hpc-oda benchmark src/hpc_oda_commons/recipes/job-power/<model>_rolling_{avg,peak}.yml`.

