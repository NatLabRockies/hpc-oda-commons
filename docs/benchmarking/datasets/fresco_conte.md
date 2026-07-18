# Dataset card — `dataset.job_runtime.fresco_conte`

*Generated 2026-07-18T18:47:38.174696+00:00 · schema `oda.dataset_card.v0.1.0`.*

**System:** Conte  ·  **Descriptor:** `dataset.job_runtime.fresco_conte`

## Characterization

- **Rows:** 1,042,125
- **Healthy span:** 2015-02-28 → 2016-02-29 (367 days, 1,041,686 rows)
- **Job rate:** 2,838 jobs/day (span avg)
- **Daily volume:** median 2,172, min 696, max 10,657 (gap floor 108)
- **Missing blocks (span):** none
- **Runtime (s):** median 568, p90 13,375, p99 169,229, max 2,160,054

| feature | distinct | missing % |
|---|---:|---:|
| `queue` | 83 | 0.0 |
| `user` | 431 | 0.0 |
| `account` | 30 | 0.0 |
| `job_state` | 93 | 0.0 |

## Benchmark window

- **Window:** 2015-09-20 → 2015-12-18 (60d train + 30d test)
- **Test period:** 2015-11-19 → 2015-12-18
- **Rows in window:** 193,764 (2,152 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks.

---
*Provenance: git `4aacd474f835e7e91f9bd91bb250b0d9843620d3`, package `0.1.0`.*
