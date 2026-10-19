# Power prediction on Eagle and Kestrel

The eight models of the [F-DATA power benchmark](power.md) predicting **average power per
node** on NLR Eagle and Kestrel, on the same split shape
([#217](https://github.com/NatLabRockies/hpc-oda-commons/issues/217),
[#219](https://github.com/NatLabRockies/hpc-oda-commons/issues/219)). How to run them:
[Predict job power](../how-to/predict-power.md).

## Protocol

- **Data:** `dataset.job_runtime.nlr_eagle` and `dataset.job_runtime.nlr_kestrel`, prepared
  from their descriptors, then cut with `hpc-oda datasets slice`. Only jobs with a power
  reading are trained on and scored ([coverage](../datasets/power-sources.md)).
- **Target:** `avgpcon_per_node`, the job's energy over its runtime, in watts per node used.
  Neither source has peak power.
- **Split:** 89 daily windows ending at the last submit, with 60 days of training lookback,
  as on F-DATA.
- **Test periods:** the last 89 days before each system started winding down.

  | System | Slice | Test period (UTC) | Jobs with power | Users | Top user's share |
  |---|---|---|---:|---:|---:|
  | Eagle | 2023-05-01 – 2023-09-30 | 2023-07-03 16:00 – 2023-09-30 16:00 | 490,260 | 428 | 9.0% |
  | Kestrel | 2025-08-01 – 2026-01-01 | 2025-10-05 06:00 – 2026-01-02 06:00 | 638,081 | 475 | 11.8% |

  - Eagle's own last 89 days (late March to June 2024) fall in its wind-down. Monthly jobs
    fell from 240k in January 2024 to 32k in June, leaving 122k jobs with power from 159
    users. One user had 41.8% of them.
  - Kestrel never wound down, so it runs its last 89 days. The runtime benchmark's Kestrel
    window (2025-03-29 to 06-26) was rejected: one user submitted 59.5% of its 1.36M jobs
    with power.
  - The counts are over the jobs the runs scored.
- **Models:** baseline (window mean), signature memorizer, TF-IDF + kNN, embedding + kNN,
  UoPC (θ = 500, k = 5), XGBoost, Random Forest and MoE XGBoost, all with their default
  configuration. MLP is left out, as on F-DATA.
- **The job embedding is computed, not shipped.** On F-DATA, UoPC and embedding + kNN read
  the job embedding F-DATA provides. Eagle and Kestrel have none, and no job names or
  scripts, so `hpc-oda embed` (harrier-oss-v1-0.6b, prose) encodes each job's submission
  fields: partition, qos, account, user, requested walltime, nodes, cores and GPUs, and the
  weekday and hour of submission. These are the fields the other models already see.
  UoPC's numeric features include the requested CPU frequency, which neither source has;
  the missing column adds nothing.
- **Metrics:** MAE and RMSE (W/node), MAPE, R², over all scored rows.

## Results

Run on 2026-10-18 on an Apple M3 Max (14 cores, 38 GB), one recipe at a time. On each
system every model scored the same jobs, in all 89 windows. UoPC predicted the window mean
for users with fewer than k = 5 training jobs: 18,169 Eagle jobs (3.7%) and 4,999 Kestrel
jobs (0.8%). Best value in each column in bold.

**Eagle (`avgpcon_per_node`, W per node; 490,260 jobs)**

| Model | MAE | RMSE | MAPE | R² | Wall time |
|---|---:|---:|---:|---:|---:|
| XGBoost | **64.27** | **90.09** | **20.33%** | **0.322** | 27 min |
| MoE XGBoost | 64.81 | 92.13 | 20.54% | 0.291 | 11 min† |
| Random Forest | 66.16 | 94.28 | 21.13% | 0.258 | 9 min† |
| Signature memorizer | 66.61 | 97.99 | 20.73% | 0.198 | 6 min |
| Embedding + kNN | 77.41 | 109.83 | 24.48% | −0.008 | 14 min |
| TF-IDF + kNN | 78.12 | 115.84 | 24.39% | −0.121 | 14 min |
| UoPC (θ = 500, k = 5) | 80.94 | 116.87 | 24.15% | −0.141 | 2 min |
| Baseline (window mean) | 92.78 | 109.81 | 30.02% | −0.007 | 2 min |

**Kestrel (`avgpcon_per_node`, W per node; 638,081 jobs)**

| Model | MAE | RMSE | MAPE | R² | Wall time |
|---|---:|---:|---:|---:|---:|
| MoE XGBoost | **86.21** | 129.46 | **19.41%** | 0.468 | 15 min† |
| XGBoost | 90.04 | **127.93** | 21.20% | **0.481** | 43 min |
| Random Forest | 101.59 | 150.62 | 23.30% | 0.280 | 15 min† |
| Signature memorizer | 112.61 | 161.41 | 26.56% | 0.173 | 8 min |
| Embedding + kNN | 113.12 | 167.20 | 25.26% | 0.113 | 26 min |
| TF-IDF + kNN | 113.26 | 171.75 | 25.05% | 0.064 | 27 min |
| UoPC (θ = 500, k = 5) | 125.34 | 190.91 | 26.27% | −0.157 | 3 min |
| Baseline (window mean) | 163.08 | 179.36 | 36.10% | −0.021 | 3 min |

† Read every day's preprocessing from the store that the XGBoost run had just filled
([#213](https://github.com/NatLabRockies/hpc-oda-commons/issues/213)).

**The XGBoost models are best on both systems.** On Eagle, XGBoost leads every column, with
MoE XGBoost close behind. On Kestrel, MoE XGBoost has the lowest MAE and MAPE and XGBoost
the lowest RMSE and highest R². The two are within two points of MAPE of each other on
both systems.

**Predicting power is much harder here than on F-DATA.** The best MAPE is about 20%, against
10% on F-DATA, and the best R² is 0.32 (Eagle) and 0.48 (Kestrel), against 0.81. The
window mean is about as far off on all three (30%, 36% and 35.5% MAPE). The difference is
how much of that error the models remove: the best MAE is 31% below the baseline's on
Eagle and 47% below on Kestrel, against 72% on F-DATA. F-DATA's records include the job
name and the requested CPU frequency; Eagle's and Kestrel's include neither. We haven't
measured how much of the gap that explains.

**Remembering identical jobs gets most of the way on Eagle.** The signature memorizer, the
median power of past jobs with the same submission fields, found an exact match for 72% of
Eagle's jobs and 67% of Kestrel's (57% on F-DATA). On Eagle it is within 2.3 W of
XGBoost's MAE, though well behind on RMSE and R²: it misses the jobs it hasn't seen. On
Kestrel the tree models pull clearly ahead of it.

**TF-IDF + kNN does worse than memorizing.** On Eagle its R² is below zero and its RMSE is
above the baseline's: its large misses cost more than predicting the window mean would.
On F-DATA it was ahead of the memorizer.

**The embedding models add nothing here.** On F-DATA, embedding + kNN and UoPC were
level with XGBoost and Random Forest (11.11% and 11.36% MAPE, against 11.05% and 11.10%).
Here they are about 4–7 points behind the best model, level with TF-IDF + kNN, and behind
the signature memorizer on MAE. UoPC's R² is below zero on both systems, and its RMSE is
above the window mean's. The computed embedding carries only the submission fields the
other models use directly, while F-DATA's comes from the source. So this measures the
methods on these systems, not on F-DATA's inputs.

**Random Forest trails on Kestrel.** It is 3.9 points of MAPE behind MoE XGBoost there,
against 0.6 on Eagle.

**Wall times are not comparable between models.** As on F-DATA, the tree models spend most
of their time building each day's OHE + SVD preprocessing. XGBoost built it; MoE XGBoost and Random Forest read it back and took a third to under half of XGBoost's time. The six models of #217 took just
under 3 hours: 68 minutes for Eagle and 1 h 50 min for Kestrel. UoPC and embedding + kNN
took 46 minutes more, plus 29 minutes to embed the two slices.

### How the runs were done

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
  ([known issues](../known-issues.md#note--on-macos-torch-and-xgboost-crash-in-one-process)).
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
