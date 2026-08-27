# Dataset card — `dataset.job_runtime.nlr_kestrel`

*Generated 2026-08-27T12:59:03.695523+00:00 · schema `oda.dataset_card.v0.1.0`.*

**System:** Kestrel  ·  **Descriptor:** `dataset.job_runtime.nlr_kestrel`

## Characterization

- **Rows:** 9,321,737
- **Healthy span:** 2023-08-24 → 2025-12-30 (860 days, 9,311,227 rows)
- **Job rate:** 10,827 jobs/day (span avg)
- **Daily volume:** median 8,660, min 1, max 132,360 (gap floor 433)
- **Missing blocks (span):** 6
    - 2023-09-30 → 2023-10-03 (4 days)
    - 2024-01-30 → 2024-02-10 (12 days)
    - 2024-04-13 → 2024-04-16 (4 days)
    - 2024-10-02 → 2024-10-07 (6 days)
    - 2024-12-20 → 2024-12-22 (3 days)
    - 2025-06-27 → 2025-06-30 (4 days)
- **Runtime (s):** median 290, p90 29,188, p99 172,815, max 6,055,479

| feature | distinct | missing % |
|---|---:|---:|
| `partition` | 32 | 0.0 |
| `user` | 1,087 | 0.0 |
| `account` | 641 | 0.0 |
| `job_state` | 7 | 0.0 |

## Benchmark window

- **Window:** 2025-01-28 → 2025-06-26 (60d train + 90d test)
- **Test period:** 2025-03-29 → 2025-06-26
- **Rows in window:** 2,387,339 (15,915 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** anchor (80%) window overlapped a missing block; shifted 15d to the nearest window clear of every block.

---
*Provenance: git `fdf037fe018c5ad7eed76829bbf790b72aa73995`, package `0.1.0`.*
