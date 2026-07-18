# Dataset card — `dataset.job_runtime.pwa_metacentrum`

*Generated 2026-07-18T18:44:10.959941+00:00 · schema `oda.dataset_card.v0.1.0`.*

**System:** MetaCentrum  ·  **Descriptor:** `dataset.job_runtime.pwa_metacentrum`

## Characterization

- **Rows:** 5,731,100
- **Healthy span:** 2013-01-03 → 2014-12-30 (727 days, 5,726,455 rows)
- **Job rate:** 7,876 jobs/day (span avg)
- **Daily volume:** median 5,468, min 137, max 36,083 (gap floor 273)
- **Missing blocks (span):** none
- **Runtime (s):** median 127, p90 13,903, p99 203,987, max 10,499,676

| feature | distinct | missing % |
|---|---:|---:|
| `partition` | 1 | 0.0 |
| `user` | 880 | 0.0 |
| `job_state` | 1 | 0.0 |

## Benchmark window

- **Window:** 2014-05-10 → 2014-08-07 (60d train + 30d test)
- **Test period:** 2014-07-09 → 2014-08-07
- **Rows in window:** 1,012,677 (11,252 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks.

---
*Provenance: git `4aacd474f835e7e91f9bd91bb250b0d9843620d3`, package `0.1.0`.*
