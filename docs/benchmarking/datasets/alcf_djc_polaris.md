# Dataset card — `dataset.job_runtime.alcf_djc_polaris`

*Generated 2026-07-18T18:54:03.699257+00:00 · schema `oda.dataset_card.v0.1.0`.*

**System:** Polaris  ·  **Descriptor:** `dataset.job_runtime.alcf_djc_polaris`

## Characterization

- **Rows:** 1,000,194
- **Healthy span:** 2022-08-12 → 2026-07-14 (1,433 days, 999,068 rows)
- **Job rate:** 697 jobs/day (span avg)
- **Daily volume:** median 577, min 2, max 6,936 (gap floor 28)
- **Missing blocks (span):** 4
    - 2023-05-06 → 2023-05-12 (7 days)
    - 2023-07-29 → 2023-08-01 (4 days)
    - 2025-01-03 → 2025-01-07 (5 days)
    - 2025-02-15 → 2025-02-18 (4 days)
- **Runtime (s):** median 224, p90 5,307, p99 86,510, max 710,741

| feature | distinct | missing % |
|---|---:|---:|
| `queue` | 3,513 | 0.0 |
| `user` | 2,522 | 0.0 |
| `account` | 587 | 0.0 |
| `job_state` | 121 | 0.0 |

## Benchmark window

- **Window:** 2025-07-04 → 2025-10-01 (60d train + 30d test)
- **Test period:** 2025-09-02 → 2025-10-01
- **Rows in window:** 72,912 (810 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks.

---
*Provenance: git `3071c4dd863b48e8b27e6870cdb937244d5b1347`, package `0.1.0`.*
