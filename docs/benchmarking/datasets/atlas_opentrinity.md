# Dataset card — `dataset.job_runtime.atlas_opentrinity`

*Generated 2026-08-27T12:58:44.631702+00:00 · schema `oda.dataset_card.v0.1.0`.*

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

- **Window:** 2016-02-03 → 2016-04-22 (50d train + 30d test)
- **Test period:** 2016-03-24 → 2016-04-22
- **Rows in window:** 21,529 (269 jobs/day)
- **Anchor:** 0.8 of healthy span
- **Health:** ✅ healthy
- **Rationale:** window END at 80% of healthy span; clear of all missing blocks. Source affords 80d, short of the 120d history + 90d evaluation requested, so this card runs 50d + 30d.

---
*Provenance: git `fdf037fe018c5ad7eed76829bbf790b72aa73995`, package `0.1.0`.*
