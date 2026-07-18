# Dataset card — `dataset.job_runtime.atlas_mustang`

*Generated 2026-07-18T18:30:40.698932+00:00 · schema `oda.dataset_card.v0.1.0`.*

**System:** Mustang  ·  **Descriptor:** `dataset.job_runtime.atlas_mustang`

## Characterization

- **Rows:** 2,019,005
- **Healthy span:** 2011-11-05 → 2016-11-04 (1,827 days, 2,016,065 rows)
- **Job rate:** 1,103 jobs/day (span avg)
- **Daily volume:** median 276, min 1, max 23,446 (gap floor 13)
- **Missing blocks (span):** 8
    - 2011-11-06 → 2011-11-08 (3 days)
    - 2011-11-10 → 2011-11-15 (6 days)
    - 2011-11-23 → 2011-11-28 (6 days)
    - 2011-12-03 → 2011-12-05 (3 days)
    - 2011-12-10 → 2011-12-12 (3 days)
    - 2011-12-27 → 2012-01-02 (7 days)
    - 2014-09-19 → 2014-09-21 (3 days)
    - 2016-10-22 → 2016-10-26 (5 days)
- **Runtime (s):** median 259, p90 4,724, p99 57,601, max 523,186

| feature | distinct | missing % |
|---|---:|---:|
| `user` | 558 | 0.0 |
| `account` | 574 | 0.0 |
| `job_state` | 3 | 0.0 |

## Benchmark window

- **Window:** 2015-08-08 → 2015-11-05 (60d train + 30d test)
- **Test period:** 2015-10-07 → 2015-11-05
- **Rows in window:** 65,571 (728 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks.

---
*Provenance: git `1f961b887ea83187480cb4d7e415e8f7a1bff418`, package `0.1.0`.*
