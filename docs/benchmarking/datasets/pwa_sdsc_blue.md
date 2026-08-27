# Dataset card — `dataset.job_runtime.pwa_sdsc_blue`

*Generated 2026-08-27T12:59:14.814489+00:00 · schema `oda.dataset_card.v0.1.0`.*

**System:** Blue Horizon  ·  **Descriptor:** `dataset.job_runtime.pwa_sdsc_blue`

## Characterization

- **Rows:** 238,562
- **Healthy span:** 2000-05-01 → 2002-12-28 (972 days, 238,336 rows)
- **Job rate:** 245 jobs/day (span avg)
- **Daily volume:** median 230, min 2, max 1,037 (gap floor 11)
- **Missing blocks (span):** 2
    - 2000-09-30 → 2000-10-02 (3 days)
    - 2000-12-29 → 2000-12-31 (3 days)
- **Runtime (s):** median 210, p90 7,890, p99 64,848, max 616,793

| feature | distinct | missing % |
|---|---:|---:|
| `queue` | 22 | 0.0 |
| `user` | 468 | 0.0 |
| `job_state` | 2 | 0.0 |

## Benchmark window

- **Window:** 2002-01-19 → 2002-06-17 (60d train + 90d test)
- **Test period:** 2002-03-20 → 2002-06-17
- **Rows in window:** 51,738 (344 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks.

---
*Provenance: git `fdf037fe018c5ad7eed76829bbf790b72aa73995`, package `0.1.0`.*
