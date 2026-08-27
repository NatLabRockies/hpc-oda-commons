# Dataset card — `dataset.job_runtime.pwa_kit_fh2`

*Generated 2026-08-27T12:59:09.855453+00:00 · schema `oda.dataset_card.v0.1.0`.*

**System:** ForHLR-II  ·  **Descriptor:** `dataset.job_runtime.pwa_kit_fh2`

## Characterization

- **Rows:** 114,355
- **Healthy span:** 2016-06-02 → 2018-01-04 (582 days, 114,352 rows)
- **Job rate:** 196 jobs/day (span avg)
- **Daily volume:** median 130, min 1, max 2,451 (gap floor 6)
- **Missing blocks (span):** 1
    - 2017-09-27 → 2017-10-01 (5 days)
- **Runtime (s):** median 600, p90 53,285, p99 259,140, max 604,800

| feature | distinct | missing % |
|---|---:|---:|
| `queue` | 2 | 0.0 |
| `partition` | 2 | 0.0 |
| `user` | 166 | 0.0 |
| `job_state` | 1 | 0.0 |

## Benchmark window

- **Window:** 2017-04-14 → 2017-09-10 (60d train + 90d test)
- **Test period:** 2017-06-13 → 2017-09-10
- **Rows in window:** 37,844 (252 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks.

---
*Provenance: git `fdf037fe018c5ad7eed76829bbf790b72aa73995`, package `0.1.0`.*
