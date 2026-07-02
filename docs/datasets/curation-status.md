# Runtime Dataset Curation — Status & Remaining Roadmap

**Updated:** 2026-07-02 (autonomous curation run; 22 runtime datasets registered)
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
  **timedelta**/native-Arrow-`duration`), memory/memory_slurm, hash_identifier, **integer/number**
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
| `acme_seren` | Seren (Shanghai AI) | 818,327 | HF/https | GPU/LLM, no walltime |
| `acme_kalos` | Kalos (Shanghai AI) | 62,410 | HF/https | GPU/LLM, no walltime |
| `helios` | SenseTime ×4 | 3,362,981 | GitHub/https | GPU, no walltime |
| `lassen` | Lassen (LLNL, LSF) | 1,467,746 | GitHub-LFS/https | via LFS media URL |
| `fresco_anvil` | Anvil (Purdue, A100) | 1,475,155 | datadepot/https | 11 months, real walltime |

~55M jobs across SLURM / LSF / Torque / SWF and cloud, 1996–2025, x86 / ARM / GPU, home-lab included.
All strict-validate against `oda.job.v0.2.0`.

## Remaining runtime datasets

Only two remain, and both need a service (Globus / Aliyun-OSS) we deliberately don't fetch in the
pipeline — they are documented for user ingestion in
[`external-datasets.md`](external-datasets.md):

- **Blue Waters** (NCSA, Torque, ~4.5M jobs) — Globus; has requested walltime (primary-quality).
- **Alibaba GPU-v2026** (ASI) — Aliyun-OSS; no requested walltime (secondary).

### Fetch-mechanism findings (most "backends" were never needed)

Direct HTTPS (the existing `http` backend) covers far more than expected — **no new fetch backend
was ever built**. Public **S3** (MIT: `https://<bucket>.s3.amazonaws.com/<key>`), **data.nlr.gov**
(302→presigned S3), **HuggingFace** (`resolve/<ref>/<path>`), **git-LFS** (GitHub
`media.githubusercontent.com/media/...` — no `git-lfs` tool), and the **FRESCO datadepot** (a plain
web directory) are all direct HTTPS. Only **Globus** (Blue Waters) and **Aliyun-OSS** (Alibaba)
genuinely need a login/SDK → see [`external-datasets.md`](external-datasets.md).

## What's left

Runtime-first auto-fetch curation is effectively complete: **22 datasets** registered, and the
only two that remain (Blue Waters, Alibaba) require Globus / Aliyun-OSS and are documented for
user ingestion in [`external-datasets.md`](external-datasets.md) rather than pipeline-fetched.

Power/failure/anomaly datasets remain deferred to their phases (see the investigation doc §7).
