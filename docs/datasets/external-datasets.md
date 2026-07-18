# External datasets (not auto-fetched)

hpc-oda-commons prefers **lightweight, dependency-free fetching**: every *registered* dataset
pins a direct-HTTPS URL + `sha256`, and `hpc-oda datasets fetch` / `prepare` downloads and
normalizes it with the stdlib fetcher — no extra tooling. (Most sources that *look* like they
need a special backend turn out to be direct HTTPS anyway — public **S3**, **HuggingFace**
`resolve`, **git-LFS** media URLs, and presigned 302 redirects are all handled by the plain
`http` backend; see [`curation-status.md`](curation-status.md).)

A few valuable datasets aren't auto-fetched, for different reasons — documented here so you can
retrieve them yourself and turn them into canonical `oda.job.v0.2.0` tables:

- **Blue Waters** — Globus only (no direct HTTPS at all).

**ALCF DJC** was on this list too, but a closer look showed it isn't a hard wall — its downloads
sit behind a one-time name/email form on *public* data. It is now a **registered `manual`-kind
dataset** (`dataset.job_runtime.alcf_djc_polaris` + `dataset.job_runtime.alcf_djc_aurora`): you clear
the form once, download the files, and `datasets prepare --from <dir>` checksum-verifies + normalizes
them. See the ALCF DJC entry below and
"How to ingest" path 2 — it's the working example of the manual flow.

## How to ingest one of these

After you've downloaded the raw file(s) from the source below, there are two paths:

1. **Ingestion wizard** — `hpc-oda ingest jobs-parquet <file>` walks you through mapping the
   columns to `oda.job.v0.2.0` (timestamps, runtime, requested walltime, resources) and writes a
   schema-valid job table you can validate and benchmark. Best for a one-off local analysis.
2. **A `manual`-kind descriptor** — for a reproducible, registered dataset, author an
   `oda.dataset.v0.1.0` descriptor with `source.kind: manual` plus the column mapping. Place the
   downloaded file at the descriptor's cache path and `hpc-oda datasets prepare` checksum-verifies
   it and normalizes it exactly like an auto-fetched dataset. The mapping has to be built and
   verified against the real schema once, so this is a good contribution to open with a maintainer.

## Datasets

### Blue Waters workload (NCSA)

- **What:** Torque/Moab accounting for the Blue Waters supercomputer, Apr 2013 – Sep 2016,
  ~4.5M jobs. Records include `Resource_List.walltime` (requested) and `resources_used.walltime`,
  `ctime`/`qtime`/`etime`, start/end, `nodect`, `exec_host`, `Exit_status` — **primary-quality**
  (it has requested walltime).
- **Where:** **Globus only** (verified — the [NCSA data-sets page](https://bluewaters.ncsa.illinois.edu/data-sets)
  provides *no* direct HTTPS, just a Globus file-manager link to collection
  `854c1a5c-fa9f-4df4-a71c-407a33e44da0`). Grab only the **Torque accounting** subfolder (~4–5 GB);
  skip the 95 TB LDMS telemetry.
- **Format:** per-day `key=value` text files — needs a Torque-accounting parser (a `manual`
  descriptor for this would also add that decoder).
- **License:** none stated — cite the NSF Blue Waters project.

### ALCF DJC (Argonne — Polaris / Aurora / Theta / Mira) — **registered (manual-kind)**

Polaris (all published years 2022–2026, five files) and Aurora (2025–2026) are registered as
`dataset.job_runtime.alcf_djc_polaris` and `dataset.job_runtime.alcf_djc_aurora`; these entries are
the recipe for adding **further years / systems** (Theta, Mira) the same way.

- **What:** `DIM_JOB_COMPOSITE` job accounting for ALCF systems (Polaris 2022–2026, Theta, ThetaGPU,
  Mira, Aurora) — Cobalt/PBS scheduler data **with requested walltime** → primary-quality.
- **Where:** per-year files under `https://reports.alcf.anl.gov/data/` (open the viewer, e.g.
  `ANL-ALCF-DJC-POLARIS_20230101_20231231.html`, and click the CSV link). The download itself
  (`…/data/data/ANL-ALCF-DJC-<SYS>_<start>_<end>.csv.gz`) 302-redirects to a **one-time name/email
  form** on public data — not a login. Fill it once in a browser and the `.csv.gz` downloads.
- **Ingest:** `hpc-oda datasets prepare dataset.job_runtime.alcf_djc_polaris --from <dir>` (the
  `manual` backend checksum-verifies your placed file). For a new year/system, copy the descriptor,
  swap the filename + pinned `sha256`, and adjust the date in the id/name.
- **Format:** `.csv.gz`, 67 columns; the descriptor reads the ~17 mapped ones (`WALLTIME_SECONDS`,
  `RUNTIME_SECONDS`, queued/start/end, cores/nodes used+requested, queue, exit status, machine,
  science field, anonymized `USERNAME_GENID`/`PROJECT_NAME_GENID`).
- **License:** unstated — cite ALCF.

---

*Note:* FRESCO Anvil + Conte and Lassen (LLNL, git-LFS) were initially expected to need Globus /
git-LFS, but all turned out to be reachable over plain HTTPS, so they are now normally-fetched
registered datasets (`fresco_anvil`, `fresco_conte`, `lassen`). Always **live-check the fetch
path** — "gated" labels are frequently wrong; only genuinely-blocked datasets belong on this page.
