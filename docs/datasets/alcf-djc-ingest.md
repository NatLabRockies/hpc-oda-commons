# Ingesting ALCF DJC (DIM_JOB_COMPOSITE)

ALCF's `DIM_JOB_COMPOSITE` job accounting is **primary-quality** scheduler data — real requested
walltime (`WALLTIME_SECONDS`) *and* actual runtime (`RUNTIME_SECONDS`), plus cores/nodes
used+requested, queue, exit status, machine, science field, and pre-anonymized user/project — for
Argonne systems. ALCF publishes it as **public data behind a one-time name/email form**, so it's
registered as **`manual`-kind** datasets: you download the files once, put them in a folder, and
`hpc-oda datasets prepare --from <folder>` checks and prepares them. Nothing is downloaded by the
pipeline, and no personal information reaches the repo.

Three systems are registered, one dataset each: `dataset.alcf_djc_polaris`,
`dataset.alcf_djc_aurora` and `dataset.alcf_djc_theta`. Each one's
[dataset card](cards/README.md) lists the files it needs, its columns and what preparing keeps.

## 1. Download the files

1. Open the system's viewer page:
   [polaris](https://reports.alcf.anl.gov/data/polaris.html),
   [aurora](https://reports.alcf.anl.gov/data/aurora.html) or
   [theta](https://reports.alcf.anl.gov/data/theta.html).
2. Under **DIM_JOB_COMPOSITE**, click a year's download link. The **first** click shows ALCF's
   one-time form (first/last name + email) — submit it.
3. That authorizes your **browser session**; every DJC link then downloads a `.csv.gz` directly.
   Download each file the dataset's card lists. They range from a few MB to a few tens of MB.

Notes:
- The form cookie is browser-scoped, so the download can't be scripted from the pipeline — that's
  exactly why these are `manual`-kind.
- Do **not** unzip or rename the files. The pipeline reads `.csv.gz` directly and verifies each
  file's `sha256` by its exact name.
- ALCF adds files as years go by, and its newest file's end date moves. A file the descriptor
  doesn't pin is ignored; a pinned file whose contents changed fails its checksum.

## 2. Put them in one folder

Put all the downloaded `.csv.gz` files in **one folder** — e.g. `~/alcf-djc/`. The systems can
share it; each descriptor picks its own files by name.

## 3. Prepare

```bash
hpc-oda datasets prepare src/hpc_oda_commons/datasets/descriptors/alcf_djc_polaris.yml --from ~/alcf-djc/
hpc-oda datasets prepare src/hpc_oda_commons/datasets/descriptors/alcf_djc_aurora.yml --from ~/alcf-djc/
hpc-oda datasets prepare src/hpc_oda_commons/datasets/descriptors/alcf_djc_theta.yml --from ~/alcf-djc/
```

`prepare` copies the files, checks each one's checksum, decodes the `.csv.gz`, maps it onto
`oda.job.v0.2.0`, and writes the job table, ready to validate or benchmark.

## Adding a year or a system

A maintainer step, needed once per file: add a resource (`filename` + `sha256` + `bytes`) to the
system's descriptor and check the mapping against the real file. The mapping is the same for
every system and year (one `DIM_JOB_COMPOSITE` schema); only the pinned files change. Template:
[`descriptors/alcf_djc_polaris.yml`](../../src/hpc_oda_commons/datasets/descriptors/alcf_djc_polaris.yml).

**License:** unstated on the ALCF pages — cite ALCF.
