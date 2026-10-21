# Quickstart

Five minutes, no data of your own: install the toolkit, look around, and run a model on a
bundled synthetic dataset.

## 1. Install

```bash
pip install -e ".[dev]"
```

See [install](install.md) for the extras (`embed`, `torch`, `faiss`).

## 2. Look around

```bash
hpc-oda browse                    # the models, recipes and datasets
hpc-oda info model.xgboost        # one entry
```

Each model has a [card](../models/README.md), and each dataset too:
[dataset cards](../datasets/cards/README.md). Both are generated from the code and the
results.

## 3. Run a model

```bash
HPC_ODA_OFFLINE=1 hpc-oda run-baseline
```

This runs the baseline model, which predicts the training mean, on a tiny synthetic dataset and writes a result bundle
under `runs/`. [Interpret results](interpret-results.md) explains what's in it.

## 4. Build a leaderboard

```bash
hpc-oda leaderboard --runs runs --out leaderboard
```

This writes `leaderboard/index.html`, with one table per prediction target, and
`leaderboard/runs.html`, which lists every run. The demo run isn't on the benchmark's
protocol, so it shows on `runs.html` only, with the reason
([reading the leaderboard](interpret-results.md#reading-the-leaderboard)).

## Next

- **Benchmark your own data:** [Benchmark your own data](benchmark-your-data.md) runs every
  model on your jobs, the way the
  [published leaderboard](https://natlabrockies.github.io/hpc-oda-commons/leaderboard/) runs
  them.
- **Predict power:** [Predict job power](predict-power.md).
- **See the published results:** [Benchmarking](../benchmarking/README.md).
