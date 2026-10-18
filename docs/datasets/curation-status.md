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
| `fdata_fugaku` | Fugaku (ARM) | 5,793,789 | Zenodo | Mar–Sep 2023 (7 months, no missing blocks) |
| `adastra_mi250` | Adastra (MI250) | 15,285 | Zenodo | 15 days |
| `ccin2p3_2024` | CC-IN2P3 | 15,737,082 | Zenodo | Sep–Dec 2024 |
| `nrel_eagle` | Eagle (OEDI 5860) | 11,014,796 | OEDI/https | |
| `pwa_kit_fh2` | ForHLR II (KIT) | 114,355 | PWA/SWF | |
| `pwa_cea_curie` | CEA Curie | 312,826 | PWA/SWF | |
| `pwa_metacentrum` | MetaCentrum grid | 5,731,100 | PWA/SWF | |
| `pwa_ricc` | RIKEN RICC | 447,794 | PWA/SWF | |
| `pwa_hpc2n` | HPC2N Seth | 527,370 | PWA/SWF | |
| `pwa_sdsc_blue` | SDSC Blue Horizon | 238,562 | PWA/SWF | |
| `atlas_mustang` | Mustang (LANL) | 2,019,005 | Atlas/https | synth id, timedelta |
| `atlas_opentrinity` | Trinity (LANL) | 21,531 | Atlas/https | synth id, timedelta |
| `mit_supercloud` | Supercloud (MIT) | 395,914 | S3/https | Jan–Oct 2021 (~9 mo) |
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

~81M jobs across SLURM / LSF / PBS / Torque / SWF and cloud, 1996–2026, x86 / ARM / GPU, home-lab included.
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

## Power columns

Mapped per node (`avgpcon_per_node`, `maxpcon_per_node`) for job-power prediction
([#204](https://github.com/NatLabRockies/hpc-oda-commons/issues/204),
[how-to](../how-to/predict-power.md)):

| Dataset | Status |
|---|---|
| `fdata_fugaku_uopc` (Dec 2023–Apr 2024) | Mapped. F-DATA gives `avgpcon`/`maxpcon` per job in W, divided by requested nodes (`nnumr`): the allocated count `nnuma` can be padded past the nodes a job runs on (1-node jobs recorded with 48). |
| `fdata_fugaku` (Mar–Sep 2023) | Mapped, same columns; rows still filtered on runtime only. |
| `adastra_mi250` | **Not mapped yet; usable for average power.** Undocumented at the source, but measured: `node_power_consumption` holds exactly one value per allocated node, each node's **energy in joules over the job** (it grows with run time, r = 0.89). Value ÷ run time gives a median ~1.1–1.3 kW per node, plausible for MI250 nodes, so average power per node = `list_mean` ÷ runtime; no peak. 214 of 15,285 jobs read 0 and some read a few watts: missing telemetry that must become null before it can be a target, which the mapping cannot yet express. The `cpu_`/`mem_power_consumption` columns are placeholders (exactly 140 W and ~74 W × run time). Newer Adastra releases (30-day, 90-day with 20 s telemetry) use different conventions. See [power sources](power-sources.md). |
| `pm100` (Marconi100, May–Oct 2020) | Mapped. `node_power_consumption` is the job's total node power in W across its allocated nodes, sampled every 20 s: it scales linearly with node count (~690–770 W per node from 1 to 14 nodes). `list_mean`/`list_max` reduce it to `avgpcon`/`maxpcon`, then per node. Checked against the raw traces on the real file. Rows still filtered on runtime only. |
| `nlr_kestrel` (2023-08 to 2025-12) | Mapped, average only, CPU nodes (#209). `consumed_energy_raw_joules` is Slurm's job energy summed over its nodes: `energy_joules` (0 J as null) ÷ runtime ÷ `nodes_used`. GPU jobs have no energy. On a shared node Slurm reports the node's energy, so `null_when` nulls power for a job with `shared_job_count` ≥ 1 or in a `shared*` partition. Over all 9.3M rows kept for runtime, 65.6% have power, none before 2023-12 (2024 and 2025: 71–72%), median 587 W per node. Without power: 1.57M shared their node, 1.01M have no reading, 616k ran on GPU partitions. 138 jobs read above 1.5 kW per node ([known issues](../known-issues.md)). Rows still filtered on runtime only. |
| `nlr_eagle` (2018-11 to 2024-06) | Mapped, average only (#206). `node_energy_total_watt_hours` is the job's node energy summed over its nodes: `energy_joules` (`type: energy, unit: wh`, 0 Wh as null) ÷ runtime ÷ `nodes_used`. Matches the separate energy variant's per-node averages exactly on June 2024 (12,858 jobs). Over all 13.8M jobs, 73.4% have power, none before 2019-04, median 356 W per node; 0.08% read impossibly high (up to 20.7 MW, see [known issues](../known-issues.md)). Rows still filtered on runtime only. |
