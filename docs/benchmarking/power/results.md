# Power prediction — results

Every model predicting **power per node** on one shared rolling protocol, on every power
dataset. Job-power prediction is becoming a tracked benchmark
([#230](https://github.com/NatLabRockies/hpc-oda-commons/issues/230)); this page is where its
results live. How to run any model on power: [Predict job power](../../how-to/predict-power.md).
UoPC's own paper protocol is a separate, one-model study: [UoPC reproduction](uopc.md).

## Protocol

The same for every dataset
([#204](https://github.com/NatLabRockies/hpc-oda-commons/issues/204),
[#217](https://github.com/NatLabRockies/hpc-oda-commons/issues/217),
[#219](https://github.com/NatLabRockies/hpc-oda-commons/issues/219)):

- **Split:** 89 daily windows ending at the last submit, with 60 days of training lookback.
- **Targets:** `avgpcon_per_node` on every dataset, and `maxpcon_per_node` where the source
  records peak power (F-DATA). Watts per requested node, not per allocated node as in the
  UoPC paper: F-DATA's allocated count can be padded
  ([why](../../how-to/predict-power.md#per-node-power)). Only jobs with a power reading are
  trained on and scored.
- **Models:** baseline (window mean), signature memorizer, TF-IDF + kNN, embedding + kNN,
  UoPC (θ = 500, k = 20, `balanced` features), XGBoost, Random Forest and MoE XGBoost, each
  with its default configuration (`recipes/job-power/<model>_rolling_*.yml`). MLP is left
  out, as it is from the runtime fleet run ([methodology](../runtime/methodology.md)): it
  measured weaker than the other rolling-tabular models across the board on runtime, and on
  F-DATA it cost ~130 s per window (over 3 h per target). `model.job_runtime_mlp` still
  predicts power when a recipe names it.
- **Metrics:** MAE and RMSE (W/node), MAPE, R², over all scored rows.
- **Same rows for everyone.** UoPC predicts the window mean for users with fewer than k
  training jobs, as the rolling baseline would, and reports how many in `rows_fallback`.

This differs from the [UoPC paper reproduction](uopc.md) on purpose: the paper scores each
job against everything its user finished before submission (an online protocol), while here
every model, UoPC included, retrains once per day on the previous 60 days. The paper divides
by allocated nodes, which F-DATA pads ([why we don't](uopc.md#nodes-requested-not-allocated)).

## Datasets

| Dataset | Data | Targets | Test period (UTC) | Jobs scored | Users | Top user's share |
|---|---|---|---|---:|---:|---:|
| [F-DATA](#f-data) (Fugaku) | `dataset.job_power.fdata_fugaku_uopc`: Dec 2023 – Apr 2024, the five months the UoPC paper uses | average, peak | from ~2024-02-01, the paper's test period | 1,510,726 | | |
| [Eagle](#eagle-and-kestrel) (NLR) | `dataset.job_runtime.nlr_eagle`, sliced 2023-05-01 – 2023-09-30 | average | 2023-07-03 16:00 – 2023-09-30 16:00 | 490,260 | 428 | 9.0% |
| [Kestrel](#eagle-and-kestrel) (NLR) | `dataset.job_runtime.nlr_kestrel`, sliced 2025-08-01 – 2026-01-01 | average | 2025-10-05 06:00 – 2026-01-02 06:00 | 638,081 | 475 | 11.8% |

The counts are over the jobs the runs scored.

**How the windows were chosen.**
- **F-DATA** tests on the UoPC paper's test period, so the two protocols can be compared.
- **Eagle and Kestrel** each test on the last 89 days before the system started winding
  down. Each is prepared from its descriptor and cut with `hpc-oda datasets slice`
  ([coverage](../../datasets/power-sources.md)).
  - Eagle's own last 89 days (late March to June 2024) fall in its wind-down. Monthly jobs
    fell from 240k in January 2024 to 32k in June, leaving 122k jobs with power from 159
    users. One user had 41.8% of them.
  - Kestrel never wound down, so it runs its last 89 days. The runtime benchmark's Kestrel
    window (2025-03-29 to 06-26) was rejected: one user submitted 59.5% of its 1.36M jobs
    with power.

**The job embedding.** UoPC and embedding + kNN read a job embedding.
- **F-DATA** provides one.
- **Eagle and Kestrel** have none, and no job names or scripts. So `hpc-oda embed`
  (harrier-oss-v1-0.6b, prose) encodes each job's submission fields: partition, qos,
  account, user, requested walltime, nodes, cores and GPUs, and the weekday and hour of
  submission. These are the fields the other models already see.
- UoPC's `balanced` features add log2 of the requested nodes and the requested CPU
  frequency. Neither NLR source has frequency, so that column is 0 there.

## Results

<!-- results:power-rolling -->

### F-DATA

Run on 2026-10-16 and 17 on an Apple M3 Max (14 cores, 38 GB), one recipe at a time.
Every model scored the same 1,510,726 jobs, in the 85 of 89 daily windows that have test
jobs. UoPC predicted the window mean for 22,149 of them (1.47%), users with fewer than k = 20
training jobs. Best value in each column in bold.

UoPC's rows use its `balanced` features, the default since
[#222](https://github.com/NatLabRockies/hpc-oda-commons/issues/222), and k = 20, the default
since [#228](https://github.com/NatLabRockies/hpc-oda-commons/issues/228). They were rerun on
2026-10-20 at cd78524. At k = 5 it scored 10.80% / 0.682 (average) and 11.15% / 0.651 (peak)
with `balanced` features, and 11.36% / 0.660 and 11.73% / 0.629 with the earlier `zscore`
features ([feature modes](uopc.md#feature-modes)).

**Average power (`avgpcon_per_node`, W per node)**

| Model | MAE | RMSE | MAPE | R² | Wall time |
|---|---:|---:|---:|---:|---:|
| UoPC (θ = 500, k = 20) | **7.17** | 16.87 | 10.29% | 0.706 | 5 min |
| MoE XGBoost | 7.19 | 14.75 | **10.07%** | 0.775 | 3.0 h |
| XGBoost | 7.68 | **13.54** | 11.05% | **0.810** | 2.6 h |
| Random Forest | 7.78 | 14.71 | 11.10% | 0.776 | 2.4 h |
| Embedding + kNN | 8.03 | 17.83 | 11.11% | 0.671 | 3.4 h |
| TF-IDF + kNN | 13.62 | 24.46 | 18.48% | 0.382 | 65 min |
| Signature memorizer | 15.47 | 25.02 | 20.88% | 0.353 | 28 min |
| Baseline (window mean) | 25.57 | 31.17 | 35.51% | −0.004 | 4 min |

**Peak power (`maxpcon_per_node`, W per node)**

| Model | MAE | RMSE | MAPE | R² | Wall time |
|---|---:|---:|---:|---:|---:|
| UoPC (θ = 500, k = 20) | **7.63** | 18.38 | 10.68% | 0.688 | 5 min |
| MoE XGBoost | 7.72 | 16.58 | **10.43%** | 0.746 | 67 min† |
| XGBoost | 7.98 | **14.69** | 11.43% | **0.801** | 34 min† |
| Random Forest | 7.98 | 15.54 | 11.17% | 0.777 | 71 min† |
| Embedding + kNN | 8.23 | 19.09 | 11.15% | 0.663 | 3.5 h |
| TF-IDF + kNN | 14.38 | 26.66 | 18.90% | 0.343 | 1.5 h |
| Signature memorizer | 15.86 | 26.77 | 19.43% | 0.338 | 29 min |
| Baseline (window mean) | 26.05 | 32.95 | 34.62% | −0.003 | 6 min |

† Read every day's preprocessing from the store (#213); see the wall-time note below.

**The tree models predict power best overall.** MoE XGBoost has the lowest MAPE on both
targets. Plain XGBoost has the lowest RMSE and the highest R², so it makes fewer large
misses. The three tree models are within about a point of MAPE of each other.

**UoPC is level on typical jobs and further behind on large errors.**
- **Typical jobs:** it has the lowest MAE on both targets, just ahead of MoE XGBoost, and
  the second-best MAPE, within 0.25 points of MoE XGBoost's.
- **Large errors:** its RMSE is about 25% higher than XGBoost's, and its R² is 0.71 and 0.69
  against about 0.8.
- **Embedding + kNN,** the other model that reads F-DATA's job embedding, is behind it.

Both predict from a job's nearest neighbours, while the tree models also use the submission
fields directly.

**Peak is a little harder than average.** MAE is higher for every model, and MAPE is up to
0.4 points higher for the five strongest.

**This is not the paper's number.** UoPC scores 7.82% MAPE in the [paper
reproduction](uopc.md#our-reproduction-θ--500-k--20) and 10.29% here. Both divide by requested
nodes and use `balanced` features with k = 20; only the protocol differs:
- the reproduction predicts each job from all its user's jobs that finished before it was
  submitted;
- here every model retrains once a day on the previous 60 days.

That day-level cutoff costs about 2.5 points (2.7 with `zscore` features and k = 5: 8.65%
against 11.36%, [variants](uopc.md#variants-padded-jobs-and-node-count)).

**Wall times are not comparable between models.** The rolling-tabular models spend most of
their time building each day's OHE + SVD preprocessing, one day at a time. The average-power
runs of XGBoost and MoE XGBoost built it themselves at ~100 s per day. Random Forest
(average) filled the store at ~55 s per day. The three peak runs read it back. That is why
XGBoost took 2.6 h on average power and 34 minutes on peak. The kNN models, UoPC and the
baselines don't use that preprocessing.

### Eagle and Kestrel

Run on 2026-10-18 on an Apple M3 Max (14 cores, 38 GB), one recipe at a time. On each
system every model scored the same jobs, in all 89 windows. UoPC predicted the window mean
for users with fewer than k = 20 training jobs: 21,261 Eagle jobs (4.3%) and 10,485 Kestrel
jobs (1.6%). Best value in each column in bold.

UoPC's rows use its `balanced` features, the default since
[#222](https://github.com/NatLabRockies/hpc-oda-commons/issues/222), and k = 20, the default
since [#228](https://github.com/NatLabRockies/hpc-oda-commons/issues/228). They were rerun on
2026-10-20 at cd78524. k = 20 comes from the θ × k sweep on F-DATA
([uopc.md](uopc.md#sensitivity-sweep-θ--k)) and was not tuned on these systems. At k = 5 UoPC
scored 23.54% / −0.075 on Eagle and 24.69% / −0.015 on Kestrel, so k = 20 is worse on Eagle
and better on Kestrel. With the earlier `zscore` features and k = 5 it scored 24.15% /
−0.141 and 26.27% / −0.157 ([feature modes](uopc.md#feature-modes)).

**Eagle (`avgpcon_per_node`, W per node; 490,260 jobs)**

| Model | MAE | RMSE | MAPE | R² | Wall time |
|---|---:|---:|---:|---:|---:|
| XGBoost | **64.27** | **90.09** | **20.33%** | **0.322** | 27 min |
| MoE XGBoost | 64.81 | 92.13 | 20.54% | 0.291 | 11 min† |
| Random Forest | 66.16 | 94.28 | 21.13% | 0.258 | 9 min† |
| Signature memorizer | 66.61 | 97.99 | 20.73% | 0.198 | 6 min |
| Embedding + kNN | 77.41 | 109.83 | 24.48% | −0.008 | 14 min |
| TF-IDF + kNN | 78.12 | 115.84 | 24.39% | −0.121 | 14 min |
| UoPC (θ = 500, k = 20) | 81.10 | 120.75 | 25.21% | −0.218 | 2 min |
| Baseline (window mean) | 92.78 | 109.81 | 30.02% | −0.007 | 2 min |

**Kestrel (`avgpcon_per_node`, W per node; 638,081 jobs)**

| Model | MAE | RMSE | MAPE | R² | Wall time |
|---|---:|---:|---:|---:|---:|
| MoE XGBoost | **86.21** | 129.46 | **19.41%** | 0.468 | 15 min† |
| XGBoost | 90.04 | **127.93** | 21.20% | **0.481** | 43 min |
| Random Forest | 101.59 | 150.62 | 23.30% | 0.280 | 15 min† |
| UoPC (θ = 500, k = 20) | 101.83 | 166.89 | 23.08% | 0.116 | 3 min |
| Signature memorizer | 112.61 | 161.41 | 26.56% | 0.173 | 8 min |
| Embedding + kNN | 113.12 | 167.20 | 25.26% | 0.113 | 26 min |
| TF-IDF + kNN | 113.26 | 171.75 | 25.05% | 0.064 | 27 min |
| Baseline (window mean) | 163.08 | 179.36 | 36.10% | −0.021 | 3 min |

† Read every day's preprocessing from the store that the XGBoost run had just filled
([#213](https://github.com/NatLabRockies/hpc-oda-commons/issues/213)).

**The XGBoost models are best on both systems.** On Eagle, XGBoost leads every column, with
MoE XGBoost close behind. On Kestrel, MoE XGBoost has the lowest MAE and MAPE and XGBoost
the lowest RMSE and highest R². The two are within two points of MAPE of each other on
both systems.

**Predicting power is much harder on Eagle and Kestrel than on F-DATA.** The best MAPE is
about 20%, against 10% on F-DATA, and the best R² is 0.32 (Eagle) and 0.48 (Kestrel),
against 0.81. The
window mean is about as far off on all three (30%, 36% and 35.5% MAPE). The difference is
how much of that error the models remove: the best MAE is 31% below the baseline's on
Eagle and 47% below on Kestrel, against 72% on F-DATA. F-DATA's records include the job
name; Eagle's and Kestrel's don't. We haven't measured how much of the gap that explains.
F-DATA also has the requested CPU frequency, but only UoPC uses it: it is not in the
feature allowlist of the other models.

**Remembering identical jobs gets most of the way on Eagle.** The signature memorizer, the
median power of past jobs with the same submission fields, found an exact match for 72% of
Eagle's jobs and 67% of Kestrel's (57% on F-DATA). On Eagle it is within 2.3 W of
XGBoost's MAE, though well behind on RMSE and R²: it misses the jobs it hasn't seen. On
Kestrel the tree models pull clearly ahead of it.

**TF-IDF + kNN does worse than memorizing.** On Eagle its R² is below zero and its RMSE is
above the baseline's: its large misses cost more than predicting the window mean would.
On F-DATA it was ahead of the memorizer.

**The embedding models add nothing here.** On F-DATA, embedding + kNN and UoPC were level
with XGBoost and Random Forest: 11.11% and 10.29% MAPE, against 11.05% and 11.10%.
- **Here they are 4–6 points behind the best model.** On Eagle, embedding + kNN is level
  with TF-IDF + kNN and UoPC a little behind both; all three trail the signature memorizer
  on MAE. On Kestrel, UoPC is level with Random Forest on MAE and MAPE and ahead of the
  memorizer, but behind both on RMSE and R².
- **UoPC's R² is below zero on Eagle** (−0.22, with its RMSE above the window mean's), and
  0.12 on Kestrel.
- **The embeddings carry different information.** Ours carries only the submission fields
  the other models use directly. F-DATA's comes from the source and includes the real job
  names. So this measures the methods on these systems, not on F-DATA's inputs.

**Random Forest trails on Kestrel.** It is 3.9 points of MAPE behind MoE XGBoost there,
against 0.6 on Eagle.

**Wall times are not comparable between models.** As on F-DATA, the tree models spend most
of their time building each day's OHE + SVD preprocessing. XGBoost built it; MoE XGBoost and Random Forest read it back and took a third to under half of XGBoost's time. The six models of #217 took just
under 3 hours: 68 minutes for Eagle and 1 h 50 min for Kestrel. UoPC and embedding + kNN
took 46 minutes more, plus 29 minutes to embed the two slices.

## How the runs were done

### F-DATA

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
  merged. Its bundle records the later commit because a bundle then read the checkout when it
  was written, not when the run started. Since [#215](https://github.com/NatLabRockies/hpc-oda-commons/issues/215),
  a bundle records the code at start and flags a checkout that moved.
- **MLP was dropped** after 3 of 89 windows of its average-power run, at ~130 s per window.
  See Protocol.

Reproduce any row with `hpc-oda benchmark src/hpc_oda_commons/recipes/job-power/<model>_rolling_{avg,peak}.yml`.

### Eagle and Kestrel

- **Prepare and slice.** Eagle's full prepare took 36 minutes (23 GB peak), Kestrel's 25
  minutes (16 GB). Slicing kept 1,091,733 Eagle jobs and 1,809,064 Kestrel jobs, with
  power for 833,525 and 1,190,332 of them. That includes the training lookback and jobs
  that overlap the slice.
- **Embedding.** `hpc-oda embed` encodes each distinct text once: 43,314 for Eagle's slice
  (11 minutes, 14 GB peak) and 60,486 for Kestrel's (18 minutes, 19 GB). The embedded
  tables hold the same jobs in the same order, with the same power values.
- **A smoke run first.** Each model ran 3 windows on Eagle. All eight scored the same 6,162
  jobs: exactly the 7,913 jobs in those windows minus the 1,751 without power. That
  confirmed every model skips jobs without a reading.
- **One run at a time.** `window_n_jobs` was 4 for the XGBoost-family runs, as on F-DATA.
  It is execution-only and not part of the results. The six #217 models peaked at
  6.1 GB or less. UoPC peaked at 14 GB (Eagle) and 19 GB (Kestrel), and embedding + kNN at
  28 GB and 39 GB: it holds every job's 1024-wide vector.
- **Embedding and benchmarks ran in different environments.** On macOS, a process that
  imports torch and then fits XGBoost crashes
  ([known issues](../../known-issues.md#note--on-macos-torch-and-xgboost-crash-in-one-process)).
  Installing torch would also have switched embedding + kNN from the numpy backend F-DATA
  used. So the `embed` extra was removed again before the runs, and every model ran with
  the packages recorded by the #217 bundles. Embedding + kNN ran on numpy, on the CPU.
- **Two commits, one source hash.** The #217 bundles record commit f9d694e, and the #219
  bundles 1de02f6, which only adds recipes and tests. All sixteen record the same source
  hash.
- **The store held 3 Eagle days before the campaign.** The smoke run had built Eagle's last
  3 days, so the Eagle XGBoost run read 3 days from the store and built 86.

Reproduce any row with:

```
hpc-oda datasets prepare src/hpc_oda_commons/datasets/descriptors/job-runtime/nlr_<system>.yml
hpc-oda datasets slice data/datasets/nlr_<system>/data.parquet --start ... --end ... \
  --out data/windows/nlr_<system>_power/data.parquet
# UoPC and embedding + kNN only, in an environment with the `embed` extra:
hpc-oda embed data/windows/nlr_<system>_power/data.parquet \
  --out data/windows/nlr_<system>_power_embedded/data.parquet \
  --model microsoft/harrier-oss-v1-0.6b --format prose
hpc-oda benchmark src/hpc_oda_commons/recipes/job-power/<model>_rolling_avg_<system>.yml
```

Each recipe's header gives its system's `--start` and `--end`, and its embed step if it
has one.
