# Runtime Dataset Curation — Status & Remaining Roadmap

**Updated:** 2026-07-02 (autonomous curation run; refreshed after the SWF decoder landed)
**Companion to:** [`runtime-first-investigation.md`](runtime-first-investigation.md) (the plan) and
the public-dataset-ingestion RFC ([`../design/public-dataset-ingestion.md`](../design/public-dataset-ingestion.md)).

## Delivered (merged to `main`)

**Module + infrastructure**

- P1 descriptor schema + model (`oda.dataset.v0.1.0`); P2 fetch subsystem
  (stdlib, checksum-pinned, offline-gated, ≥5 GB guardrail); P3 decode → normalize →
  `prepare` (+ `hpc-oda datasets prepare`).
- Python floor raised to **≥3.10**; single-version unit CI.
- **Registry `v0.2.0`** with a `dataset` entry_type (`browse --type dataset` / `info`).
- **Archive decode**: `.gz` / `.zip` / `.tar` / `.tar.gz` are extracted transparently and
  matching members concatenated.
- **SWF decoder** (`datasets/decode/swf.py`): Standard Workload Format → absolute-time
  reconstruction from `UnixStartTime`; readies all ~40 Parallel Workloads Archive logs.
- **DoD-5** integration test: descriptor → `datasets prepare` → schema-valid table →
  `benchmark` → result bundle (offline, via `file://`).

**Registered runtime datasets** (fetched from Zenodo, real `sha256` pinned, normalized to
`oda.job.v0.2.0`, verified locally, discoverable via `browse --type dataset`):

| Dataset | System | Premium slice | Rows | Verified |
|---|---|---|---|---|
| `dataset.job_runtime.pm100` | Marconi100 | full | 231,238 | prepare + baseline benchmark (MAE ≈ 8431 s) |
| `dataset.job_runtime.fdata_fugaku` | Fugaku | 2024-04 | 420,450 | prepare, strict validation PASS |
| `dataset.job_runtime.adastra_mi250` | Adastra (MI250) | 15 days | 15,285 | prepare, strict validation PASS |
| `dataset.job_runtime.ccin2p3_2024` | CC-IN2P3 | Dec 2024 | 2,348,318 | prepare, strict validation PASS |

Each descriptor maps its native columns to `oda.job.v0.2.0` (runtime target + submit/start/end +
requested walltime where available + resource/queue/state features), preserving per-job power
columns for a later phase where present.

## Remaining runtime datasets + what each needs

Curate each with the established loop: **fetch premium slice → pin `sha256`+bytes → author
`oda.dataset.v0.1.0` descriptor → register (`dataset` entry in `registry/snapshot.json`) →
`datasets prepare` → benchmark.** The PM100 (parquet) and CC-IN2P3 (tar.gz+TSV) descriptors are
the templates.

| Dataset | Host / format | Needs |
|---|---|---|
| **NREL Eagle (OEDI 5860)** | `data.openei.org`, parquet | **CURATE NOW** — single ~253 MB parquet, exactly the `ingest jobs-parquet` shape. Home-lab, CC-BY. Top pick. |
| **PWA (~40 logs)** | `cs.huji.ac.il`, `.swf.gz` | **CURATE NOW** — SWF decoder done + fetch works. Confirm each log's `.swf.gz` URL (prefer the `-cln` cleaned variant); map SWF cols → `oda.job.v0.2.0`. Highest-value breadth. |
| **Atlas (Mustang/OpenTrinity)** | `ftp.pdl.cmu.edu`, `csv.gz` | **CURATE NOW** — fetch works; archive decode handles `.gz`; clean SLURM columns. |
| **NLR Eagle + Kestrel** | `data.nlr.gov`, zip | The download URL 302-redirects to HTML → needs a `data.nlr.gov`/OSTI **resolver** (or the real direct link); then archive decode handles the zip of hive-partitioned parquet. Home-lab, freshest data. |
| **IC2 / Polaris / AWS** | Zenodo, JSON | bespoke JSON-flatten decoder (workloads→`tasklist`; `submit`/`start`/`finish` epoch floats, `cpus`/`gpus`; drop node metrics) + runtime-derive (`finish−start`). |
| **FRESCO (Anvil accounting)** | datadepot / Globus | **Globus** fetch backend; take accounting CSVs only (exclude TACC-Stats). |
| **Lassen LAST** | GitHub **git-LFS** | git-LFS fetch backend (selective include of the job-summary CSV). |
| **MIT Supercloud** | AWS **S3** | S3 backend (`--no-sign-request`), scheduler prefix only (skip the 2 TB telemetry). |
| **Blue Waters** | **Globus** | Globus backend + a Torque-accounting (`key=value`) text decoder. |
| **Cloud complements** | GitHub / HF / Aliyun-OSS | Helios (zip CSV — archive decode ready; GitHub http), Acme (HF `resolve` https CSV), Alibaba GPU-v2026 (Aliyun-OSS). All lack requested-walltime → secondary. |

### Enabling capabilities

- ✅ **SWF decoder** — DONE (#52); unlocks all of PWA.

Still to build (each small, unit-testable):

1. **Fetch backends** — in rough effort order: `s3` (`--no-sign-request`, easy → MIT
   Supercloud); Aliyun-OSS / HuggingFace `resolve` (≈ plain https → Alibaba, Acme); `git-lfs`
   (medium → Lassen); `globus` (heavy: SDK + auth → FRESCO, Blue Waters).
2. **`data.nlr.gov` / OSTI resolver** — follow the 302 to the real file URL (home-lab NLR).
3. **JSON-flatten decoder** + a runtime-derive rule (`end − start`) — unlocks IC2.
4. **Torque `key=value` accounting decoder** — unlocks Blue Waters.

## Suggested finish order

1. **Now — no new code:** NREL Eagle (home-lab, OEDI), PWA, Atlas — fetch → pin → author →
   register → verify. Highest value for zero new capability.
2. **Easy backends:** `s3` → MIT Supercloud (modern SLURM+GPU); OSS/HF (≈ https) → Alibaba,
   Acme, Helios.
3. **`data.nlr.gov` resolver** → NLR Eagle + Kestrel (home-lab, freshest data).
4. **git-LFS** → Lassen · **IC2** (JSON-flatten + derive) · then **Globus** (FRESCO,
   Blue Waters) last — the heaviest lift.

Power/failure/anomaly datasets remain deferred to their phases (see the investigation doc §7).
