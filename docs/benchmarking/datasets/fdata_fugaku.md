# Dataset card — `dataset.job_runtime.fdata_fugaku`

*Generated 2026-07-18T19:53:42.870105+00:00 · schema `oda.dataset_card.v0.1.0`.*

**System:** Fugaku  ·  **Descriptor:** `dataset.job_runtime.fdata_fugaku`

## Characterization

- **Rows:** 2,576,793
- **Healthy span:** 2023-06-30 → 2023-09-30 (93 days, 2,576,793 rows)
- **Job rate:** 27,707 jobs/day (span avg)
- **Daily volume:** median 25,087, min 2,583, max 113,432 (gap floor 1,254)
- **Missing blocks (span):** none
- **Runtime (s):** median 2,065, p90 39,923, p99 158,888, max 259,175

| feature | distinct | missing % |
|---|---:|---:|
| `user` | 826 | 0.0 |
| `job_state` | 2 | 0.0 |

## Benchmark window

- **Window:** 2023-06-30 → 2023-09-27 (60d train + 30d test)
- **Test period:** 2023-08-29 → 2023-09-27
- **Rows in window:** 2,453,969 (27,266 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks.

---
*Provenance: git `a79f56da07bdff876a5c47ba3d082b18a12fab77`, package `0.1.0`.*
