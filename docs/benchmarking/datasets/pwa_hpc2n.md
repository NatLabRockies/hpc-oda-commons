# Dataset card — `dataset.job_runtime.pwa_hpc2n`

*Generated 2026-08-27T12:59:08.336352+00:00 · schema `oda.dataset_card.v0.1.0`.*

**System:** Seth  ·  **Descriptor:** `dataset.job_runtime.pwa_hpc2n`

## Characterization

- **Rows:** 527,370
- **Healthy span:** 2002-08-13 → 2006-01-15 (1,252 days, 526,868 rows)
- **Job rate:** 420 jobs/day (span avg)
- **Daily volume:** median 250, min 1, max 6,895 (gap floor 12)
- **Missing blocks (span):** 1
    - 2004-04-10 → 2004-04-12 (3 days)
- **Runtime (s):** median 1,763, p90 20,216, p99 139,835, max 508,620

| feature | distinct | missing % |
|---|---:|---:|
| `partition` | 2 | 0.0 |
| `user` | 258 | 0.0 |
| `job_state` | 1 | 0.2 |

## Benchmark window

- **Window:** 2004-12-12 → 2005-05-10 (60d train + 90d test)
- **Test period:** 2005-02-10 → 2005-05-10
- **Rows in window:** 30,663 (204 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks.

---
*Provenance: git `fdf037fe018c5ad7eed76829bbf790b72aa73995`, package `0.1.0`.*
