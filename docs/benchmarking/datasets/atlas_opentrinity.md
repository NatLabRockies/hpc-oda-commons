# Dataset card — `dataset.job_runtime.atlas_opentrinity`

*Generated 2026-07-18T18:30:45.008291+00:00 · schema `oda.dataset_card.v0.1.0`.*

**System:** Trinity  ·  **Descriptor:** `dataset.job_runtime.atlas_opentrinity`

## Characterization

- **Rows:** 21,531
- **Healthy span:** 2016-02-03 → 2016-04-22 (80 days, 21,529 rows)
- **Job rate:** 269 jobs/day (span avg)
- **Daily volume:** median 117, min 3, max 4,150 (gap floor 5)
- **Missing blocks (span):** none
- **Runtime (s):** median 823, p90 14,412, p99 57,681, max 625,077

| feature | distinct | missing % |
|---|---:|---:|
| `user` | 85 | 0.0 |
| `account` | 86 | 0.0 |
| `job_state` | 4 | 0.0 |

## Benchmark window

- **Window:** 2016-02-03 → 2016-04-22 (60d train + 30d test)
- **Test period:** 2016-03-24 → 2016-04-22
- **Rows in window:** 21,529 (239 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** healthy span is only 80d (< 90d requested); used the whole span. No missing blocks.

---
*Provenance: git `1f961b887ea83187480cb4d7e415e8f7a1bff418`, package `0.1.0`.*
