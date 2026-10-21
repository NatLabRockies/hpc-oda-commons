# Benchmarking

The Commons benchmarks models on public HPC operational data, one **track** per prediction
target. Each track has a decision log (what was decided and why), a results page, and the
studies behind them.

## Tracks

### Runtime

Predicting a job's runtime from its submission fields: every runtime model on ~20 datasets.

- [Methodology](runtime/methodology.md): the decision log — models, configuration, window
  selection, dataset roster, error ceilings.
- [Training lookback](runtime/lookback.md): what the 10/30/120-day lookback axis measured.
- [Error ceilings](runtime/ceilings.md): how much accuracy each dataset leaves available.
- [Dataset cards](datasets/): the generated per-dataset windows and ceilings the runner reads.

### Power

Predicting a job's average (and, where recorded, peak) power per node. Becoming a tracked
benchmark ([#230](https://github.com/NatLabRockies/hpc-oda-commons/issues/230)).

- [Methodology](power/methodology.md): the decision log — models, configuration, targets,
  ranking, error ceilings, window selection and its health gate, dataset roster.
- [Results](power/results.md): every model on every power dataset, on one rolling protocol.
- [UoPC reproduction](power/uopc.md): the UoPC paper's own protocol, a one-model study.
- [UoPC audit](power/uopc-audit.md): our UoPC checked against the paper and the authors' code.

## Leaderboards

`hpc-oda leaderboard` builds one table per target from a runs folder: a row per model, an
average, and a column per dataset, each cell the headroom captured against that dataset's
error ceiling ([reading the leaderboard](../how-to/interpret-results.md#reading-the-leaderboard)).

**The published leaderboard** is at <https://natlabrockies.github.io/hpc-oda-commons/leaderboard/>
([#245](https://github.com/NatLabRockies/hpc-oda-commons/issues/245)). It is a snapshot,
`site/leaderboard/`, committed to the repo and deployed by `.github/workflows/pages.yml`
whenever `site/` changes on `main`. CI can't rebuild it, because the result bundles aren't in
the repo. To refresh it after new results:

1. Collect every bundle under one `runs/` folder: the power runs, and the runtime fleet's
   bundles from the cluster (`bench-matrix collect`).
2. Run `hpc-oda leaderboard --runs runs --out site/leaderboard`.
3. Open a PR. The `leaderboard.json` diff shows what changed; a test keeps absolute paths off
   the pages.

## Shared

- [HPC runner](hpc-runner.md): running the benchmark matrix on a Slurm cluster (runtime
  track today).

## Rules for these docs

- **One home per number.** A results table lives only on its track's results page. Other
  pages link to it rather than restate it, except for a study's own results.
- **Links are tested.** `tests/unit/test_doc_links.py` checks every relative link and anchor
  under `docs/`, so a move or rename that breaks one fails CI.
- **New pages go under their track.** A new dataset or model goes on its track's existing
  results page, not on a page of its own.
