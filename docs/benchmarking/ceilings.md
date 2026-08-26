# Error ceilings — how much accuracy was available

Per-dataset floors for the runtime-prediction benchmark: **the minimum error any predictor
restricted to submit-time features could achieve.** Jobs whose features are identical cannot
be told apart, so the best possible prediction per signature is its group median (for MAE) or
mean (for RMSE). See [`methodology.md`](methodology.md) for the definition and
[#169](https://github.com/NatLabRockies/hpc-oda-commons/issues/169) for what is deliberately
excluded.

Machine-readable form: `datasets/<dataset>.ceiling.json`, regenerable with

```
hpc-oda datasets ceiling <windowed-parquet> --dataset-id <ds> \
  --out docs/benchmarking/datasets/<ds>.ceiling.json
```

Unlike the fitted-model metrics, these involve no fitting and no BLAS, so they are byte-stable
across machines: a diff means a real change.

Model numbers below come from the fleet run of 2026-08-25 (plan `20260825-134838`), which is
not itself tracked; regenerate them with `bench-matrix aggregate`.

## Floor vs. achieved

"Headroom captured" is `(baseline − best model) / (baseline − floor)` — the share of the
available accuracy the best model actually got.

| dataset | scored rows | signatures | floor MAE | baseline | best model | captured |
|---|---:|---:|---:|---:|---:|---:|
| `pwa_hpc2n` | 8,457 | 461 | 4,632 | 25,561 | 5,821 (moe_xgboost) | **94%** |
| `pwa_ricc` | 117,639 | 770 | 4,446 | 17,287 | 5,976 (moe_xgboost) | **88%** |
| `atlas_opentrinity` | 9,963 | 734 | 1,644 | 9,015 | 2,563 (moe_xgboost) | **88%** |
| `alcf_djc_theta` | 4,967 | 523 | 779 | 4,499 | 1,324 (moe_xgboost) | **85%** |
| `fresco_anvil` | 121,886 | 3,870 | 2,383 | 8,728 | 3,472 (moe_xgboost) | **83%** |
| `pm100` | 45,181 | 1,594 | 2,913 | 8,743 | 4,006 (moe_xgboost) | **81%** |
| `pwa_sdsc_blue` | 11,586 | 766 | 784 | 4,484 | 1,508 (moe_xgboost) | **80%** |
| `fresco_conte` | 57,030 | 858 | 5,515 | 15,114 | 7,545 (moe_xgboost) | **79%** |
| `fresco_stampede1` | 103,064 | 4,574 | 7,719 | 21,901 | 10,771 (moe_xgboost) | **78%** |
| `atlas_mustang` | 14,974 | 767 | 2,816 | 9,801 | 4,594 (moe_xgboost) | **75%** |
| `alcf_djc_aurora` | 28,248 | 3,912 | 1,989 | 6,521 | 3,207 (moe_xgboost) | **73%** |
| `pwa_metacentrum` | 308,435 | 1,790 | 9,796 | 16,600 | 11,704 (moe_xgboost) | **72%** |
| `pwa_kit_fh2` | 6,739 | 450 | 8,391 | 24,865 | 13,091 (moe_xgboost) | **71%** |
| `alcf_djc_polaris` | 23,895 | 1,809 | 2,310 | 6,662 | 3,558 (moe_xgboost) | **71%** |
| `pwa_cea_curie` | 45,255 | 2,553 | 3,683 | 9,943 | 5,494 (moe_xgboost) | **71%** |
| `fdata_fugaku` | 988,236 | 140,675 | 2,809 | 14,801 | 7,163 (xgboost) | **64%** |
| `nlr_eagle` | 328,566 | 2,699 | 2,776 | 10,947 | 6,173 (moe_xgboost) | **58%** |
| `lassen` | 77,876 | 719 | 1,940 | 5,952 | 3,833 (random_forest) | **53%** |
| `mit_supercloud` | 32,278 | 913 | 20,079 | 41,057 | 30,016 (moe_xgboost) | **53%** |
| `nlr_kestrel` | 254,338 | 4,451 | 7,347 | 16,380 | 11,731 (moe_xgboost) | **51%** |

Median captured: **75%**. Note the ordering inverts the raw leaderboard — a low MAE can mean an
easy dataset rather than a good model.

## How tight is each bound?

A floor is only as meaningful as the groups behind it: refine the signature far enough and
every row is alone, at which point the floor is zero and says nothing. Rows alone in their
signature are rows the bound cannot constrain.

| dataset | group size min / median / max | rows alone in their signature |
|---|---|---:|
| `alcf_djc_aurora` | 1 / 2 / 797 | 5.5% |
| `alcf_djc_polaris` | 1 / 2 / 6,309 | 3.1% |
| `alcf_djc_theta` | 1 / 3 / 438 | 3.5% |
| `atlas_mustang` | 1 / 2 / 4,828 | 2.1% |
| `atlas_opentrinity` | 1 / 2 / 2,062 | 2.9% |
| `fdata_fugaku` | 1 / 1 / 138,912 | 12.5%  ⚠️ loose |
| `fresco_anvil` | 1 / 2 / 50,755 | 1.3% |
| `fresco_conte` | 1 / 4 / 5,342 | 0.3% |
| `fresco_stampede1` | 1 / 4 / 4,857 | 1.0% |
| `lassen` | 1 / 6 / 28,287 | 0.2% |
| `mit_supercloud` | 1 / 4 / 7,122 | 0.8% |
| `nlr_eagle` | 1 / 3 / 141,740 | 0.3% |
| `nlr_kestrel` | 1 / 3 / 11,840 | 0.6% |
| `pm100` | 1 / 3 / 9,438 | 1.1% |
| `pwa_cea_curie` | 1 / 3 / 3,166 | 1.8% |
| `pwa_hpc2n` | 1 / 3 / 1,040 | 1.5% |
| `pwa_kit_fh2` | 1 / 3 / 1,064 | 1.9% |
| `pwa_metacentrum` | 1 / 2 / 66,077 | 0.2% |
| `pwa_ricc` | 1 / 3 / 37,081 | 0.2% |
| `pwa_sdsc_blue` | 1 / 2 / 1,030 | 2.5% |

`fdata_fugaku` is the one loose bound in the fleet: 12.5% of its rows are alone in their
signature, because its `name` column pushes the signature count to six figures. Its floor
should be read as an optimistic bound rather than a tight one.

## Causal memorization

A *measured strategy*, not a bound: predict from same-signature jobs that finished strictly
earlier. Coverage is the share of scored rows whose signature had been seen at all.

| dataset | 1d | 10d | 30d | 60d | 120d | all | best | coverage | vs. best model |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|:--:|
| `alcf_djc_aurora` | 3,572 | 3,420 | 3,306 | **3,298** | 3,451 | 3,452 | 60d | 78% | model |
| `alcf_djc_polaris` | 3,705 | 3,778 | 3,736 | 3,629 | **3,345** | 3,367 | 120d | 89% | **memorization** |
| `alcf_djc_theta` | 2,366 | 1,618 | 1,505 | 1,488 | 1,481 | **1,466** | all | 87% | model |
| `atlas_mustang` | 6,048 | 5,224 | 5,057 | **4,661** | 4,709 | 4,699 | 60d | 90% | model |
| `atlas_opentrinity` | 4,681 | 2,631 | **2,624** | 2,800 | 2,785 | 2,785 | 30d | 69% | model |
| `fdata_fugaku` | 8,998 | 7,970 | **7,396** | 7,401 | 7,410 | 7,411 | 30d | 73% | model |
| `fresco_anvil` | 3,880 | **3,508** | 4,024 | 3,852 | 3,556 | 3,555 | 10d | 91% | model |
| `fresco_conte` | 9,200 | 8,416 | 7,845 | 8,097 | **7,673** | 7,691 | 120d | 97% | model |
| `fresco_stampede1` | 13,530 | 10,863 | 10,922 | 11,004 | **10,847** | 10,913 | 120d | 91% | model |
| `lassen` | 3,665 | **3,505** | 4,208 | 4,371 | 4,391 | 4,364 | 10d | 79% | **memorization** |
| `mit_supercloud` | **29,684** | 33,719 | 32,875 | 33,179 | 33,042 | 33,001 | 1d | 71% | **memorization** |
| `nlr_eagle` | 7,464 | **5,277** | 6,350 | 6,401 | 6,891 | 7,331 | 10d | 81% | **memorization** |
| `nlr_kestrel` | 13,472 | 11,103 | **10,687** | 10,697 | 10,954 | 11,117 | 30d | 71% | **memorization** |
| `pm100` | 4,292 | 3,918 | 3,879 | 3,881 | **3,814** | 3,814 | 120d | 90% | **memorization** |
| `pwa_cea_curie` | 6,258 | **5,072** | 5,330 | 5,209 | 5,185 | 5,194 | 10d | 81% | **memorization** |
| `pwa_hpc2n` | 9,883 | 6,790 | 6,889 | 7,124 | 6,591 | **6,512** | all | 81% | model |
| `pwa_kit_fh2` | 16,814 | 13,521 | 12,984 | **12,741** | 12,831 | 12,838 | 60d | 85% | **memorization** |
| `pwa_metacentrum` | 13,708 | 12,835 | 12,233 | 11,968 | **11,926** | 12,065 | 120d | 95% | model |
| `pwa_ricc` | 7,808 | 5,563 | **5,455** | 5,540 | 5,698 | 5,698 | 30d | 80% | **memorization** |
| `pwa_sdsc_blue` | 2,387 | 1,799 | 1,738 | 1,701 | **1,671** | 1,683 | 120d | 88% | model |

**Memorization beats all six fitted models on 9 of 20 datasets** — see
[#171](https://github.com/NatLabRockies/hpc-oda-commons/issues/171).

Optimal lookback: 1d ×1, 10d ×4, 30d ×4, 60d ×3, 120d ×6, all ×2. The benchmark fixes
`training_lookback_days: 120` for every dataset, which is optimal for 6 of
20 — see [#170](https://github.com/NatLabRockies/hpc-oda-commons/issues/170).

