# Benchmarking

The Commons benchmarks models on public HPC operational data, one **track** per prediction
target. Each track has a decision log (what was decided and why) and the studies behind it.
The results live on the [published leaderboard](https://natlabrockies.github.io/hpc-oda-commons/leaderboard/)
and the generated [model](../models/README.md) and [dataset](../datasets/cards/README.md)
cards; the power track also has a results page with the narrative.

## Tracks

### Runtime

Predicting a job's runtime from its submission fields. The leaderboard scores the last 30
days of each dataset's test period today; the cards and `bench-matrix` are sized for 90, which
[#191](https://github.com/NatLabRockies/hpc-oda-commons/issues/191) will run
([methodology](runtime/methodology.md#benchmark-configuration)).

- [Methodology](runtime/methodology.md): the decision log — models, configuration, window
  selection, dataset roster, error ceilings.
- [Training lookback](runtime/lookback.md): what the 10/30/120-day lookback axis measured.
- [Error ceilings](runtime/ceilings.md): how much accuracy each dataset leaves available.
- [Dataset cards](../datasets/cards/README.md): every dataset's source, curation,
  characterization, windows, ceilings and results, generated. Their runtime cards and
  ceilings are in [`datasets/`](datasets/): `bench-matrix` reads the windows, and the
  leaderboard the ceilings and the roster.

### Power

Predicting a job's average (and, where recorded, peak) power per node, with a table per
target on the leaderboard.

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
3. Run `hpc-oda models cards` and `hpc-oda datasets cards`. The [model
   cards](../models/README.md) and [dataset cards](../datasets/cards/README.md) carry the
   results, so they are regenerated from the new leaderboard; a test fails if they're stale.
4. Open a PR. The `leaderboard.json` diff shows what changed; a test keeps absolute paths off
   the pages.

To run the benchmark on a dataset of your own, with a private leaderboard and card, see
[Benchmark your own data](../how-to/benchmark-your-data.md).

## Shared

- [HPC runner](hpc-runner.md): running the benchmark matrix on a Slurm cluster (runtime
  track today).

## Rules for these docs

- **One home per number.** Results live on the leaderboard and the generated cards, and a
  study keeps only its own numbers. Other pages link rather than restate them.
- **Links are tested.** `tests/unit/test_doc_links.py` checks every relative link and anchor
  under `docs/`, so a move or rename that breaks one fails CI.
- **New pages go under their track.** A new dataset or model goes on its track's existing
  results page, not on a page of its own.
