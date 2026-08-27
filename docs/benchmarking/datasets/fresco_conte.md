# Dataset card — `dataset.job_runtime.fresco_conte`

*Generated 2026-08-27T12:58:53.671794+00:00 · schema `oda.dataset_card.v0.1.0`.*

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

- **Window:** 2015-07-22 → 2015-12-18 (60d train + 90d test)
- **Test period:** 2015-09-20 → 2015-12-18
- **Rows in window:** 318,392 (2,122 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks.

---
*Provenance: git `fdf037fe018c5ad7eed76829bbf790b72aa73995`, package `0.1.0`.*
