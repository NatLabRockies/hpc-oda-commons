# Power prediction — results

Every model predicting **power per node** on one shared rolling protocol, on every power
dataset. Job-power prediction is becoming a tracked benchmark
([#230](https://github.com/NatLabRockies/hpc-oda-commons/issues/230)); this page is where its
results live, and [Methodology](methodology.md) records what was decided and why. How to run any model on power: [Predict job power](../../how-to/predict-power.md).
UoPC's own paper protocol is a separate, one-model study: [UoPC reproduction](uopc.md).

## Protocol

The same for every dataset
([#204](https://github.com/NatLabRockies/hpc-oda-commons/issues/204),
[#217](https://github.com/NatLabRockies/hpc-oda-commons/issues/217),
[#219](https://github.com/NatLabRockies/hpc-oda-commons/issues/219),
[#230](https://github.com/NatLabRockies/hpc-oda-commons/issues/230)):

- **Split:** 89 daily windows ending at the last submit, with 60 days of training lookback.
- **Targets:** `avgpcon_per_node` on every dataset, and `maxpcon_per_node` where the source
  records peak power (F-DATA and PM100). Watts per node the job ran on: requested nodes on
  F-DATA, whose allocated count can be padded, not allocated nodes as in the UoPC paper
  ([why](../../how-to/predict-power.md#per-node-power), [per dataset](methodology.md#targets)).
  Only jobs with a power reading are trained on and scored.
- **Models:** baseline (window mean), signature memorizer, TF-IDF + kNN, embedding + kNN,
  UoPC (θ = 500, k = 20, `balanced` features, the median of its neighbours), XGBoost, Random
  Forest and MoE XGBoost, each with its default configuration
  (`recipes/job-power/<model>_rolling_*.yml`). MLP is left out, as it is from the runtime fleet run ([methodology](../runtime/methodology.md)): it
  measured weaker than the other rolling-tabular models across the board on runtime, and on
  F-DATA it cost ~130 s per window (over 3 h per target). `model.mlp` still
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
| [F-DATA](#f-data) (Fugaku) | `dataset.fdata_fugaku`, window 2023-11-30 – 2024-04-30: the five months the UoPC paper uses | average, peak | 2024-02-02 14:00 – 2024-05-01 14:00 (the paper's starts on 2024-02-01) | 1,510,726 | | |
| [Eagle](#eagle-and-kestrel) (NLR) | `dataset.nlr_eagle`, window 2023-05-01 – 2023-09-30 | average | 2023-07-03 16:00 – 2023-09-30 16:00 | 490,260 | 428 | 9.0% |
| [Kestrel](#eagle-and-kestrel) (NLR) | `dataset.nlr_kestrel`, window 2025-08-01 – 2026-01-01 | average | 2025-10-05 06:00 – 2026-01-02 06:00 | 638,081 | 475 | 11.8% |
| [PM100](#pm100) (Marconi100) | `dataset.pm100`, all of it: May – Oct 2020 | average, peak | 2020-07-17 04:00 – 2020-10-14 04:00 | 142,206 | 380 | 20.8% |

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
- **PM100** tests on its last 89 days. It is a May–Oct 2020 extract with no wind-down, and
  needs no slice. Its window touches a missing block at its first day, kept as a recorded
  exception ([methodology](methodology.md#health-gate)). Three test days have no submissions,
  so 86 of its 89 windows score.

**The job embedding.** UoPC and embedding + kNN read a job embedding.
- **F-DATA** provides one.
- **Eagle, Kestrel and PM100** have none, and no job names or scripts. So `hpc-oda embed`
  (harrier-oss-v1-0.6b, prose) encodes each job's submission fields: partition, qos,
  account, user, requested walltime, nodes, cores and GPUs where the source has them, and
  the weekday and hour of submission. These are the fields the other models already see,
  plus the submission time.
- UoPC's `balanced` features add log2 of the requested nodes and the requested CPU
  frequency. Only F-DATA has frequency, so that column is 0 elsewhere.

## Results

<!-- results:power-rolling -->

### How much accuracy is available

Each dataset's **error floor** is the lowest MAE any predictor could reach from the jobs'
inputs ([methodology](methodology.md#error-ceilings)). Jobs whose inputs are all identical
can't be told apart, so the best any model can do is predict each such group's median. The
signature is every input any model here reads: the shared submission fields, plus the job
embedding and requested frequency.

| Dataset | Target | Baseline MAE | Floor MAE | Floor RMSE | Floor without the embedding | Signatures | Rows alone | Best model MAE |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| F-DATA | average | 25.57 | 2.55 | 7.11 | 2.61 | 146,137 | 5.8% | 7.17 |
| F-DATA | peak | 26.05 | 2.55 | 7.54 | 2.61 | 146,137 | 5.8% | 7.63 |
| Eagle | average | 92.78 | 29.15 | 54.11 | 40.32 | 22,657 | 2.4% | 64.27 |
| Kestrel | average | 163.08 | 27.60 | 59.58 | 46.14 | 24,451 | 2.0% | 86.21 |
| PM100 | average | 148.24 | 88.65 | 139.74 | 117.14 | 19,750 | 7.4% | 131.20 |
| PM100 | peak | 205.48 | 119.90 | 185.79 | 160.39 | 19,750 | 7.4% | 181.93 |

- **The best models capture 80% of the headroom on F-DATA, 57% on Kestrel, 45% on Eagle and
  29% on PM100.** Raw MAE can't show that, since a Kestrel node draws several times a Fugaku
  node's power.
- **On Eagle, Kestrel and PM100 the embedding lowers the floor a lot.** There it encodes the
  weekday and hour a job was submitted, which no other model sees. Without it, on the shared
  fields alone, the floors are 40, 46 and 117 W rather than 29, 28 and 89. A finer signature
  always lowers the floor, though, because it splits jobs into smaller groups whether or not
  the extra field carries real information. So the floor can't say how much of that a model
  could actually use. On F-DATA the embedding adds little (2.61 against 2.55 W): it holds the
  job environment, beyond fields the other models already have.
- **The floors are not vacuous.** At most 7.4% of scored jobs are alone in their signature,
  where the floor can't constrain them. A floor is a bound, though, not a score some model
  is known to reach.

**Headroom captured** in the tables below is
(baseline MAE − model MAE) / (baseline MAE − floor MAE): the share of the error between
predicting the window mean and the floor that a model removes. Unlike MAE, it compares across
datasets. The files are `docs/benchmarking/datasets/<dataset>.<target>.ceiling.json`.

### F-DATA

Run on 2026-10-16 and 17 on an Apple M3 Max (14 cores, 38 GB), one recipe at a time.
Every model scored the same 1,510,726 jobs, in the 85 of 89 daily windows that have test
jobs. UoPC predicted the window mean for 22,149 of them (1.47%), users with fewer than k = 20
training jobs. Best value in each column in bold.

UoPC's rows use its `balanced` features, the default since
[#222](https://github.com/NatLabRockies/hpc-oda-commons/issues/222), and k = 20, the default
since [#228](https://github.com/NatLabRockies/hpc-oda-commons/issues/228), and predict the
median of the k neighbours, the default since [#241](https://github.com/NatLabRockies/hpc-oda-commons/issues/241). They were rerun on 2026-10-20 at 4ee97bb.
With the authors' vote over whole watts ([why not](uopc.md#the-median-of-the-neighbours-not-a-vote))
UoPC scored MAE 7.17 / 10.29% / 0.706 (average) and 7.63 / 10.68% / 0.688 (peak). At k = 5
with the vote it scored 10.80% / 0.682 and 11.15% / 0.651 with `balanced` features, and
11.36% / 0.660 and 11.73% / 0.629 with the earlier `zscore` features
([feature modes](uopc.md#feature-modes)).

**Average power (`avgpcon_per_node`, W per node)**

| Model | MAE | RMSE | MAPE | R² | Headroom | Wall time |
|---|---:|---:|---:|---:|---:|---:|
| UoPC (θ = 500, k = 20) | **7.10** | 16.53 | 10.57% | 0.718 | **80%** | 5 min |
| MoE XGBoost | 7.19 | 14.75 | **10.07%** | 0.775 | **80%** | 3.0 h |
| XGBoost | 7.68 | **13.54** | 11.05% | **0.810** | 78% | 2.6 h |
| Random Forest | 7.78 | 14.71 | 11.10% | 0.776 | 77% | 2.4 h |
| Embedding + kNN | 8.03 | 17.83 | 11.11% | 0.671 | 76% | 3.4 h |
| TF-IDF + kNN | 13.62 | 24.46 | 18.48% | 0.382 | 52% | 65 min |
| Signature memorizer | 15.47 | 25.02 | 20.88% | 0.353 | 44% | 28 min |
| Baseline (window mean) | 25.57 | 31.17 | 35.51% | −0.004 | 0% | 4 min |

**Peak power (`maxpcon_per_node`, W per node)**

| Model | MAE | RMSE | MAPE | R² | Headroom | Wall time |
|---|---:|---:|---:|---:|---:|---:|
| UoPC (θ = 500, k = 20) | **7.44** | 18.03 | 10.73% | 0.700 | **79%** | 5 min |
| MoE XGBoost | 7.72 | 16.58 | **10.43%** | 0.746 | 78% | 67 min† |
| XGBoost | 7.98 | **14.69** | 11.43% | **0.801** | 77% | 34 min† |
| Random Forest | 7.98 | 15.54 | 11.17% | 0.777 | 77% | 71 min† |
| Embedding + kNN | 8.23 | 19.09 | 11.15% | 0.663 | 76% | 3.5 h |
| TF-IDF + kNN | 14.38 | 26.66 | 18.90% | 0.343 | 50% | 1.5 h |
| Signature memorizer | 15.86 | 26.77 | 19.43% | 0.338 | 43% | 29 min |
| Baseline (window mean) | 26.05 | 32.95 | 34.62% | −0.003 | 0% | 6 min |

† Read every day's preprocessing from the store (#213); see the wall-time note below.

**The tree models predict power best overall.** MoE XGBoost has the lowest MAPE on both
targets. Plain XGBoost has the lowest RMSE and the highest R², so it makes fewer large
misses. The three tree models are within about a point of MAPE of each other.

**UoPC is level on typical jobs and further behind on large errors.**
- **Typical jobs:** it has the lowest MAE on both targets, ahead of MoE XGBoost (7.10 against
  7.19 W, and 7.44 against 7.72), and the second-best MAPE, 0.3–0.5 points behind MoE
  XGBoost's.
- **Large errors:** its RMSE is about 22% higher than XGBoost's, and its R² is 0.72 and 0.70
  against about 0.8.
- **Embedding + kNN,** the other model that reads F-DATA's job embedding, is behind it.

Both predict from a job's nearest neighbours, while the tree models also use the submission
fields directly.

**Peak is a little harder than average.** MAE is higher for every model, and MAPE is up to
0.4 points higher for the five strongest.

**This is not the paper's number.** UoPC scores 7.63% MAPE in the [paper
reproduction](uopc.md#our-reproduction-θ--500-k--20) and 10.57% here. Both divide by requested
nodes and use `balanced` features, k = 20 and the median; only the protocol differs:
- the reproduction predicts each job from all its user's jobs that finished before it was
  submitted;
- here every model retrains once a day on the previous 60 days.

That day-level cutoff costs about 2.9 points (2.7 with `zscore` features, k = 5 and the vote:
8.65% against 11.36%, [variants](uopc.md#variants-padded-jobs-and-node-count)).

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
since [#228](https://github.com/NatLabRockies/hpc-oda-commons/issues/228), and predict the
median of the k neighbours, the default since [#241](https://github.com/NatLabRockies/hpc-oda-commons/issues/241). They were rerun on 2026-10-20 at 4ee97bb.
k = 20 and the median were chosen on F-DATA ([uopc.md](uopc.md#our-choices-and-why)) and not
tuned on these systems. With the authors' vote at k = 20 UoPC scored MAE 81.10 / 25.21% /
−0.218 on Eagle and 101.83 / 23.08% / 0.116 on Kestrel: the median lowers MAE on both, but
raises MAPE on Eagle. At k = 5 with the vote it scored 23.54% / −0.075 and 24.69% / −0.015.
With the earlier `zscore` features and k = 5 it scored 24.15% / −0.141 and 26.27% / −0.157
([feature modes](uopc.md#feature-modes)).

**Eagle (`avgpcon_per_node`, W per node; 490,260 jobs)**

| Model | MAE | RMSE | MAPE | R² | Headroom | Wall time |
|---|---:|---:|---:|---:|---:|---:|
| XGBoost | **64.27** | **90.09** | **20.33%** | **0.322** | **45%** | 27 min |
| MoE XGBoost | 64.81 | 92.13 | 20.54% | 0.291 | 44% | 11 min† |
| Random Forest | 66.16 | 94.28 | 21.13% | 0.258 | 42% | 9 min† |
| Signature memorizer | 66.61 | 97.99 | 20.73% | 0.198 | 41% | 6 min |
| Embedding + kNN | 77.41 | 109.83 | 24.48% | −0.008 | 24% | 14 min |
| TF-IDF + kNN | 78.12 | 115.84 | 24.39% | −0.121 | 23% | 14 min |
| UoPC (θ = 500, k = 20) | 80.16 | 120.80 | 25.97% | −0.219 | 20% | 2 min |
| Baseline (window mean) | 92.78 | 109.81 | 30.02% | −0.007 | 0% | 2 min |

**Kestrel (`avgpcon_per_node`, W per node; 638,081 jobs)**

| Model | MAE | RMSE | MAPE | R² | Headroom | Wall time |
|---|---:|---:|---:|---:|---:|---:|
| MoE XGBoost | **86.21** | 129.46 | **19.41%** | 0.468 | **57%** | 15 min† |
| XGBoost | 90.04 | **127.93** | 21.20% | **0.481** | 54% | 43 min |
| UoPC (θ = 500, k = 20) | 95.63 | 156.45 | 22.17% | 0.223 | 50% | 3 min |
| Random Forest | 101.59 | 150.62 | 23.30% | 0.280 | 45% | 15 min† |
| Signature memorizer | 112.61 | 161.41 | 26.56% | 0.173 | 37% | 8 min |
| Embedding + kNN | 113.12 | 167.20 | 25.26% | 0.113 | 37% | 26 min |
| TF-IDF + kNN | 113.26 | 171.75 | 25.05% | 0.064 | 37% | 27 min |
| Baseline (window mean) | 163.08 | 179.36 | 36.10% | −0.021 | 0% | 3 min |

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
with XGBoost and Random Forest: 11.11% and 10.57% MAPE, against 11.05% and 11.10%.
- **Here they are 3–6 points behind the best model.** On Eagle, embedding + kNN is level
  with TF-IDF + kNN and UoPC a little behind both; all three trail the signature memorizer
  on MAE. On Kestrel, UoPC is ahead of Random Forest and the memorizer on MAE and MAPE, but
  behind Random Forest on RMSE and R².
- **UoPC's R² is below zero on Eagle** (−0.22, with its RMSE above the window mean's), and
  0.22 on Kestrel.
- **The embeddings carry different information.** Ours carries only the submission fields
  the other models use directly. F-DATA's comes from the source and includes the real job
  names. So this measures the methods on these systems, not on F-DATA's inputs.

**Random Forest trails on Kestrel.** It is 3.9 points of MAPE behind MoE XGBoost there,
against 0.6 on Eagle.

**Wall times are not comparable between models.** As on F-DATA, the tree models spend most
of their time building each day's OHE + SVD preprocessing. XGBoost built it; MoE XGBoost and Random Forest read it back and took a third to under half of XGBoost's time. The six models of #217 took just
under 3 hours: 68 minutes for Eagle and 1 h 50 min for Kestrel. UoPC and embedding + kNN
took 46 minutes more, plus 29 minutes to embed the two slices.

### PM100

Run on 2026-10-20 on an Apple M3 Max (14 cores, 38 GB) at commit 20a7ab3, one recipe at a
time ([#230](https://github.com/NatLabRockies/hpc-oda-commons/issues/230)). Every model scored
the same 142,206 jobs, in the 86 of 89 daily windows that have test jobs. UoPC predicted the
window mean for 6,105 of them (4.3%), users with fewer than k = 20 training jobs. UoPC's rows
were rerun on 2026-10-20 at 4ee97bb with the median predictor ([#241](https://github.com/NatLabRockies/hpc-oda-commons/issues/241)). Best value
in each column in bold.

**Average power (`avgpcon_per_node`, W per node)**

| Model | MAE | RMSE | MAPE | R² | Headroom | Wall time |
|---|---:|---:|---:|---:|---:|---:|
| XGBoost | **131.20** | **177.06** | 18.14% | **0.144** | **29%** | 5 min† |
| Signature memorizer | 131.94 | 185.15 | **17.59%** | 0.064 | 27% | 74 s |
| Random Forest | 132.06 | 178.29 | 18.27% | 0.132 | 27% | 8 min |
| MoE XGBoost | 133.10 | 179.66 | 18.43% | 0.119 | 25% | 16 min† |
| UoPC (θ = 500, k = 20) | 145.22 | 205.57 | 18.79% | −0.154 | 5% | 30 s |
| Embedding + kNN | 147.05 | 197.85 | 20.19% | −0.068 | 2% | 2 min |
| Baseline (window mean) | 148.24 | 191.97 | 19.85% | −0.006 | 0% | 24 s |
| TF-IDF + kNN | 148.33 | 199.16 | 20.69% | −0.083 | 0% | 79 s |

**Peak power (`maxpcon_per_node`, W per node)**

| Model | MAE | RMSE | MAPE | R² | Headroom | Wall time |
|---|---:|---:|---:|---:|---:|---:|
| Signature memorizer | **181.93** | 255.60 | **21.94%** | 0.093 | **28%** | 74 s |
| XGBoost | 182.03 | **242.52** | 22.99% | **0.184** | 27% | 5 min† |
| Random Forest | 182.83 | 243.75 | 23.06% | 0.176 | 26% | 2 min† |
| MoE XGBoost | 185.48 | 246.85 | 23.42% | 0.154 | 23% | 17 min† |
| UoPC (θ = 500, k = 20) | 198.78 | 276.60 | 23.56% | −0.062 | 8% | 36 s |
| TF-IDF + kNN | 202.07 | 268.37 | 25.37% | 0.001 | 4% | 77 s |
| Embedding + kNN | 205.33 | 272.74 | 25.80% | −0.032 | 0% | 2 min |
| Baseline (window mean) | 205.48 | 269.38 | 25.28% | −0.007 | 0% | 23 s |

† Read every day's preprocessing from the store that the Random Forest (average) run had
just filled ([#213](https://github.com/NatLabRockies/hpc-oda-commons/issues/213)).

**PM100 has the least to learn of the four.** The best model's MAE is 11% below the window
mean's (131 against 148 W per node), and R² is at most 0.18. The models capture 29% of the
headroom on average power and 28% on peak.

**Memorizing is as good as fitting here.** The signature memorizer found an exact match for
87% of PM100's jobs, more than on any other dataset. It is within 1 W of XGBoost's MAE on
average power and has the best MAE and MAPE on peak, though its R² is lower: it misses the
jobs it hasn't seen. XGBoost, Random Forest and MoE XGBoost are within 2 W of each other on
average power and 3.5 W on peak.

**UoPC barely beats the window mean.** Its MAE is 2% and 3% below the baseline's (5% and 8%
of the headroom), the best of the three kNN models, but its RMSE is above the baseline's and
its R² below zero (−0.15 and −0.06). With the authors' vote it was far worse than the mean,
at MAE 180.80 and 237.55 and R² −0.70 and −0.48. That vote breaks ties to the lowest
neighbour, and a PM100 user's jobs vary over hundreds of watts ([#241](https://github.com/NatLabRockies/hpc-oda-commons/issues/241)). Its k = 20
and the median were chosen on F-DATA and not tuned here
([methodology](methodology.md#models-in-scope)).

**Peak is harder than average**, more so than on F-DATA: MAPE is 4–6 points higher for every
model. PM100's peak is the peak of the summed node trace, not F-DATA's per-node peak, so the
two peak tables are not comparable ([methodology](methodology.md#targets)).

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
hpc-oda datasets prepare src/hpc_oda_commons/datasets/descriptors/nlr_<system>.yml
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

### PM100

- **Prepare and embed.** `datasets prepare` took 33 s. `hpc-oda embed` encoded PM100's
  35,470 distinct descriptions in 12 minutes (6.2 GB peak, on the Apple GPU), in a separate
  environment with the `embed` extra
  ([why](../../known-issues.md#note--on-macos-torch-and-xgboost-crash-in-one-process)). The
  embedded table holds the prepared table's 231,238 jobs in the same order, with the same
  power values.
- **A smoke run first.** Each model ran 3 windows and scored the same 2,115 jobs, exactly the
  jobs with power in those windows.
- **One run at a time.** The 16 runs took 64 minutes and peaked at 8.8 GB (embedding + kNN).
  `window_n_jobs` was left at the recipes' default.
- **One commit, one source hash** (20a7ab3) for all sixteen bundles.

Reproduce any row with:

```
hpc-oda datasets prepare src/hpc_oda_commons/datasets/descriptors/pm100.yml
# UoPC and embedding + kNN only, in an environment with the `embed` extra:
hpc-oda embed data/datasets/pm100/data.parquet \
  --out data/windows/pm100_power_embedded/data.parquet \
  --model microsoft/harrier-oss-v1-0.6b --format prose
hpc-oda benchmark src/hpc_oda_commons/recipes/job-power/<model>_rolling_{avg,peak}_pm100.yml
```
