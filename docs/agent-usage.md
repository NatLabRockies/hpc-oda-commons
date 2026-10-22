# Agent Usage Guide

Instructions for AI agents **using** hpc-oda-commons as a tool. If you are
*developing* hpc-oda-commons (changing its code), see
[`CONTRIBUTING.md`](../CONTRIBUTING.md) and
[`docs/architecture.md`](architecture.md) instead.

## Project Overview

**hpc-oda-commons** is a local-first CLI + standards toolkit for HPC Operational Data Analytics (ODA). It discovers, prepares and benchmarks models that predict job runtime and job power, across HPC sites.

## Installation

```bash
pip install -e ".[dev]"
```

See [install](how-to/install.md) for the optional extras.

## Workflow

To benchmark a user's own job data, follow
[Benchmark your own data](how-to/benchmark-your-data.md) step by step. It runs every model
the way the published leaderboard does, and a test keeps its commands working. In short:

```bash
hpc-oda datasets prepare descriptors/<name>.yml --from exports      # read and check the export
hpc-oda datasets characterize data/datasets/<name>/data.parquet \
  --dataset-id dataset.<name> --descriptor dataset.<name> --out benchmark/datasets
hpc-oda recipes write descriptors/<name>.yml \
  --card benchmark/datasets/<name>.card.json --out recipes          # prints embed + ceiling commands
# run the printed embed and ceiling commands, then:
for r in recipes/runtime/*.yml recipes/power/*.yml; do hpc-oda benchmark "$r"; done
hpc-oda leaderboard --runs runs --out leaderboard --ceilings benchmark/datasets --recipes recipes
```

Everything runs locally. For a first look at a Parquet export without writing a descriptor,
`hpc-oda ingest jobs-parquet --path <parquet>` maps it interactively ([Ingesting Parquet
Data](#ingesting-parquet-data)), and `hpc-oda validate` checks the result.

## Key Commands

| Command | What it does |
|---------|-------------|
| `hpc-oda browse`, `hpc-oda info <id>` | List the registry's models, datasets, recipes and adapters; show one |
| `hpc-oda datasets prepare <descriptor>` | Fetch (or, with `--from`, read) a dataset and write its canonical table |
| `hpc-oda recipes write <descriptor> --card <card> --out <dir>` | Every model's recipes for a dataset, on the benchmark's protocol |
| `hpc-oda benchmark <recipe.yml>` | Run one recipe; `-v` prints progress |
| `hpc-oda leaderboard --runs <dir> --out <dir>` | One leaderboard per target, plus a page listing every run |
| `hpc-oda validate <path>` | Check a bundle, manifest or table against its schema |

The [CLI reference](reference/cli.md) lists every command, its options and the environment
variables. Most write under the current directory: `data/`, `runs/`, `leaderboard/`,
`reports/`, all gitignored in a checkout.

## Models and recipes

The [model cards](models/README.md) list every model: what it predicts, the splits it supports,
its settings and its results. Every model predicts the column its recipe's metrics target:
`runtime_seconds` for runtime, or a power column such as `avgpcon_per_node`
([Predict job power](how-to/predict-power.md)).

`hpc-oda browse --type recipe` lists the bundled recipes, and the
[recipes reference](reference/recipes.md) explains every key. For a dataset of your own, let
`hpc-oda recipes write` write the recipes rather than copying them by hand. For a one-off
study, copy a bundled recipe and change it:

```bash
cp src/hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml my_recipe.yml
# Edit my_recipe.yml: the dataset's table_path (and window), the model, the split
hpc-oda benchmark my_recipe.yml
```

## Ingesting Parquet Data

The jobs-parquet ingest uses an interactive wizard that profiles columns, suggests mappings, and asks for timestamp, duration and memory formats. Agents should ask the user to run it:

```bash
hpc-oda ingest jobs-parquet --path /path/to/jobs.parquet
```

It writes a reusable `mapping.yml`. Later ingests of the same layout can run unattended:

```bash
hpc-oda ingest jobs-parquet --path new_data.parquet --mapping data/ingested/jobs_parquet/<prior-run>/mapping.yml --non-interactive
```

See [Ingest jobs Parquet exports](how-to/ingest-jobs-parquet.md). To benchmark the data, a
dataset descriptor is the better route ([Benchmark your own data](how-to/benchmark-your-data.md)).

## Reading Results

A benchmark writes `result.json` (the scores, model, dataset and integrity), `metrics.json`
(per-window detail) and `provenance.json` (the environment, code and input hashes).
[Interpreting results](how-to/interpret-results.md) explains each.

Two results with the same `dataset.hash` used the same input data. Two with the same
`integrity.code_hash` and `validated: true` used identical, test-validated code. Both together
mean the results are fully comparable.
