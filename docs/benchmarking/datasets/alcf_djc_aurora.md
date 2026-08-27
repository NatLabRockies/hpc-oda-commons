# Dataset card — `dataset.job_runtime.alcf_djc_aurora`

*Generated 2026-08-27T12:58:38.309780+00:00 · schema `oda.dataset_card.v0.1.0`.*

**System:** Aurora  ·  **Descriptor:** `dataset.job_runtime.alcf_djc_aurora`

## Characterization

- **Rows:** 927,999
- **Healthy span:** 2025-01-02 → 2026-07-14 (559 days, 926,499 rows)
- **Job rate:** 1,657 jobs/day (span avg)
- **Daily volume:** median 1,289, min 1, max 29,722 (gap floor 64)
- **Missing blocks (span):** 4
    - 2025-02-15 → 2025-02-18 (4 days)
    - 2025-09-16 → 2025-09-21 (6 days)
    - 2025-09-23 → 2025-09-25 (3 days)
    - 2026-05-16 → 2026-05-20 (5 days)
- **Runtime (s):** median 237, p90 6,677, p99 22,304, max 604,926

| feature | distinct | missing % |
|---|---:|---:|
| `queue` | 256 | 0.0 |
| `user` | 1,226 | 0.0 |
| `account` | 347 | 0.0 |
| `job_state` | 166 | 0.0 |

## Benchmark window

- **Window:** 2025-10-26 → 2026-03-24 (60d train + 90d test)
- **Test period:** 2025-12-25 → 2026-03-24
- **Rows in window:** 158,194 (1,054 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks.

---
*Provenance: git `fdf037fe018c5ad7eed76829bbf790b72aa73995`, package `0.1.0`.*
