# Ingesting ALCF DJC (DIM_JOB_COMPOSITE)

ALCF's `DIM_JOB_COMPOSITE` job accounting is **primary-quality** scheduler data — real requested
walltime (`WALLTIME_SECONDS`) *and* actual runtime (`RUNTIME_SECONDS`), plus cores/nodes
used+requested, queue, exit status, machine, science field, and pre-anonymized user/project — for
Argonne systems. ALCF publishes it as **public data behind a one-time name/email form**, so it's
ingested as **`manual`-kind** datasets: you download the files once, drop them in a directory, and
`hpc-oda datasets prepare --from <dir>` checksum-verifies + normalizes them (no download in the
pipeline, no personal info in the repo).

This page is the repeatable recipe for **Polaris + Aurora, all years**.

## 1. Files to download

Every file is `https://reports.alcf.anl.gov/data/data/<name>.csv.gz`. Grouped into one registered
dataset per system.

### Polaris → `dataset.job_runtime.alcf_djc_polaris`

| Coverage | File | Status |
|---|---|---|
| 2022 (Aug 9 – Dec 31) | `ANL-ALCF-DJC-POLARIS_20220809_20221231.csv.gz` | **registered** |
| 2023 | `ANL-ALCF-DJC-POLARIS_20230101_20231231.csv.gz` | **registered** |
| 2024 | `ANL-ALCF-DJC-POLARIS_20240101_20241231.csv.gz` | **registered** |
| 2025 | `ANL-ALCF-DJC-POLARIS_20250101_20251231.csv.gz` | **registered** |
| 2026 (Jan 1 – Jun 16) | `ANL-ALCF-DJC-POLARIS_20260101_20260616.csv.gz` | **registered** |

### Aurora → `dataset.job_runtime.alcf_djc_aurora`

| Coverage | File | Status |
|---|---|---|
| 2025 (Jan 27 – Dec 31) | `ANL-ALCF-DJC-AURORA_20250127_20251231.csv.gz` | **registered** |
| 2026 (Jan 1 – Jun 16) | `ANL-ALCF-DJC-AURORA_20260101_20260616.csv.gz` | **registered** |

> Date ranges are what ALCF publishes today; the newest year grows over time and new ranges appear.
> Confirm the current list from the viewer pages
> ([polaris](https://reports.alcf.anl.gov/data/polaris.html) /
> [aurora](https://reports.alcf.anl.gov/data/aurora.html)) under **DIM_JOB_COMPOSITE**.

## 2. How to download

1. Open the system's viewer page: `https://reports.alcf.anl.gov/data/polaris.html` (or
   `aurora.html`).
2. Under **DIM_JOB_COMPOSITE**, click a year's download link. The **first** click shows ALCF's
   one-time form (first/last name + email) — submit it.
3. That authorizes your **browser session**; every DJC link then downloads a `.csv.gz` directly
   (no re-form). Download each file listed above — they range from a few MB to a few tens of MB.

Notes:
- The form cookie is browser-scoped, so the download can't be scripted from the pipeline — that's
  exactly why these are `manual`-kind.
- Do **not** unzip or rename the files. The pipeline reads `.csv.gz` directly and verifies each
  file's `sha256` by its exact name.

## 3. Where to place them

Put all the downloaded `.csv.gz` files in **one directory** — e.g. `~/alcf-djc/`. Both systems can
share the directory; each descriptor picks its own files by name.

## 4. Ingest

**Self-serve** (any already-registered ALCF dataset):

```
hpc-oda datasets prepare dataset.job_runtime.alcf_djc_polaris --from ~/alcf-djc/
hpc-oda datasets prepare dataset.job_runtime.alcf_djc_aurora  --from ~/alcf-djc/
```

`prepare` copies the placed files, checksum-verifies each, decodes the `.csv.gz`, normalizes to
`oda.job.v0.2.0`, and writes the job table (ready for `validate` / `benchmark`).

**Registering a new year/system** (maintainer step — needed once per file before self-serve works):
add a resource (`filename` + `sha256` + `bytes`) to the system's descriptor and verify the mapping
against the real file. The mapping is **identical across systems and years** (same
`DIM_JOB_COMPOSITE` schema) — only the pinned `sha256`/`filename` change. Template:
[`descriptors/job-runtime/alcf_djc_polaris.yml`](../../src/hpc_oda_commons/datasets/descriptors/job-runtime/alcf_djc_polaris.yml).

## Notes

- **Schema:** 67 raw columns; the descriptor reads ~17 mapped ones. `job_id ← JOB_NAME`,
  `requested_seconds ← WALLTIME_SECONDS`, `runtime_seconds ← RUNTIME_SECONDS`, queued/start/end
  timestamps (`iso8601`), cores/nodes used+requested, queue, exit status, machine, science field.
- **Data-quality drops:** ~110 rows/year are dropped by the `require_positive: [allocated_cpus]`
  (0-core jobs) and `require_end_after_start: true` (inverted timestamps) filters.
- **License:** unstated on the ALCF pages — cite ALCF.
