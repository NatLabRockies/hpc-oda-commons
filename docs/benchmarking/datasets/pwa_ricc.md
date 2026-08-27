# Dataset card — `dataset.job_runtime.pwa_ricc`

*Generated 2026-08-27T12:59:13.284601+00:00 · schema `oda.dataset_card.v0.1.0`.*

**System:** RICC  ·  **Descriptor:** `dataset.job_runtime.pwa_ricc`

## Characterization

- **Rows:** 447,794
- **Healthy span:** 2010-05-03 → 2010-09-29 (150 days, 447,126 rows)
- **Job rate:** 2,980 jobs/day (span avg)
- **Daily volume:** median 1,481, min 13, max 24,306 (gap floor 74)
- **Missing blocks (span):** none
- **Runtime (s):** median 1,218, p90 26,429, p99 229,840, max 363,357

| feature | distinct | missing % |
|---|---:|---:|
| `queue` | 2 | 0.0 |
| `user` | 176 | 0.0 |
| `job_state` | 2 | 0.0 |

## Benchmark window

- **Window:** 2010-07-02 → 2010-09-29 (60d train + 30d test)
- **Test period:** 2010-08-31 → 2010-09-29
- **Rows in window:** 350,982 (3,899 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks. Source affords 150d, short of the 120d history + 90d evaluation requested, so this card runs 120d + 30d.

---
*Provenance: git `fdf037fe018c5ad7eed76829bbf790b72aa73995`, package `0.1.0`.*
