# Runtime Dataset Curation — Status & Remaining Roadmap

**Updated:** 2026-07-18 (24 runtime datasets registered)
**Companion to:** [`runtime-first-investigation.md`](runtime-first-investigation.md) (the plan) and
the public-dataset-ingestion RFC ([`../design/public-dataset-ingestion.md`](../design/public-dataset-ingestion.md)).

## Delivered (merged to `main`)

**Module + infrastructure**

- P1 descriptor schema + model (`oda.dataset.v0.1.0`); P2 fetch subsystem
  (stdlib, checksum-pinned, offline-gated, ≥5 GB guardrail); P3 decode → normalize →
  `prepare` (+ `hpc-oda datasets prepare`). Python floor ≥3.10.
- **Registry `v0.2.0`** with a `dataset` entry_type (`browse --type dataset` / `info`).
- **Decoders**: parquet, csv/tsv, **swf** (Standard Workload Format), **json** (flatten a
  workloads/records tree, drop nested arrays). Archive extraction (`.gz`/`.zip`/`.tar`/`.tar.gz`)
  with a **`member_glob`** filter; a parquet **`columns`** option; parquet **temporal unification**
  (mixed-tz/mixed-unit Hive partitions → UTC / `duration(us)`).
- **Mapping transforms**: timestamp (iso8601/epoch), duration (seconds/minutes/hours/hh:mm:ss/
  **timedelta**/native-Arrow-`duration`; non-numeric walltime sentinels like `UNLIMITED` → null),
  memory/memory_slurm, hash_identifier, **integer/number**
  cast, **`synthesize: row_index`** (surrogate job_id), **`derive: "end_time - start_time"`**.
- **DoD-5** integration test: descriptor → `datasets prepare` → schema-valid table → `benchmark`.

**Registered runtime datasets** (fetched from source, real `sha256` pinned, normalized to
`oda.job.v0.2.0`, verified locally, discoverable via `browse --type dataset`):

| Dataset | System | Rows kept | Source | Notes |
|---|---|---|---|---|
| `pm100` | Marconi100 | 231,238 | Zenodo | + per-job power |
| `fdata_fugaku` | Fugaku (ARM) | 420,450 | Zenodo | 2024-04 |
| `adastra_mi250` | Adastra (MI250) | 15,285 | Zenodo | 15 days |
| `ccin2p3_2024` | CC-IN2P3 | 2,348,318 | Zenodo | Dec 2024 |
| `nrel_eagle` | Eagle (OEDI 5860) | 11,014,796 | OEDI/https | |
| `pwa_kit_fh2` | ForHLR II (KIT) | 114,355 | PWA/SWF | |
| `pwa_cea_curie` | CEA Curie | 312,826 | PWA/SWF | |
| `pwa_metacentrum` | MetaCentrum grid | 5,731,100 | PWA/SWF | |
| `pwa_ricc` | RIKEN RICC | 447,794 | PWA/SWF | |
| `pwa_hpc2n` | HPC2N Seth | 527,370 | PWA/SWF | |
| `pwa_sdsc_blue` | SDSC Blue Horizon | 238,562 | PWA/SWF | |
| `atlas_mustang` | Mustang (LANL) | 2,019,005 | Atlas/https | synth id, timedelta |
| `atlas_opentrinity` | Trinity (LANL) | 21,531 | Atlas/https | synth id, timedelta |
| `mit_supercloud` | Supercloud (MIT) | 395,914 | S3/https | |
| `nlr_kestrel` | Kestrel (H100) | 9,321,737 | data.nlr.gov | home-lab |
| `nlr_eagle` | Eagle | 13,836,216 | data.nlr.gov | home-lab |
| `ic2` | IC2/Polaris/AWS | 3,599 | Zenodo/JSON | cloud+HPC |
| `lassen` | Lassen (LLNL, LSF) | 1,467,746 | GitHub-LFS/https | via LFS media URL |
| `fresco_anvil` | Anvil (Purdue, A100) | 1,475,155 | datadepot/https | 11 months, real walltime |
| `fresco_conte` | Conte (Purdue) | 1,042,125 | datadepot/https | Torque, 2015-16, real walltime |
| `fresco_stampede1` | Stampede1 (TACC) | 8,710,048 | datadepot/https | Slurm, 2013-2018, real walltime |
| `alcf_djc_polaris` | Polaris (Argonne) | 1,000,194 | ALCF (manual) | PBS, 2022-2026, real walltime |
| `alcf_djc_aurora` | Aurora (Argonne) | 927,999 | ALCF (manual) | PBS, 2025-2026, real walltime |
| `alcf_djc_theta` | Theta (Argonne) | 540,391 | ALCF (manual) | Cobalt/PBS, 2017-2023 (KNL), real walltime |

~62M jobs across SLURM / LSF / PBS / Torque / SWF and cloud, 1996–2026, x86 / ARM / GPU, home-lab included.
All strict-validate against `oda.job.v0.2.0`.

> **Note — `nrel_eagle` and `nlr_eagle` are the same machine** (NREL's Eagle), from two
> sources with overlapping years. For benchmarks/aggregates use **only `nlr_eagle`** (more
> recent, longer span) to avoid double-counting one machine. See
> [`../benchmarking/methodology.md`](../benchmarking/methodology.md).

## Remaining runtime datasets

One is documented for user ingestion in [`external-datasets.md`](external-datasets.md) —
verified as genuinely not fetchable/pinnable from this environment:

- **Blue Waters** (NCSA, Torque, ~4.5M jobs) — **Globus only** (verified: NCSA's page gives no
  direct HTTPS); has requested walltime.

(**FRESCO Stampede1** was here too, but on an unrestricted network the single 1.13 GB datadepot CSV
downloads fine; it is now the registered `fresco_stampede1` dataset — 8,710,048 jobs, real requested
walltime.)

(**ALCF DJC** was here too, but a closer look found its data isn't behind a Cloudflare wall — just a
one-time name/email form on public data. Now registered as three manual-kind datasets — all Polaris
years (`alcf_djc_polaris`, 2022–2026) + Aurora (`alcf_djc_aurora`, 2025–2026) + Theta
(`alcf_djc_theta`, 2017–2023); Mira adds the
same way. See [`alcf-djc-ingest.md`](alcf-djc-ingest.md).)

### Fetch-mechanism findings (most "backends" were never needed)

Direct HTTPS (the existing `http` backend) covers far more than expected — **no new fetch backend
was ever built**. Public **S3** (MIT: `https://<bucket>.s3.amazonaws.com/<key>`), **data.nlr.gov**
(302→presigned S3), **HuggingFace** (`resolve/<ref>/<path>`), **git-LFS** (GitHub
`media.githubusercontent.com/media/...` — no `git-lfs` tool), and the **FRESCO datadepot** (a plain
web directory) are all direct HTTPS. And **ALCF DJC** is public data behind a one-time name/email
form (now a registered manual-kind dataset), not the Cloudflare wall it first looked like — only
**Globus** (Blue Waters) genuinely needs a login. **Lesson: always live-check the fetch path.** See
[`external-datasets.md`](external-datasets.md).

## What's left

Runtime-first curation is effectively complete: **24 datasets** registered (incl. ALCF Polaris +
Aurora + Theta via the manual-kind flow; the 2026 Polaris/Aurora files were re-pinned to the
latest published export). The one remaining (Blue Waters) is genuinely not
fetchable/pinnable from this environment (Globus) and is documented for user ingestion in
[`external-datasets.md`](external-datasets.md) rather than pipeline-fetched.

Power/failure/anomaly datasets remain deferred to their phases (see the investigation doc §7).
