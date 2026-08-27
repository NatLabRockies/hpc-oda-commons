# Dataset card — `dataset.job_runtime.fresco_stampede1`

*Generated 2026-08-27T12:58:55.963063+00:00 · schema `oda.dataset_card.v0.1.0`.*

**System:** Stampede1  ·  **Descriptor:** `dataset.job_runtime.fresco_stampede1`

## Characterization

- **Rows:** 8,710,048
- **Healthy span:** 2013-01-11 → 2018-01-17 (1,833 days, 8,693,278 rows)
- **Job rate:** 4,742 jobs/day (span avg)
- **Daily volume:** median 4,539, min 1, max 39,445 (gap floor 227)
- **Missing blocks (span):** 1
    - 2018-01-13 → 2018-01-15 (3 days)
- **Runtime (s):** median 406, p90 30,977, p99 172,804, max 1,430,986,363

| feature | distinct | missing % |
|---|---:|---:|
| `queue` | 16 | 0.0 |
| `user` | 13,115 | 0.0 |
| `account` | 5,154 | 0.0 |
| `job_state` | 5 | 0.0 |

## Benchmark window

- **Window:** 2016-08-20 → 2017-01-16 (60d train + 90d test)
- **Test period:** 2016-10-19 → 2017-01-16
- **Rows in window:** 601,668 (4,011 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks.

---
*Provenance: git `fdf037fe018c5ad7eed76829bbf790b72aa73995`, package `0.1.0`.*
