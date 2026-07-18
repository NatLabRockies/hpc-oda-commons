# Dataset card — `dataset.job_runtime.fresco_anvil`

*Generated 2026-07-18T18:45:31.138493+00:00 · schema `oda.dataset_card.v0.1.0`.*

**System:** Anvil  ·  **Descriptor:** `dataset.job_runtime.fresco_anvil`

## Characterization

- **Rows:** 1,475,155
- **Healthy span:** 2022-07-05 → 2023-05-30 (330 days, 1,473,516 rows)
- **Job rate:** 4,465 jobs/day (span avg)
- **Daily volume:** median 2,220, min 6, max 38,578 (gap floor 111)
- **Missing blocks (span):** 1
    - 2022-09-23 → 2022-09-27 (5 days)
- **Runtime (s):** median 197, p90 10,974, p99 345,618, max 1,189,169

| feature | distinct | missing % |
|---|---:|---:|
| `queue` | 9 | 0.0 |
| `user` | 2,165 | 0.0 |
| `account` | 252 | 0.0 |
| `job_state` | 5 | 0.0 |

## Benchmark window

- **Window:** 2022-12-26 → 2023-03-25 (60d train + 30d test)
- **Test period:** 2023-02-24 → 2023-03-25
- **Rows in window:** 257,239 (2,858 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks.

---
*Provenance: git `4aacd474f835e7e91f9bd91bb250b0d9843620d3`, package `0.1.0`.*
