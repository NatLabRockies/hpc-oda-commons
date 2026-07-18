# Dataset card — `dataset.job_runtime.lassen`

*Generated 2026-07-18T18:28:59.775408+00:00 · schema `oda.dataset_card.v0.1.0`.*

**System:** Lassen  ·  **Descriptor:** `dataset.job_runtime.lassen`

## Characterization

- **Rows:** 1,467,746
- **Healthy span:** 2018-09-28 → 2020-11-17 (782 days, 1,466,981 rows)
- **Job rate:** 1,875 jobs/day (span avg)
- **Daily volume:** median 1,300, min 2, max 22,192 (gap floor 65)
- **Missing blocks (span):** 6
    - 2018-09-29 → 2018-10-01 (3 days)
    - 2018-10-05 → 2018-10-07 (3 days)
    - 2018-10-18 → 2018-10-23 (6 days)
    - 2018-11-01 → 2018-11-06 (6 days)
    - 2018-11-15 → 2018-11-18 (4 days)
    - 2018-11-20 → 2018-11-23 (4 days)
- **Runtime (s):** median 321, p90 21,619, p99 43,223, max 345,501

| feature | distinct | missing % |
|---|---:|---:|
| `queue` | 14 | 0.0 |
| `user` | 589 | 0.0 |
| `account` | 589 | 0.0 |

## Benchmark window

- **Window:** 2020-03-17 → 2020-06-14 (60d train + 30d test)
- **Test period:** 2020-05-16 → 2020-06-14
- **Rows in window:** 174,542 (1,939 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks.

---
*Provenance: git `1f961b887ea83187480cb4d7e415e8f7a1bff418`, package `0.1.0`.*
