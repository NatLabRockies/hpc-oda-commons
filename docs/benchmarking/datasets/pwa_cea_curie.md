# Dataset card — `dataset.job_runtime.pwa_cea_curie`

*Generated 2026-08-27T12:59:06.787203+00:00 · schema `oda.dataset_card.v0.1.0`.*

**System:** Curie  ·  **Descriptor:** `dataset.job_runtime.pwa_cea_curie`

## Characterization

- **Rows:** 312,826
- **Healthy span:** 2012-02-03 → 2012-10-12 (253 days, 312,822 rows)
- **Job rate:** 1,236 jobs/day (span avg)
- **Daily volume:** median 1,051, min 26, max 6,572 (gap floor 52)
- **Missing blocks (span):** 1
    - 2012-03-02 → 2012-03-07 (6 days)
- **Runtime (s):** median 124, p90 15,886, p99 86,386, max 124,615

| feature | distinct | missing % |
|---|---:|---:|
| `partition` | 18 | 0.0 |
| `user` | 582 | 0.0 |
| `job_state` | 3 | 0.0 |

## Benchmark window

- **Window:** 2012-04-03 → 2012-08-30 (60d train + 90d test)
- **Test period:** 2012-06-02 → 2012-08-30
- **Rows in window:** 185,870 (1,239 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks.

---
*Provenance: git `fdf037fe018c5ad7eed76829bbf790b72aa73995`, package `0.1.0`.*
