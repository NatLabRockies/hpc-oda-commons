# Runtime Dataset Curation — Status & Remaining Roadmap

**Updated:** 2026-07-02 (autonomous curation run; 21 runtime datasets registered)
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

~53M jobs across SLURM / LSF / Torque / SWF and cloud, 1996–2025, x86 / ARM / GPU, home-lab included.
All strict-validate against `oda.job.v0.2.0`.

## Remaining runtime datasets + what each needs

| Dataset | Host / format | Needs |
|---|---|---|
| **FRESCO (Anvil accounting)** | Purdue datadepot / Globus | Check the datadepot **web/HTTPS** path first; else **Globus** (login). Accounting CSVs only (exclude TACC-Stats). |
| **Blue Waters** (Torque, 4.5M jobs) | NCSA / Globus | **Globus** login + a small **Torque `key=value`** accounting decoder. Heaviest. |
| **Alibaba GPU-v2026** | Aliyun-OSS | Verify public OSS **HTTPS** access + release status; no requested-walltime → secondary. |

### Fetch-mechanism findings (most "backends" were never needed)

Direct HTTPS (existing `http` backend) covers far more than expected — no new fetch backend was built:
- **S3** (MIT Supercloud): public objects at `https://<bucket>.s3.amazonaws.com/<key>`.
- **data.nlr.gov** (NLR): the stable URL 302-redirects to a presigned S3 object; urllib follows it.
- **HuggingFace** (Acme): the `resolve/<ref>/<path>` endpoint is direct HTTPS.
- **git-LFS** (Lassen): GitHub serves LFS content at `media.githubusercontent.com/media/<owner>/<repo>/<ref>/<path>` — **no `git-lfs` tool**.

Genuinely gated: **Globus** (FRESCO, Blue Waters) — no stable pinnable URL, needs the user's login
(use the `manual` source kind), plus a Torque decoder for Blue Waters. **Aliyun-OSS** (Alibaba) —
needs an access check.

## Suggested finish order

1. **FRESCO** — quick datadepot-HTTPS check; if it works, curate now; else it joins the Globus set.
2. **Globus set** (FRESCO + Blue Waters) — needs a user login (manual-kind flow); Blue Waters also
   needs the Torque decoder.
3. **Alibaba GPU-v2026** — verify OSS HTTPS access; secondary (no walltime).

Power/failure/anomaly datasets remain deferred to their phases (see the investigation doc §7).
