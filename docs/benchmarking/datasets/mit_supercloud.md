# Dataset card — `dataset.job_runtime.mit_supercloud`

*Generated 2026-08-27T12:58:59.176642+00:00 · schema `oda.dataset_card.v0.1.0`.*

**System:** Supercloud  ·  **Descriptor:** `dataset.job_runtime.mit_supercloud`

## Characterization

- **Rows:** 395,914
- **Healthy span:** 2021-01-05 → 2021-10-01 (270 days, 395,901 rows)
- **Job rate:** 1,466 jobs/day (span avg)
- **Daily volume:** median 840, min 1, max 18,880 (gap floor 42)
- **Missing blocks (span):** 3
    - 2021-01-12 → 2021-01-18 (7 days)
    - 2021-01-26 → 2021-02-01 (7 days)
    - 2021-02-27 → 2021-03-02 (4 days)
- **Runtime (s):** median 2,640, p90 43,221, p99 356,911, max 3,367,134

| feature | distinct | missing % |
|---|---:|---:|
| `partition` | 5 | 0.0 |
| `user` | 608 | 0.0 |
| `job_state` | 7 | 0.0 |

## Benchmark window

- **Window:** 2021-03-12 → 2021-08-08 (60d train + 90d test)
- **Test period:** 2021-05-11 → 2021-08-08
- **Rows in window:** 207,147 (1,381 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks.

---
*Provenance: git `fdf037fe018c5ad7eed76829bbf790b72aa73995`, package `0.1.0`.*
