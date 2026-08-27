# Training lookback — is one value right for every dataset?

No. This records what the lookback axis measured and what the fixed value cost.

The benchmark used to train every model on a fixed 120-day lookback. Since
[#187](https://github.com/NatLabRockies/hpc-oda-commons/issues/187) each model runs at
`{10d, 30d, 120d}` instead, and [#190](https://github.com/NatLabRockies/hpc-oda-commons/issues/190)
decides which arm a cell is credited with. Regenerate with:

```
hpc-oda bench-matrix rank
```

> **This is not the published leaderboard.** It answers one question — whether a single
> lookback serves every dataset — using a 30-day evaluation that is itself too short
> ([#191](https://github.com/NatLabRockies/hpc-oda-commons/issues/191)). Model rankings appear
> here only as evidence about the parameter.

## No single value serves the fleet

Across 140 cells (20 datasets x 7 models), the walk-forward policy spends its windows almost
evenly across the three arms:

| arm | share of scored windows |
|---|---:|
| 10d | 30% |
| 30d | 29% |
| 120d | 42% |

The old fixed value is the best arm in hindsight for **70 of 140 cells** — exactly half. A
parameter that is right half the time was not measured into place; it was assumed.

## Nor a single value per dataset

The dominant arm varies sharply by machine, which is the result
[#170](https://github.com/NatLabRockies/hpc-oda-commons/issues/170) predicted:

| dataset | 10d | 30d | 120d | dominant | cells that switched arms |
|---|---:|---:|---:|:--:|---:|
| `lassen` | 82% | 2% | 15% | 10d | 3/7 |
| `fresco_anvil` | 78% | 1% | 21% | 10d | 6/7 |
| `nlr_eagle` | 46% | 19% | 34% | 10d | 6/7 |
| `pwa_cea_curie` | 43% | 24% | 33% | 10d | 6/7 |
| `alcf_djc_aurora` | 42% | 42% | 16% | 30d | 5/7 |
| `fresco_stampede1` | 13% | 62% | 25% | 30d | 4/7 |
| `alcf_djc_theta` | 21% | 47% | 32% | 30d | 5/7 |
| `fdata_fugaku` | 21% | 43% | 36% | 30d | 3/7 |
| `pm100` | 28% | 43% | 29% | 30d | 5/7 |
| `pwa_metacentrum` | 6% | 13% | 81% | 120d | 5/7 |
| `pwa_sdsc_blue` | 18% | 16% | 65% | 120d | 6/7 |
| `mit_supercloud` | 15% | 22% | 64% | 120d | 5/7 |
| `alcf_djc_polaris` | 27% | 15% | 57% | 120d | 1/7 |
| `fresco_conte` | 8% | 39% | 52% | 120d | 6/7 |
| `atlas_mustang` | 10% | 39% | 51% | 120d | 7/7 |
| `nlr_kestrel` | 3% | 47% | 50% | 120d | 5/7 |
| `pwa_hpc2n` | 37% | 13% | 50% | 120d | 3/7 |
| `atlas_opentrinity` | 35% | 23% | 42% | 120d | 7/7 |
| `pwa_ricc` | 37% | 23% | 40% | 120d | 7/7 |
| `pwa_kit_fh2` | 25% | 35% | 40% | 120d | 5/7 |

## Nor a single value per cell

The right lookback is not even stable within one model on one machine. **In 100 of 140 cells
the policy switched arms at least once mid-run**, and on `atlas_mustang`, `atlas_opentrinity`
and `pwa_ricc` every one of the seven models switched. Thirty days of evaluation is enough for
the best amount of history to change — which is an argument for treating the lookback as
something a deployed system revisits, not something a benchmark pins once.

## What the fixed value cost

Per cell, the gap between the walk-forward score and the best arm in hindsight:

| | regret |
|---|---:|
| median | 1.5% |
| mean | 4.0% |
| max | 45.7% |

By model — a larger number means that model's arms disagree more over time, so more of its
apparent skill would come from being allowed to choose with hindsight:

| model | mean | median | max |
|---|---:|---:|---:|
| `embedding_knn` | 6.8% | 2.8% | 45.7% |
| `xgboost` | 4.7% | 1.6% | 32.8% |
| `tfidf_knn` | 4.6% | 3.0% | 17.5% |
| `signature_memorizer` | 4.0% | 2.2% | 29.1% |
| `moe_xgboost` | 3.4% | 0.9% | 25.6% |
| `random_forest` | 3.4% | 1.2% | 20.8% |
| `baseline` | 1.5% | 0.1% | 15.9% |

## It decided which model won on 6 of 20 datasets

Comparing "best model by its hindsight-best arm" against "best model by walk-forward score":

| dataset | hindsight winner | walk-forward winner | hindsight margin |
|---|---|---|---:|
| `atlas_opentrinity` | moe_xgboost | xgboost | 0.1% |
| `pwa_cea_curie` | moe_xgboost | signature_memorizer | 0.1% |
| `pwa_ricc` | signature_memorizer | moe_xgboost | 1.3% |
| `nlr_eagle` | xgboost | signature_memorizer | 1.9% |
| `fresco_anvil` | moe_xgboost | xgboost | 4.0% |
| `lassen` | moe_xgboost | signature_memorizer | 5.1% |

**The mechanism is narrow margins, not one model being especially flattered.** Five of the six
races were decided by under 5% in hindsight, and four by under 2% — close enough that the
loser's steadier arms overturn the leader's nominal edge. `moe_xgboost` appears on the losing
side four times because it was the narrow hindsight leader four times, not because its arms are
the least stable: its mean regret (3.4%) is second-lowest of the seven models.

`lassen` is the one flip that is not a photo finish. There `moe_xgboost` carries **25.6%**
regret against `signature_memorizer`'s 1.9% — its arms disagree enough that picking among them
with hindsight was doing most of the work.

## Caveats

- **The evaluation is 30 days.** Too short to contain an allocation cycle or a semester
  boundary, and not fixable by re-ranking ([#191](https://github.com/NatLabRockies/hpc-oda-commons/issues/191)).
- **`atlas_opentrinity`'s 120d arm is not 120 days.** That source holds only 80 days, so its
  longest arm is really "all available history". The arms still separate by training-set size,
  so the comparison is real, but the label is not.
- **`fdata_fugaku` was provisional and no longer is.** When this was first written its
  `xgboost`, `moe_xgboost` and `random_forest` cells had ranked on two arms rather than three,
  the 120d arm still running. All 420 cells have since completed with no failures, and the
  re-ranked fleet reproduces every number above: the same six flips, the same regret
  distribution, and no dataset whose winner moved. Fugaku itself does not flip — `xgboost`
  wins it under both rules at 6,711, and its walk-forward score *equals* its oracle, so the
  policy chose the best arm at every scored window there.
- Fitted-model metrics are not byte-stable across machines (`docs/known-issues.md`), so small
  differences between reruns of the same cell are expected. The findings above rest on
  differences much larger than that.
