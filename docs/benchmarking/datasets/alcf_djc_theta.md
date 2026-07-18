# Dataset card — `dataset.job_runtime.alcf_djc_theta`

*Generated 2026-07-18T18:55:10.203439+00:00 · schema `oda.dataset_card.v0.1.0`.*

**System:** Theta  ·  **Descriptor:** `dataset.job_runtime.alcf_djc_theta`

## Characterization

- **Rows:** 540,391
- **Healthy span:** 2017-07-05 → 2023-12-27 (2,367 days, 539,395 rows)
- **Job rate:** 227 jobs/day (span avg)
- **Daily volume:** median 208, min 3, max 1,386 (gap floor 10)
- **Missing blocks (span):** 6
    - 2018-11-06 → 2018-11-08 (3 days)
    - 2019-09-07 → 2019-09-09 (3 days)
    - 2020-07-14 → 2020-07-21 (8 days)
    - 2021-11-20 → 2021-11-22 (3 days)
    - 2023-05-06 → 2023-05-12 (7 days)
    - 2023-07-29 → 2023-08-01 (4 days)
- **Runtime (s):** median 1,084, p90 10,884, p99 34,276, max 628,014

| feature | distinct | missing % |
|---|---:|---:|
| `queue` | 157 | 0.0 |
| `user` | 1,827 | 0.0 |
| `account` | 628 | 0.0 |
| `job_state` | 103 | 0.0 |

## Benchmark window

- **Window:** 2022-06-13 → 2022-09-10 (60d train + 30d test)
- **Test period:** 2022-08-12 → 2022-09-10
- **Rows in window:** 15,472 (171 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks.

---
*Provenance: git `3071c4dd863b48e8b27e6870cdb937244d5b1347`, package `0.1.0`.*
