# Dataset card — `dataset.job_runtime.pwa_cea_curie`

*Generated 2026-07-18T18:39:01.852495+00:00 · schema `oda.dataset_card.v0.1.0`.*

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

- **Window:** 2012-05-26 → 2012-08-23 (60d train + 30d test)
- **Test period:** 2012-07-25 → 2012-08-23
- **Rows in window:** 123,688 (1,374 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks.

---
*Provenance: git `4aacd474f835e7e91f9bd91bb250b0d9843620d3`, package `0.1.0`.*
