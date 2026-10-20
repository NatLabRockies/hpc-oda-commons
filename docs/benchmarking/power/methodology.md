# Power-prediction benchmark — methodology & decisions

This is the tracked decision log for the power-prediction benchmark: every model predicting a
job's power on every usable power dataset. It records **what we decided and why**, so the
benchmark is reproducible and our choices are explainable. The numbers live on one page,
[Results](results.md). The decisions were agreed in
[#230](https://github.com/NatLabRockies/hpc-oda-commons/issues/230).

Status: **decision log, error ceilings, four datasets, leaderboard** (#230, #237).

## Models in scope

Eight models, each with its default configuration:

- `job_runtime_baseline` (the window mean);
- `job_runtime_signature_memorizer`;
- `job_runtime_tfidf_knn`;
- `job_runtime_embedding_knn`;
- `job_power_uopc`;
- `job_runtime_xgboost`;
- `job_runtime_random_forest`;
- `job_runtime_moe_xgboost`.

The `job_runtime_*` models predict whatever column their recipe's metrics name, so the same
models serve both tracks ([Predict job power](../../how-to/predict-power.md)).

**UoPC runs at θ = 500, k = 20, with `balanced` features.** k = 20 comes from the θ × k sweep
on F-DATA ([UoPC sweep](uopc.md#sensitivity-sweep-θ--k)). It was chosen there once and is used
on every dataset, not tuned on each dataset's results. On Eagle it scores worse than k = 5,
and that is reported as it is.

**MLP is excluded**, as from the runtime fleet run
([runtime methodology](../runtime/methodology.md#models-in-scope)). It measured weaker than the
other rolling-tabular models across the board on runtime, and on F-DATA it cost ~130 s per
window, over 3 hours per target. `model.job_runtime_mlp` still predicts power when a recipe
names it.

Adding a model to the benchmark is a decision recorded here, not a side effect of writing one.

## Benchmark configuration

One protocol for every dataset:

| Parameter | Value | Meaning |
|---|---|---|
| `n_windows` | 89 | daily test windows, ending at the dataset's last submit |
| `test_window_hours` | 24 | so 89 days of test coverage |
| `training_lookback_days` | 60 | each window retrains on the previous 60 days |

Every model retrains once per window on the same rows and is scored on the same test jobs.

**Why these values.** They are the protocol every power result so far ran on
([#204](https://github.com/NatLabRockies/hpc-oda-commons/issues/204),
[#217](https://github.com/NatLabRockies/hpc-oda-commons/issues/217)), so all existing results
stay valid. On F-DATA they also put the test period within a day of the UoPC paper's, which
starts on 2024-02-01.

**Not an axis yet.** The runtime benchmark runs every model at three lookbacks, because one
fixed value decided which model won ([lookback](../runtime/lookback.md)). Power has not been
measured that way; it is an [open item](#open-items).

**Same rows for everyone.** UoPC needs k training jobs from a user. A user with fewer gets the
window mean, as the baseline would predict, counted in `summary.rows_fallback`. No row the
other models score is dropped.

**This is not UoPC's paper protocol.** The paper scores each job against everything its user
finished before submission. That protocol stays a one-model study,
[UoPC reproduction](uopc.md), because most models in the Commons cannot refit per job.

## Targets

- **Headline: average power per node** (`avgpcon_per_node`), on every dataset.
- **Second table: peak power per node** (`maxpcon_per_node`), only where the source records
  peak (F-DATA and PM100). Peak means different things across sources: F-DATA reports each
  node's own peak, PM100 the peak of the summed trace
  ([power sources](../../datasets/power-sources.md#summary)). Comparing them across datasets
  would compare definitions, not models.
- **Per node the job ran on.** A job's power sums the nodes it ran on, so that is the divisor.
  Each source records it differently:

  | Dataset | Divisor | Why |
  |---|---|---|
  | F-DATA | requested nodes | F-DATA pads its allocated counts: 410,740 one-node jobs record 48. The nodes a job ran on match its request for ~96% of jobs and never match the padded count ([known issues](../../known-issues.md#note--f-datas-allocated-node-counts-can-be-padded), [why](uopc.md#nodes-requested-not-allocated)) |
  | PM100 | allocated nodes | the power trace sums exactly the allocated nodes; they equal the request for 99.92% of jobs |
  | Eagle, Kestrel | nodes used | the energy reading covers the nodes the job used |

  Agreed on #230.
- **Only jobs with a power reading** are trained on and scored. Readings no node could
  produce are nulled per dataset by the descriptor (`trim_quantiles`,
  [known issues](../../known-issues.md#note--eagles-and-kestrels-energy-readings-include-impossible-per-node-power)).

## Ranking

**Models are ranked by MAE within a dataset**, as in the runtime benchmark. RMSE, MAPE and R²
are reported beside it.

- MAE is in watts per node and is what the error ceiling bounds, so it shows how much of the
  available accuracy a model captures.
- MAPE is inflated by small targets: on F-DATA's padded allocations a ~2 W target turned
  small misses into huge percentages.
- R² rewards getting the rare large jobs right and can go below zero while a model is still
  useful on typical jobs.

**Across datasets, MAE is not comparable**: a Fugaku node draws ~90 W and a Kestrel node
~590 W. The cross-dataset view is the share of the available headroom each model captures,
against each dataset's [error ceiling](#error-ceilings).

**The leaderboard** ranks the same way (#237). `hpc-oda leaderboard` has one table each for
average and peak power, with a row per model and a column per dataset showing headroom
captured and the MAE beneath. The average over datasets is shown only for models that ran
on every one. Only bundles of this protocol, from the bundled recipes as they stand today,
count; the rest are listed on `runs.html` with the reason
([reading the leaderboard](../../how-to/interpret-results.md#reading-the-leaderboard)).

## Error ceilings

The runtime benchmark's ceiling, applied to power
([runtime methodology](../runtime/methodology.md#calibrating-the-numbers-the-error-ceiling)).
Jobs whose inputs are identical can't be told apart, so for each dataset and target the
lowest MAE any predictor could reach is that of predicting each group's median. It is exact,
needs no fitting, and is the same on every machine.

**The signature is every input any benchmarked model reads**, not only the shared submission
fields as on runtime. UoPC and embedding + kNN also read a job embedding, and UoPC the
requested frequency. On F-DATA the embedding encodes the job environment; on Eagle and
Kestrel ours encodes the weekday and hour of submission. With a signature that omits them,
those two models could in principle beat the "floor". With every input in it, the floor
bounds all eight models and headroom captured never exceeds 100%. Two jobs share an
embedding only if every element is identical. Agreed on #230.

The cost is a lower, finer floor where the extra inputs carry information. The ceiling file
records each feature's cost, so the floor without the embedding is also on record.

**Headroom captured** = (baseline MAE − model MAE) / (baseline MAE − floor MAE), where the
baseline is the window mean. 0% is the baseline, 100% the floor.

The ceilings use the benchmark's own windows and score exactly its rows: only jobs with a
reading of the target. Results: [How much accuracy is available](results.md#how-much-accuracy-is-available).
Regenerate with:

```
hpc-oda datasets ceiling data/datasets/fdata_fugaku_uopc/data.parquet \
  --target avgpcon_per_node --dataset-id dataset.job_power.fdata_fugaku_uopc \
  --n-windows 89 --test-window-hours 24 --training-lookback-days 60 \
  --extra-feature embedding --extra-feature freq_req \
  --out docs/benchmarking/datasets/fdata_fugaku_uopc.avgpcon_per_node.ceiling.json
```

The same with `--target maxpcon_per_node`, and for Eagle and Kestrel on
`data/windows/nlr_{eagle,kestrel}_power_embedded/data.parquet` (the tables UoPC and
embedding + kNN read) as `nlr_{eagle,kestrel}_power.avgpcon_per_node.ceiling.json`. A field
a table lacks, such as frequency on Eagle, is left out of its signature.

## Window selection

Each dataset has one window, chosen and justified per dataset. The runtime benchmark's rule
(end the window at 80% of the dataset's healthy span) does not apply: F-DATA is pinned to the
UoPC paper's test period, and the NLR systems are chosen against their wind-down.

| Dataset | Test period | Why |
|---|---|---|
| F-DATA | the 89 days to its last submit | it matches the UoPC paper's test period, so the two protocols can be compared |
| Eagle | the last 89 days before its wind-down | its real last 89 days had 122k jobs from 159 users, one with 41.8% |
| Kestrel | its last 89 days | it never wound down. The runtime benchmark's Kestrel window was rejected: one user submitted 59.5% of its jobs with power |
| PM100 | its last 89 days | it is a May–Oct 2020 extract with no wind-down, and only just long enough: 89 test days plus the 60-day lookback need 149 of its ~160 days |

The dates, users and top user's share of each test period are on the
[results page](results.md#datasets). Each window starts 60 days before its test period, for
the training lookback.

### Health gate

Each window must pass the runtime benchmark's missing-block test
([runtime methodology](../runtime/methodology.md#window-selection)): no run of 3 or more
consecutive days with fewer than 5% of the median daily number of submitted jobs. It is run
on the jobs the benchmark uses, those with a power reading, over the whole window: from 60
days before the test period to the last submit.

| Dataset | Jobs with power | Median per day | Missing blocks in the window | Result |
|---|---:|---:|---|---|
| F-DATA | 2,930,414 | 19,847 | 2024-02-10 – 02-12, 2024-04-01 – 04-03 | **fails; kept as an exception** |
| Eagle | 833,525 | 5,071 | none | passes |
| Kestrel | 1,190,332 | 5,173 | none (two before the window, in July 2025) | passes |
| PM100 | 231,238 | 1,161 | 2020-05-14 – 05-18, ending on the window's first day | **fails at the edge; kept as an exception** |

**F-DATA is kept as a recorded exception.** The runtime rule treats outages and lost records
alike, because the two usually can't be told apart. Here they can. On each of the six days
no job was submitted, started, ended *or running*. Lost records would still leave the jobs
that were already running spanning the gap. Before each block the machine drains (on
2024-02-09, 2,652 jobs were submitted and none started), and it ramps back up over a day or
two. These are whole-machine maintenance outages.

What they cost:
- four of the 89 daily windows fall inside the blocks and have no test jobs, so 85 score
  (two windows from 2024-02-09 14:00 UTC and two from 2024-04-01 14:00);
- the windows after each block train on three days fewer.

Shifting the window would lose the comparison with the paper and rerun every F-DATA result.
A deployed predictor would face the same outages. Agreed on #230.

**PM100 is kept as a recorded exception too.** Its window begins at 2020-05-18 04:00 UTC, the
last day of a 5-day missing block. Only the earliest test windows reach back that far, and
they lose part of one training day. The window cannot move: the data ends in October. Three
single test days have no submissions (2020-08-02, 08-03 and 08-09); they are under the 3-day
threshold, so they are not a missing block, and they leave 86 of the 89 windows scoring.
Agreed on #230.

Reproduce the gate from a prepared table:

```python
import pyarrow.compute as pc
import pyarrow.parquet as pq
from hpc_oda_commons.benchmarking.characterize import characterize_table

table = pq.read_table("data/datasets/fdata_fugaku_uopc/data.parquet")
table = table.filter(pc.is_valid(table.column("avgpcon_per_node")))
print(characterize_table(table)["gaps"])  # then keep the blocks inside the window above
```

For Eagle and Kestrel, read the sliced tables in `data/windows/nlr_{eagle,kestrel}_power/`;
for PM100, `data/datasets/pm100/data.parquet`.

## Dataset roster

From the public sources with per-job power ([power sources](../../datasets/power-sources.md)):

- **In:** F-DATA (`fdata_fugaku_uopc`, its five UoPC months), NLR Eagle (`nlr_eagle`) and NLR
  Kestrel (`nlr_kestrel`, CPU nodes, shared nodes excluded).
- **Shared nodes on PM100 are kept.** 5,396 jobs (2.3%) ran on a node at the same time as
  another job, so their node's power includes the other job's. PM100 does not flag them, as
  Kestrel does; they were found by overlapping node lists and run times. At 2.3% they are kept
  and recorded as a limitation, rather than excluded with new code (agreed on #230;
  [known issues](../../known-issues.md#note--pm100-power-includes-co-located-jobs-for-23-of-jobs)).
- **In since #230:** PM100 (`pm100`), with average and peak power: 231k jobs, May–Oct 2020.
- **Waiting on mapping:** Lassen (power needs a join) and Adastra (needs cleaning).
- **Not used:** `nrel_eagle`, the same machine as `nlr_eagle` from another source, as in the
  runtime benchmark. Sources not registered or not usable are listed on the power sources page.

## Reproducibility

- Every result row is a bundled recipe: `recipes/job-power/<model>_rolling_*.yml`.
- A bundle records the code it ran (commit, source hash, and whether the checkout moved,
  [#215](https://github.com/NatLabRockies/hpc-oda-commons/issues/215)). Bundles stay local;
  the results page records each campaign's date, machine and commit.
- **Changing a tracked setting means rerunning what it affects**, not mixing numbers from
  before and after: a model's configuration, the protocol, a target's definition or a
  dataset's window.
- Exact values move across machines (BLAS, thread order; [known issues](../../known-issues.md)),
  so compare within a tolerance.

## Open items

- **A lookback axis**, as in the runtime benchmark.
- **The HPC runner** (`bench-matrix`) is runtime-only; power runs locally from recipes.
