# Dataset card — `dataset.job_runtime.pwa_hpc2n`

*Generated 2026-07-18T18:38:15.069562+00:00 · schema `oda.dataset_card.v0.1.0`.*

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

- **Window:** 2005-02-10 → 2005-05-10 (60d train + 30d test)
- **Test period:** 2005-04-11 → 2005-05-10
- **Rows in window:** 14,321 (159 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks.

---
*Provenance: git `4aacd474f835e7e91f9bd91bb250b0d9843620d3`, package `0.1.0`.*
