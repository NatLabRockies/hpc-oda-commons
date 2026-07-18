# Dataset card — `dataset.job_runtime.nlr_eagle`

*Generated 2026-07-18T18:22:16.286905+00:00 · schema `oda.dataset_card.v0.1.0`.*

**System:** Eagle  ·  **Descriptor:** `dataset.job_runtime.nlr_eagle`

## Characterization

- **Rows:** 13,836,216
- **Healthy span:** 2018-11-20 → 2024-06-10 (2,030 days, 13,817,149 rows)
- **Job rate:** 6,806 jobs/day (span avg)
- **Daily volume:** median 5,147, min 2, max 70,081 (gap floor 257)
- **Missing blocks (span):** 13
    - 2018-11-21 → 2018-11-25 (5 days)
    - 2019-02-03 → 2019-02-05 (3 days)
    - 2019-08-02 → 2019-08-06 (5 days)
    - 2019-10-02 → 2019-10-04 (3 days)
    - 2020-02-11 → 2020-02-15 (5 days)
    - 2021-08-14 → 2021-08-16 (3 days)
    - 2021-10-11 → 2021-10-13 (3 days)
    - 2022-01-11 → 2022-01-13 (3 days)
    - 2022-06-25 → 2022-06-27 (3 days)
    - 2022-10-03 → 2022-10-05 (3 days)
    - 2023-09-30 → 2023-10-04 (5 days)
    - 2024-04-10 → 2024-04-19 (10 days)
    - 2024-05-23 → 2024-05-26 (4 days)
- **Runtime (s):** median 374, p90 16,187, p99 172,815, max 1,302,272

| feature | distinct | missing % |
|---|---:|---:|
| `partition` | 46 | 0.0 |
| `user` | 1,132 | 0.0 |
| `account` | 656 | 0.0 |
| `job_state` | 7 | 0.0 |

## Benchmark window

- **Window:** 2023-02-01 → 2023-05-01 (60d train + 30d test)
- **Test period:** 2023-04-02 → 2023-05-01
- **Rows in window:** 780,011 (8,666 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks.

---
*Provenance: git `3071c4dd863b48e8b27e6870cdb937244d5b1347`, package `0.1.0`.*
