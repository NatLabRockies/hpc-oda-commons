# Runtime Dataset Curation — Status & Remaining Roadmap

**Updated:** 2026-07-02 (autonomous curation run; 13 runtime datasets registered)
**Companion to:** [`runtime-first-investigation.md`](runtime-first-investigation.md) (the plan) and
the public-dataset-ingestion RFC ([`../design/public-dataset-ingestion.md`](../design/public-dataset-ingestion.md)).

## Delivered (merged to `main`)

**Module + infrastructure**

- P1 descriptor schema + model (`oda.dataset.v0.1.0`); P2 fetch subsystem
  (stdlib, checksum-pinned, offline-gated, ≥5 GB guardrail); P3 decode → normalize →
  `prepare` (+ `hpc-oda datasets prepare`).
- Python floor raised to **≥3.10**; single-version unit CI.
- **Registry `v0.2.0`** with a `dataset` entry_type (`browse --type dataset` / `info`).
- **Archive decode**: `.gz` / `.zip` / `.tar` / `.tar.gz` extracted transparently, members concatenated.
- **SWF decoder** (`datasets/decode/swf.py`): absolute-time reconstruction from `UnixStartTime`.
- **Mapping capabilities**: `synthesize: row_index` (surrogate job_id), `derive: "end_time - start_time"`
  (runtime from timestamps), duration unit `timedelta` (pandas strings), native Arrow `duration`
  columns → seconds.
- **Parquet decode**: temporal unification for heterogeneous Hive partitions (tz-aware timestamps
  → UTC; durations → `duration(us)`) and a `columns` option (read only mapped columns, skipping
  heavy irrelevant arrays).
- **DoD-5** integration test: descriptor → `datasets prepare` → schema-valid table → `benchmark`.

**Registered runtime datasets** (fetched from source, real `sha256` pinned, normalized to
`oda.job.v0.2.0`, verified locally, discoverable via `browse --type dataset`):

| Dataset | System | Slice | Rows kept | Source |
|---|---|---|---|---|
| `pm100` | Marconi100 | full | 231,238 | Zenodo |
| `fdata_fugaku` | Fugaku | 2024-04 | 420,450 | Zenodo |
| `adastra_mi250` | Adastra (MI250) | 15 days | 15,285 | Zenodo |
| `ccin2p3_2024` | CC-IN2P3 | Dec 2024 | 2,348,318 | Zenodo |
| `nrel_eagle` | Eagle (OEDI 5860) | full | 11,014,796 | OEDI/https |
| `pwa_kit_fh2` | ForHLR II (KIT) | 2016–18 | 114,355 | PWA/SWF |
| `pwa_cea_curie` | CEA Curie | 2011–12 | 312,826 | PWA/SWF |
| `pwa_metacentrum` | MetaCentrum grid | 2013–15 | 5,731,100 | PWA/SWF |
| `atlas_mustang` | Mustang (LANL) | 2011–16 | 2,019,005 | Atlas/https |
| `atlas_opentrinity` | Trinity (LANL) | 2017 | 21,531 | Atlas/https |
| `mit_supercloud` | Supercloud (MIT) | 2021-01 | 395,914 | S3/https |
| `nlr_kestrel` | Kestrel (H100) | 2023–25 | 9,321,737 | data.nlr.gov |
| `nlr_eagle` | Eagle | 2019–24 | 13,836,216 | data.nlr.gov |

All strict-validate against `oda.job.v0.2.0` (runtime target + submit/start/end + requested walltime
where available + resource/queue/state features).

## Remaining runtime datasets + what each needs

Curate each with the established loop: **fetch premium slice → pin `sha256`+bytes → author
`oda.dataset.v0.1.0` descriptor → register (`dataset` entry in `registry/snapshot.json`) →
`datasets prepare`.**

| Dataset | Host / format | Needs |
|---|---|---|
| **PWA — more logs** | `cs.huji.ac.il`, `.swf.gz` | **CURATE NOW** — 3 of ~40 done; the SWF decoder handles the rest, just author descriptors. (CIEMAT-Euler deferred: its `.swf.gz` truncates mid-transfer.) |
| **Cloud complements** | GitHub / HF / Aliyun-OSS | **CURATE NOW (direct https)** — Helios (GitHub zip CSV), Acme (HF `resolve` CSV), Alibaba GPU-v2026 (OSS). All lack requested-walltime → secondary. |
| **IC2 / Polaris / AWS** | Zenodo, JSON | bespoke **JSON-flatten decoder** (workloads→`tasklist`; `submit`/`start`/`finish` epoch floats; drop node metrics) + `derive`. |
| **Lassen LAST** | GitHub **git-LFS** | resolve the LFS pointer to its media URL (or `git lfs pull` then pin the job-summary CSV). |
| **FRESCO (Anvil accounting)** | datadepot / Globus | **Globus** fetch (accounting CSVs only, exclude TACC-Stats). |
| **Blue Waters** | **Globus** | Globus fetch + a Torque-accounting (`key=value`) text decoder. |

### Enabling capabilities

Done: archive decode, SWF decoder, synthesize/derive/timedelta, Arrow-duration + parquet temporal
unification, parquet `columns` option. **Note:** most previously-listed "fetch backends" proved
unnecessary — S3 (MIT), and the NLR `data.nlr.gov` downloads, are all **direct HTTPS** (the NLR
stable URL 302-redirects to a presigned S3 object; urllib follows it), so no `s3`/resolver backend
was needed. Still to build: a **JSON-flatten decoder** (IC2), **git-LFS** media-URL resolution
(Lassen), a **Torque `key=value` decoder** (Blue Waters), and a **Globus** fetch (FRESCO, Blue Waters).

## Suggested finish order

1. **Now — no new code:** more PWA logs; cloud complements (Alibaba / Acme / Helios, direct https).
2. **IC2** — the JSON-flatten decoder (finishes the Zenodo set).
3. **Lassen** (git-LFS) · then **FRESCO / Blue Waters** (Globus) last — the heaviest lift.

Power/failure/anomaly datasets remain deferred to their phases (see the investigation doc §7).
