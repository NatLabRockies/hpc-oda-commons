# Dataset card — `dataset.job_runtime.fdata_fugaku`

*Generated 2026-08-27T12:58:50.439335+00:00 · schema `oda.dataset_card.v0.1.0`.*

**System:** Fugaku  ·  **Descriptor:** `dataset.job_runtime.fdata_fugaku`

## Characterization

- **Rows:** 5,793,789
- **Healthy span:** 2023-03-01 → 2023-09-30 (214 days, 5,793,568 rows)
- **Job rate:** 27,072 jobs/day (span avg)
- **Daily volume:** median 20,222, min 2,583, max 113,432 (gap floor 1,011)
- **Missing blocks (span):** none
- **Runtime (s):** median 1,680, p90 31,002, p99 141,545, max 259,201

| feature | distinct | missing % |
|---|---:|---:|
| `user` | 1,161 | 0.0 |
| `job_state` | 2 | 0.0 |

## Benchmark window

- **Window:** 2023-04-30 → 2023-09-26 (60d train + 90d test)
- **Test period:** 2023-06-29 → 2023-09-26
- **Rows in window:** 4,351,251 (29,008 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks.

---
*Provenance: git `fdf037fe018c5ad7eed76829bbf790b72aa73995`, package `0.1.0`.*
