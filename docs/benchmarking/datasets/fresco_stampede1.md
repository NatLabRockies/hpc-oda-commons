# Dataset card — `dataset.job_runtime.fresco_stampede1`

*Generated 2026-07-18T17:35:02.552197+00:00 · schema `oda.dataset_card.v0.1.0`.*

**System:** Stampede1  ·  **Descriptor:** `dataset.job_runtime.fresco_stampede1`

## Characterization

- **Rows:** 8,710,048
- **Healthy span:** 2013-01-11 → 2018-01-17 (1,833 days, 8,693,278 rows)
- **Job rate:** 4,742 jobs/day (span avg)
- **Daily volume:** median 4,539, min 1, max 39,445 (gap floor 227)
- **Missing blocks (span):** 1
    - 2018-01-13 → 2018-01-15 (3 days)
- **Runtime (s):** median 406, p90 30,977, p99 172,804, max 1,430,986,363

| feature | distinct | missing % |
|---|---:|---:|
| `queue` | 16 | 0.0 |
| `user` | 13,115 | 0.0 |
| `account` | 5,154 | 0.0 |
| `job_state` | 5 | 0.0 |

## Benchmark window

- **Window:** 2016-10-19 → 2017-01-16 (60d train + 30d test)
- **Test period:** 2016-12-18 → 2017-01-16
- **Rows in window:** 378,696 (4,207 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; gap-free.

---
*Provenance: git `1041677a0eb01a73353df2b7bc3895972851ff37`, package `0.1.0`.*
