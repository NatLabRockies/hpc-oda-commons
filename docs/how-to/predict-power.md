# Predict job power with any model

Every runtime-prediction model can predict job power instead: same model, same rolling
evaluation, different target ([#204](https://github.com/NatLabRockies/hpc-oda-commons/issues/204)).
This page shows how, and what is guaranteed along the way.

## The target is the recipe's metric target

A model predicts the column its recipe's metrics name:

```yaml
model:
  id: model.job_runtime_xgboost
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

Supported by `model.job_runtime_baseline`, `_xgboost`, `_random_forest`, `_mlp`,
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
of scoring.

**Which node count.** Divide by the nodes the power was summed over. For PM100 that is the
allocated nodes. For F-DATA it is the **requested** nodes (`num_nodes_req`): Fugaku's
allocated count (`nnuma`) can be padded past the nodes a job runs on, while its power sums
only those. In the UoPC test months, 137k jobs (8.6%) request 1 node and 48 cores but show
`nnuma` = 48, and their ~91 W would read as 1.9 W per allocated node. The UoPC paper
divides by `nnuma`, so the [paper reproduction](../benchmarking/uopc.md) still does.

## Datasets with power

| Dataset | Window | Power columns |
|---|---|---|
| `dataset.job_power.fdata_fugaku_uopc` | Fugaku, Dec 2023–Apr 2024 | `avgpcon`, `maxpcon`, per node, plus F-DATA's job `embedding` |
| `dataset.job_runtime.fdata_fugaku` | Fugaku, Mar–Sep 2023 (the runtime benchmark window) | `avgpcon`, `maxpcon`, per node; rows filtered on runtime only |
| `dataset.job_runtime.pm100` | Marconi100, May–Oct 2020 | mean and peak of the job's node-power trace, per node; rows filtered on runtime only |
| `dataset.job_runtime.nlr_eagle` | Eagle, 2018-11 to 2024-06 | average only: the job's node energy over its runtime, per node used; rows filtered on runtime only |
| `dataset.job_runtime.nlr_kestrel` | Kestrel, 2023-08 to 2025-12 | average only, CPU nodes: Slurm job energy over runtime, per node used; null for jobs that shared their node and for GPU jobs (no energy); rows filtered on runtime only |

Sources that record power as a trace of samples are reduced with `type: list_mean` or
`type: list_max`. Sources that record energy instead convert it with `type: energy` and
divide by runtime (Eagle). Adastra records per-node job energy that is not mapped yet (it
needs near-zero readings treated as missing,
[#207](https://github.com/NatLabRockies/hpc-oda-commons/issues/207)); see [curation status](../datasets/curation-status.md#power-columns) and the
[power sources audit](../datasets/power-sources.md).

## Run it

```bash
hpc-oda datasets prepare src/hpc_oda_commons/datasets/descriptors/job-power/fdata_fugaku_uopc.yml
hpc-oda benchmark src/hpc_oda_commons/recipes/job-power/xgboost_rolling_avg.yml
hpc-oda leaderboard --runs runs --out leaderboard
```

`recipes/job-power/<model>_rolling_{avg,peak}.yml` exist for all nine models, UoPC
included, on one shared protocol (89 daily windows from ~2024-02-01, 60 days of lookback,
MAE/RMSE/MAPE/R²). Rolling recipes may report `mape` and `r2`; they are computed over all
scored rows (arm ranking still refuses to pool them from windows).

The leaderboard shows power errors in W/node and picks the best value of each metric per
target, so runtime and power results in one runs folder are never ranked against each
other.

## UoPC on the same windows

`model.job_power_uopc` with `split.method: rolling` scores UoPC on exactly the windows and
rows the other models are scored on. A test job's context is its user's newest `theta`
training-window jobs; features are scaled on training rows only. A user with fewer than `k`
training jobs gets the window's mean target (the rolling baseline's prediction), counted in
`summary.rows_fallback`, so no row the other models score is dropped. The paper's own
date-cutoff protocol is described in [UoPC reproduction](../benchmarking/uopc.md).

Results for all models: [Power prediction benchmark](../benchmarking/power.md).
