# Error ceilings — how much accuracy is available

Per-dataset floors for the runtime-prediction benchmark: **the minimum error any predictor
restricted to submit-time features could achieve.** Jobs whose features are identical cannot
be told apart, so the best possible prediction per signature is its group median (for MAE) or
mean (for RMSE). See [`methodology.md`](methodology.md) for the definition and
[#169](https://github.com/NatLabRockies/hpc-oda-commons/issues/169) for what is deliberately
excluded.

Machine-readable form: `docs/benchmarking/datasets/<dataset>.ceiling.json`, regenerable with

```
hpc-oda datasets ceiling <windowed-parquet> --dataset-id <ds> \
  --n-windows 120 --skip-windows 20 \
  --out docs/benchmarking/datasets/<ds>.ceiling.json
```

The tables below were computed this way on 2026-10-21, on the slices the runtime fleet of
2026-08-26 ran on: its 120 × 6 h windows, past the 20-window walk-forward burn-in. When a fleet
runs the cards' 90 days ([#191](https://github.com/NatLabRockies/hpc-oda-commons/issues/191)),
`--card` takes the window count from the card's `test_days` instead.
`--skip-windows` (default 20) leaves the walk-forward burn-in unscored. Only windows that hold
jobs count towards it, as in walk-forward, so the floor covers exactly the jobs a leaderboard
cell is scored on ([#238](https://github.com/NatLabRockies/hpc-oda-commons/issues/238)). No training lookback is involved: the floor
and the feature costs use only the scored jobs, and causal memorization sweeps its own.

These involve no fitting and no BLAS, so unlike the fitted-model metrics they are byte-stable
across machines: a diff means a real change.

> **No model scores here.** They are deliberately absent so this file cannot go stale —
> compare against them on the leaderboard (`hpc-oda leaderboard`, `bench-matrix aggregate`).
> The floors depend only on which jobs are scored, which is set by the fleet's windows.

## The floor, per dataset

| dataset | scored rows | signatures | floor MAE | floor RMSE |
|---|---:|---:|---:|---:|
| `alcf_djc_aurora` | 22,753 | 3,220 | 1,905 | 10,270 |
| `alcf_djc_polaris` | 15,081 | 1,577 | 2,556 | 12,509 |
| `alcf_djc_theta` | 4,106 | 443 | 828 | 3,544 |
| `atlas_mustang` | 13,407 | 665 | 2,090 | 7,388 |
| `atlas_opentrinity` | 8,413 | 613 | 1,678 | 10,727 |
| `fdata_fugaku` | 854,381 | 123,447 | 2,743 | 12,909 |
| `fresco_anvil` | 115,442 | 3,596 | 2,045 | 14,027 |
| `fresco_conte` | 49,437 | 754 | 4,870 | 32,976 |
| `fresco_stampede1` | 86,911 | 3,822 | 7,414 | 21,591 |
| `lassen` | 65,193 | 633 | 1,609 | 3,956 |
| `mit_supercloud` | 29,194 | 775 | 17,251 | 56,908 |
| `nlr_eagle` | 262,472 | 2,262 | 2,554 | 15,484 |
| `nlr_kestrel` | 214,640 | 3,840 | 7,633 | 23,154 |
| `pm100` | 40,395 | 1,456 | 2,818 | 9,373 |
| `pwa_cea_curie` | 38,407 | 2,126 | 3,492 | 10,876 |
| `pwa_hpc2n` | 7,293 | 426 | 3,294 | 17,919 |
| `pwa_kit_fh2` | 5,748 | 393 | 7,115 | 22,856 |
| `pwa_metacentrum` | 273,407 | 1,632 | 9,876 | 74,146 |
| `pwa_ricc` | 110,254 | 664 | 4,084 | 19,067 |
| `pwa_sdsc_blue` | 9,879 | 640 | 696 | 3,875 |

A model's MAE is only interpretable against these. A low score can mean an easy dataset rather
than a good model.

## How tight is each bound?

A floor is only as meaningful as the groups behind it: refine the signature far enough and
every row is alone, at which point the floor is zero and says nothing. Rows alone in their
signature are rows the bound cannot constrain.

| dataset | group size min / median / max | rows alone in their signature |
|---|---|---:|
| `alcf_djc_aurora` | 1 / 2 / 788 | 5.7% |
| `alcf_djc_polaris` | 1 / 2 / 825 | 4.0% |
| `alcf_djc_theta` | 1 / 3 / 367 | 3.5% |
| `atlas_mustang` | 1 / 2 / 4,821 | 2.0% |
| `atlas_opentrinity` | 1 / 2 / 1,839 | 2.9% |
| `fdata_fugaku` | 1 / 1 / 138,912 | 12.6%  ⚠️ loose |
| `fresco_anvil` | 1 / 2 / 50,755 | 1.3% |
| `fresco_conte` | 1 / 5 / 5,342 | 0.4% |
| `fresco_stampede1` | 1 / 4 / 4,857 | 1.0% |
| `lassen` | 1 / 6 / 23,102 | 0.2% |
| `mit_supercloud` | 1 / 4 / 6,661 | 0.7% |
| `nlr_eagle` | 1 / 3 / 114,560 | 0.3% |
| `nlr_kestrel` | 1 / 3 / 11,840 | 0.6% |
| `pm100` | 1 / 3 / 7,284 | 1.1% |
| `pwa_cea_curie` | 1 / 3 / 3,166 | 1.7% |
| `pwa_hpc2n` | 1 / 3 / 1,040 | 1.6% |
| `pwa_kit_fh2` | 1 / 3 / 1,008 | 1.9% |
| `pwa_metacentrum` | 1 / 2 / 66,077 | 0.2% |
| `pwa_ricc` | 1 / 3 / 37,081 | 0.2% |
| `pwa_sdsc_blue` | 1 / 2 / 943 | 2.5% |

`fdata_fugaku` is the one loose bound in the fleet: 12.5% of its rows are alone in their
signature, because its `name` column pushes the signature count to six figures. Its floor
should be read as optimistic rather than tight.

## Causal memorization

A *measured strategy*, not a bound: predict from same-signature jobs that finished strictly
earlier. Coverage is the share of scored rows whose signature had been seen at all.

| dataset | 1d | 10d | 30d | 60d | 120d | all | best | coverage |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|
| `alcf_djc_aurora` | 3,453 | 3,364 | 3,242 | **3,239** | 3,425 | 3,426 | 60d | 80% |
| `alcf_djc_polaris` | 4,516 | 4,302 | 4,150 | **3,869** | 3,891 | 3,926 | 60d | 83% |
| `alcf_djc_theta` | 2,503 | 1,702 | 1,583 | 1,551 | 1,558 | **1,541** | all | 87% |
| `atlas_mustang` | 4,943 | 4,221 | 4,051 | **3,561** | 3,590 | 3,578 | 60d | 91% |
| `atlas_opentrinity` | 3,575 | 2,710 | **2,668** | 2,743 | 2,725 | 2,725 | 30d | 69% |
| `fdata_fugaku` | 8,624 | 7,466 | 6,918 | **6,902** | 6,912 | 6,914 | 60d | 73% |
| `fresco_anvil` | 3,379 | 3,120 | 3,422 | 3,354 | **3,098** | 3,098 | 120d | 95% |
| `fresco_conte` | 8,554 | 7,748 | 7,340 | 7,501 | **6,924** | 6,953 | 120d | 97% |
| `fresco_stampede1` | 13,343 | **10,462** | 10,639 | 10,715 | 10,546 | 10,626 | 10d | 81% |
| `lassen` | 3,236 | **2,974** | 3,883 | 4,071 | 4,076 | 4,044 | 10d | 79% |
| `mit_supercloud` | **28,645** | 31,494 | 30,908 | 31,285 | 31,181 | 31,135 | 1d | 72% |
| `nlr_eagle` | 8,188 | **5,393** | 6,771 | 6,943 | 7,569 | 8,121 | 10d | 85% |
| `nlr_kestrel` | 13,731 | 11,144 | **10,895** | 10,907 | 11,104 | 11,299 | 30d | 70% |
| `pm100` | 4,108 | 3,821 | 3,784 | 3,762 | **3,693** | 3,693 | 120d | 90% |
| `pwa_cea_curie` | 6,030 | **4,892** | 5,157 | 4,996 | 4,968 | 4,978 | 10d | 81% |
| `pwa_hpc2n` | 7,028 | **5,207** | 5,566 | 5,737 | 5,326 | 5,261 | 10d | 76% |
| `pwa_kit_fh2` | 15,682 | 12,415 | 11,528 | **11,402** | 11,575 | 11,592 | 60d | 87% |
| `pwa_metacentrum` | 14,105 | 13,130 | 12,446 | 12,163 | **12,103** | 12,262 | 120d | 94% |
| `pwa_ricc` | 7,080 | 5,275 | **5,134** | 5,230 | 5,404 | 5,404 | 30d | 80% |
| `pwa_sdsc_blue` | 2,317 | 1,794 | 1,673 | 1,628 | **1,590** | 1,604 | 120d | 89% |

Optimal lookback: 1d ×1, 10d ×5, 30d ×3, 60d ×5, 120d ×5, all ×1. The benchmark once fixed
`training_lookback_days: 120` for every dataset, which is optimal here for 5 of 20. Since
[#170](https://github.com/NatLabRockies/hpc-oda-commons/issues/170) it runs every model at
10, 30 and 120 days and chooses among them walk-forward. How this
strategy compares against the fitted models is tracked in
[#171](https://github.com/NatLabRockies/hpc-oda-commons/issues/171).

## Per-feature information cost

Each dataset's `.ceiling.json` records how far its floor rises without each feature — which
identifies where the signal lives, and orders the fallback when no exact signature match
exists. On `fdata_fugaku`, dropping `name` raises the floor by 67%; on `nlr_kestrel` no single
feature is worth more than 6%.

