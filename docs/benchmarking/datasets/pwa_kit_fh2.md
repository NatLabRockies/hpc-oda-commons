# Dataset card — `dataset.job_runtime.pwa_kit_fh2`

*Generated 2026-07-18T18:38:42.053413+00:00 · schema `oda.dataset_card.v0.1.0`.*

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

- **Window:** 2017-06-13 → 2017-09-10 (60d train + 30d test)
- **Test period:** 2017-08-12 → 2017-09-10
- **Rows in window:** 21,975 (244 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks.

---
*Provenance: git `4aacd474f835e7e91f9bd91bb250b0d9843620d3`, package `0.1.0`.*
