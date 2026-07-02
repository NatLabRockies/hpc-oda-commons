# Runtime Dataset Curation — Status & Remaining Roadmap

**Updated:** 2026-07-02 (autonomous curation run)
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

## Environment constraint hit during this run

This session's network sat behind a **TLS-intercepting proxy**: only **Zenodo** validated
cleanly. OEDI (`data.openei.org`), `cs.huji.ac.il` (PWA), and others failed with
`REDACTED REDACTED`. Consequently only **Zenodo-hosted** datasets
could be fetched + checksum-pinned here. Descriptors for the rest must be authored in a
network-unrestricted environment (each needs a one-time fetch to compute `sha256` + byte size).
**No fabricated checksums or unvalidated decoders were committed.**

## Remaining runtime datasets + what each needs

Curate each with the established loop: **fetch premium slice → pin `sha256`+bytes → author
`oda.dataset.v0.1.0` descriptor → register (`dataset` entry in `registry/snapshot.json`) →
`datasets prepare` → benchmark.** The PM100 (parquet) and CC-IN2P3 (tar.gz+TSV) descriptors are
the templates.

| Dataset | Host / format | Needs |
|---|---|---|
| **PWA (~40 logs)** | `cs.huji.ac.il`, `.swf.gz` | **SWF decoder** (18-col SWF; use header `UnixStartTime` to turn relative offsets into absolute UTC; `submit=Start+offset`, `start=submit+wait`, `end=start+runtime`) + fetch (TLS-blocked here). Archive decode already handles the `.gz`. Highest-value single unlock. |
| **IC2 / Polaris / AWS** | Zenodo, JSON | bespoke flattening decoder: top-level list of workloads, each with `tasklist` of tasks (`submit_time`/`start_time`/`finish_time` epoch floats, `cpus`, `gpus`); runtime = `finish−start`; drop nested per-node metric time-series. |
| **NREL Eagle (OEDI 5860)** | `data.openei.org`, parquet | OEDI TLS chain fails here → fetch in a CA-complete/unrestricted env (single 241 MB parquet; already the shape the repo's `ingest jobs-parquet` expects). Home-lab, CC-BY. |
| **NLR Eagle + Kestrel** | `data.nlr.gov`, zip | download URL 302-redirects to an HTML page → needs a `data.nlr.gov`/OSTI **resolver** (or the real direct link) to get a stable URL; then archive decode handles the zip of hive-partitioned parquet. Home-lab, freshest data. |
| **Atlas (Mustang/OpenTrinity)** | `ftp.pdl.cmu.edu`, `csv.gz` | fetch (host blocks HEAD/range; TLS here). Archive decode handles the `.gz`; clean SLURM columns. |
| **FRESCO (Anvil accounting)** | datadepot / Globus | **Globus** fetch backend + the host's REDACTED cert; take accounting CSVs only (exclude TACC-Stats). |
| **Lassen LAST** | GitHub **git-LFS** | git-LFS fetch backend (selective include of the job-summary CSV). |
| **MIT Supercloud** | AWS **S3** | S3 backend (`--no-sign-request`), scheduler prefix only (skip the 2 TB telemetry). |
| **Blue Waters** | **Globus** | Globus backend + a Torque-accounting (`key=value`) text decoder. |
| **Cloud complements** | GitHub / HF / Aliyun-OSS | Helios (zip CSV — archive decode ready; GitHub http), Acme (HF `resolve` https CSV), Alibaba GPU-v2026 (Aliyun-OSS). All lack requested-walltime → secondary. |

### Enabling capabilities still to build (each small, unit-testable)

1. **SWF decoder** (`datasets/decode/swf.py`) — unlocks all of PWA. *Do this first.*
2. **JSON flattening decoder** — unlocks IC2 (bespoke nesting).
3. **Fetch backends**: `git-lfs`, `s3` (`--no-sign-request`), `globus`, Aliyun-OSS, and an
   OSTI/`data.nlr.gov` **resolver** kind; plus a per-resource CA/verify option for hosts with
   incomplete TLS chains (OEDI, FRESCO). Route through the `manual` kind in the interim.
4. **Torque `key=value` accounting decoder** — unlocks Blue Waters.

## Suggested finish order

SWF → PWA · then NLR Eagle/Kestrel + NREL Eagle (home-lab) · then Atlas / FRESCO / MIT /
Blue Waters via their backends · cloud complements last. Power/failure/anomaly datasets remain
deferred to their phases (see the investigation doc §7).
