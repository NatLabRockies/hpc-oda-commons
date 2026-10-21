# Predict job power with any model

Every runtime-prediction model can predict job power instead: same model, same rolling
evaluation, different target ([#204](https://github.com/NatLabRockies/hpc-oda-commons/issues/204)).
This page shows how, and what is guaranteed along the way.

## The target is the recipe's metric target

A model predicts the column its recipe's metrics name:

```yaml
model:
  id: model.xgboost
  version: "0.1.0"

metrics:
  - name: mae
    target: avgpcon_per_node   # the model predicts this column
  - name: rmse
    target: avgpcon_per_node
```

- All metrics must share one target; that column is what the model is trained and scored
  on. It is recorded as `run_config.target_field` in the result bundle.
- `runtime_seconds` is the default, so existing runtime recipes behave exactly as before.
- **A target the model cannot predict is an error, not a label.** The fixed UoPC adaptation
  only predicts `maxpcon`, and the UoPC paper protocol only the two per-node targets; naming
  anything else fails before the model runs. (Before #204 a metric's target was only a
  label, so a recipe could report runtime errors under a power name.)
- **The target is never a feature.** Features come from one submit-time allowlist
  (`models/feature_policy.py`) that excludes runtime, power and energy columns whatever
  the target. Naming the target in `extra_feature_fields`, or as the embedding column, is
  an error.

Supported by `model.baseline`, `_xgboost`, `_random_forest`, `_mlp`,
`_moe_xgboost`, `_signature_memorizer`, `_tfidf_knn` and `_embedding_knn`. The model ids
still say `job_runtime`; they are target-agnostic.

## Per-node power

The power targets are **watts per node**: `avgpcon_per_node` (average) and
`maxpcon_per_node` (peak). They are computed once, when a dataset is prepared, so every
model reads the same column:

```yaml
# in a dataset descriptor's mapping (PM100)
avgpcon_per_node: { derive: "avgpcon / num_nodes_alloc" }
maxpcon_per_node: { derive: "maxpcon / num_nodes_alloc" }
```

`derive: "<field> / <field>"` divides two other mapped fields after their own transforms.
A job with a zero or missing node count gets null, never an infinite target, and drops out
of scoring. `trim_quantiles: [0.001, 0.999]` nulls the outer 0.1% of a target at each end,
for sources with impossible readings such as Eagle's
([ingest how-to](ingest-jobs-parquet.md), #216).

**Which node count.** Divide by the nodes the power was summed over. For PM100 that is the
allocated nodes. For F-DATA it is the **requested** nodes (`num_nodes_req`): Fugaku's
allocated count (`nnuma`) can be padded past the nodes a job runs on, while its power sums
only those. In the UoPC test months, 137k jobs (8.6%) request 1 node and 48 cores but show
`nnuma` = 48, and their ~91 W would read as 1.9 W per allocated node. The UoPC paper
divides by `nnuma`. Our [paper reproduction](../benchmarking/power/uopc.md#nodes-requested-not-allocated)
divides by requested nodes, and keeps the paper's divisor only for comparison.

## Datasets with power

| Dataset | Window | Power columns |
|---|---|---|
| `dataset.fdata_fugaku` | Fugaku, Mar–Sep 2023 and Dec 2023–Apr 2024 | `avgpcon`, `maxpcon`, per node, plus F-DATA's job `embedding`; rows filtered on runtime only |
| `dataset.pm100` | Marconi100, May–Oct 2020 | mean and peak of the job's node-power trace, per node; rows filtered on runtime only |
| `dataset.nlr_eagle` | Eagle, 2018-11 to 2024-06 | average only: the job's node energy over its runtime, per node used; rows filtered on runtime only |
| `dataset.nlr_kestrel` | Kestrel, 2023-08 to 2025-12 | average only, CPU nodes: Slurm job energy over runtime, per node used; null for jobs that shared their node and for GPU jobs (no energy); rows filtered on runtime only |

Sources that record power as a trace of samples are reduced with `type: list_mean` or
`type: list_max`. Sources that record energy instead convert it with `type: energy` and
divide by runtime (Eagle). Adastra records per-node job energy that is not mapped yet (it
needs near-zero readings treated as missing,
[#207](https://github.com/NatLabRockies/hpc-oda-commons/issues/207)); see [curation status](../datasets/curation-status.md#power-columns) and the
[power sources audit](../datasets/power-sources.md).

## Run it

```bash
hpc-oda datasets prepare src/hpc_oda_commons/datasets/descriptors/fdata_fugaku.yml
hpc-oda benchmark src/hpc_oda_commons/recipes/job-power/xgboost_rolling_avg.yml
hpc-oda leaderboard --runs runs --out leaderboard
```

`recipes/job-power/<model>_rolling_{avg,peak}.yml` exist for eight models, UoPC
included (all but MLP, which is left out of the benchmark as it is for runtime), on one
shared protocol (89 daily windows from ~2024-02-01, 60 days of lookback,
MAE/RMSE/MAPE/R²). Rolling recipes may report `mape` and `r2`; they are computed over all
scored rows (arm ranking still refuses to pool them from windows).

On Eagle and Kestrel, `recipes/job-power/<model>_rolling_avg_{eagle,kestrel}.yml` run the
same eight models on the same split shape, average power only. The split tests the days before
a table's last submit, so each table is cut to its benchmark period first, keeping every job
that overlaps it:

```bash
hpc-oda datasets prepare src/hpc_oda_commons/datasets/descriptors/nlr_eagle.yml
hpc-oda datasets slice data/datasets/nlr_eagle/data.parquet \
  --start 2023-05-01 --end 2023-09-30 --out data/windows/nlr_eagle_power/data.parquet
hpc-oda benchmark src/hpc_oda_commons/recipes/job-power/xgboost_rolling_avg_eagle.yml
```

Neither source has a job embedding, so UoPC and embedding kNN read the slice with one
computed by `hpc-oda embed`. Run that step in a separate environment with the `embed`
extra ([why](../known-issues.md#note--on-macos-torch-and-xgboost-crash-in-one-process)).
Each recipe's header gives its system's slice, and its embed step if it has one. Results are in
[Power prediction on Eagle and Kestrel](../benchmarking/power/results.md#eagle-and-kestrel).

On PM100, `recipes/job-power/<model>_rolling_{avg,peak}_pm100.yml` run them on both targets.
PM100's prepared table needs no slice; UoPC and embedding kNN read it with an embedding added
(`data/windows/pm100_power_embedded/`). Results: [PM100](../benchmarking/power/results.md#pm100).

The leaderboard has one table per target, so runtime and power results in one runs folder
are never ranked against each other. Each power cell is headroom captured against the
dataset's error ceiling, with the MAE in W/node beneath
([reading the leaderboard](interpret-results.md#reading-the-leaderboard)).

## UoPC on the same windows

`model.uopc` with `split.method: rolling` scores UoPC on exactly the windows and
rows the other models are scored on. A test job's context is its user's newest `theta`
training-window jobs; features are scaled on training rows only. A user with fewer than `k`
training jobs gets the window's mean target (the rolling baseline's prediction), counted in
`summary.rows_fallback`, so no row the other models score is dropped. The paper's own
date-cutoff protocol is described in [UoPC reproduction](../benchmarking/power/uopc.md).

Results for all models: [Power prediction benchmark](../benchmarking/power/results.md).
