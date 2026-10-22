# Predict job power with any model

Every model can predict job power as well as runtime: same model, same rolling
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

Supported by `model.baseline`, `model.xgboost`, `model.random_forest`, `model.mlp`,
`model.moe_xgboost`, `model.signature_memorizer`, `model.tfidf_knn` and
`model.embedding_knn`. UoPC (`model.uopc`) predicts power only.

To run every power model on your own data, on the benchmark's protocol, see
[Benchmark your own data](benchmark-your-data.md).

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
([descriptor reference](../reference/descriptors.md#mapping-rules), #216).

**Which node count.** Divide by the nodes the power was summed over. For PM100 that is the
allocated nodes. For F-DATA it is the **requested** nodes (`num_nodes_req`): Fugaku's
allocated count (`nnuma`) can be padded past the nodes a job runs on, while its power sums
only those, so dividing by `nnuma` understates many jobs' power several-fold. The UoPC
paper divides by `nnuma`. Our [paper reproduction](../benchmarking/power/uopc.md#nodes-requested-not-allocated)
divides by requested nodes, and keeps the paper's divisor only for comparison.

## Datasets with power

Four bundled datasets carry a power target. Each one's
[dataset card](../datasets/cards/README.md) gives its span, its power columns and how they were
derived, and its results: F-DATA (Fugaku), PM100 (Marconi100), NLR Eagle and NLR Kestrel.

Sources that record power as a trace of samples are reduced with `type: list_mean` or
`type: list_max`. Sources that record energy instead convert it with `type: energy` and
divide by runtime (Eagle, Kestrel). Adastra records per-node job energy that is not mapped yet
(it needs near-zero readings treated as missing,
[#207](https://github.com/NatLabRockies/hpc-oda-commons/issues/207)); see the
[power sources audit](../datasets/power-sources.md).

## Run it

```bash
hpc-oda datasets prepare src/hpc_oda_commons/datasets/descriptors/fdata_fugaku.yml
hpc-oda benchmark src/hpc_oda_commons/recipes/job-power/xgboost_rolling_avg.yml
hpc-oda leaderboard --runs runs --out leaderboard
```

`recipes/job-power/` holds every model's power recipes except MLP's, which has none, on one
shared protocol ([power methodology](../benchmarking/power/methodology.md#benchmark-configuration)):

- `<model>_rolling_{avg,peak}.yml` on F-DATA;
- `<model>_rolling_avg_{eagle,kestrel}.yml` on Eagle and Kestrel, average power only;
- `<model>_rolling_{avg,peak}_pm100.yml` on PM100.

The recipes read the prepared tables directly. Those on F-DATA, Eagle and Kestrel declare
the days they read (`dataset.window`); PM100's read the whole table. The two embedding models
are the exception where a source has no job embedding (Eagle, Kestrel, PM100): they read a
copy of the table with an embedding added by `hpc-oda embed`. Each such recipe's header gives the slice and embed commands. Run the embed
step in a separate environment with the `embed` extra
([why](../known-issues.md#note--on-macos-torch-and-xgboost-crash-in-one-process)).

Rolling recipes may report `mape` and `r2` as well as MAE and RMSE; they are computed over all
scored rows. Results are in [the power benchmark](../benchmarking/power/results.md).

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
