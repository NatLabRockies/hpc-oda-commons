# HPC Operational Datasets — Investigation & Runtime-First Download Plan

**Status:** Investigation complete; download decision proposed (awaiting sign-off).
**Date:** 2026-07-02
**Scope:** First pass = **job runtime prediction**. Power/energy, failure/reliability,
anomaly detection, telemetry, network, and I/O are **deferred to later phases** (but a
dataset that carries *both* runtime and power still counts as runtime-relevant — we fetch
it now for runtime and reuse it later for power).
**Budget:** 1 TB available; **≤ 500 GB** for this pass (target far less). Prefer "premium"
data = the **most recent + most relevant** subset, not full history.
**Source of record:** `docs/hpc_operational_datasets.xlsx` (45 catalog entries + ~40
Parallel Workloads Archive logs + aggregators).

**Method.** Six parallel investigations covered every catalog dataset, web-verifying sizes,
recency, formats, access/gating, download mechanics, and per-job field content, then
assessing runtime-prediction relevance and estimating the disk cost of the premium slice.
Figures are tagged `[web-verified]`, `[catalog]`, or `[estimated]` in the per-dataset notes
below.

---

## 1. TL;DR — the download decision

The runtime-relevant data is **tiny**: HPC job/accounting tables compress to MB–single-GB;
the multi-TB items in the catalog are all telemetry/power we're deferring. The recommended
first-pass pull is **≈ 41 GB downloaded (~80–100 GB on disk after unzip/parse) — under ~20 %
of the 500 GB budget**, with room to add historical depth later.

**Recommended download set (premium runtime slices):**

| # | Dataset | System | Sched. | Slice to grab | DL size | Backend |
|---|---------|--------|--------|---------------|--------:|---------|
| 7  | **NLR Kestrel Jobs** | Kestrel (H100) | SLURM | whole zip | 0.70 GB | osti/http |
| 6  | **NLR Eagle Jobs + Energy** | Eagle | SLURM | core job zip (skip 1.3 GB energy) | 0.85 GB | osti/http |
| 4  | **NREL Eagle (OEDI 5860)** | Eagle | SLURM | `eagle_data.parquet` | 0.24 GB | oedi/http |
| 14 | **CC-IN2P3 2024** | CC-IN2P3 | SLURM | all 12 monthly tar.gz (44M jobs) | 0.88 GB | zenodo |
| 1  | **F-DATA** | Fugaku | Fujitsu | recent 12 months `2[34]_*.parquet` | ~10 GB | zenodo |
| 3  | **PM100** | Marconi100 | SLURM | `job_table.parquet` | 0.29 GB | zenodo |
| 11 | **ALCF Public (DJC)** | Mira/Theta/Polaris | Cobalt/PBS | DJC job tables (per sys/yr) | 0.30 GB | http |
| 13 | **IC2/Polaris/AWS** | multi | mixed | Polaris+IC2(+AWS) JSON | 0.70 GB | zenodo |
| B  | **Parallel Workloads Archive** | ~30 systems | mixed | all 40 `-cln`/`.swf.gz` logs | 0.67 GB | http |
| 23 | **Atlas (Mustang+OpenTrinity)** | LANL | SLURM | 2 `*_release_v1.0beta.csv.gz` | 0.50 GB | ftp/http |
| 30 | **Lassen LAST** | Lassen | LSF | job-summary CSV (LFS include) | ~2 GB | git-lfs |
| 33 | **MIT Supercloud** | Supercloud | SLURM | scheduler prefix only (skip 2 TB telemetry) | ~3 GB | s3 |
| 37 | **Blue Waters workload** | Blue Waters | Torque | Torque accounting logs (skip 95 TB LDMS) | ~5 GB | globus |
| 26 | **FRESCO** | Anvil/Conte/Stampede1 | Slurm/Torque | **accounting only** (skip TACC-Stats) | ~10 GB | globus/https |
| 31 | **Adastra MI250** | Adastra | SLURM | single parquet | 0.001 GB | zenodo |
| | **Cloud/GPU complements** | | | | | |
| 20 | **Helios** | SenseTime | (sacct) | whole `data.zip` | 0.36 GB | github |
| 21 | **Acme** | Seren/Kalos | (sacct) | 2 job-trace CSVs | 0.11 GB | huggingface |
| 17 | **Alibaba GPU-v2026** | ASI | k8s | `job_execution_summary` only | ~5 GB | aliyun-oss |

**Recommended total ≈ 41 GB download / ~80–100 GB on disk.** Leaner variant (F-DATA 4 mo,
FRESCO Anvil-only, drop Alibaba) ≈ **22 GB**. The 500 GB ceiling is only ever at risk from
data we deliberately exclude (TACC-Stats, MIT/Blue Waters telemetry, Alibaba v2018 = 270 GB
uncompressed, Google 2019 = 2.4 TiB).

**Why these:** they are the datasets that carry the actual runtime-prediction signal —
per-job **requested walltime vs. actual runtime**, plus submit/start/end, requested/used
nodes/CPUs, queue wait, and exit/state — and they're recent, openly licensed, and small.

---

## 2. Selection criteria

A dataset is **runtime-relevant** if it exposes per-job records with the fields runtime
prediction actually uses:

- **Target:** actual runtime (`elapsed`/`run_time`/`duration`, or end − start).
- **Key feature:** the user's **requested walltime** / time limit (the classic
  requested-vs-used signal). *This is the single most predictive HPC feature — and the one
  most often missing from cloud/GPU traces.*
- **Context features:** submit/start/end timestamps, requested vs. used nodes/CPUs/GPUs/mem,
  queue wait (start − submit), exit/state, partition/queue/QOS, user/account.

Classification: **core** = ships real per-job scheduler/accounting with runtime + requested
walltime; **partial** = runtime derivable but incomplete (e.g., no requested walltime, or
reconstructed from polling); **none** = telemetry/power/failure/anomaly with no per-job
accounting.

"**Premium**" = most recent + most representative subset (favor current-gen systems, richest
schemas, and — for the home-lab Eagle/Kestrel — full coverage since those are our own).

---

## 3. The download plan (detail)

### 3.1 Tier 1 — Primary HPC scheduler traces (have requested walltime) → **INCLUDE**

- **NLR Kestrel (#7)** — SLURM, Aug 2023–**Dec 2025**, ~11M rows/50 vars, Hive-partitioned
  Parquet in one ~0.7 GB zip. Freshest data of any dataset, current-gen H100, home-lab.
  `data.nlr.gov/system/files/302/…kestrel.job-anon.zip` (DOI 10.7799/3023270). License
  `nlr-data-1.0`. Filter `year=2025` partitions locally if a leaner slice is wanted. **Top pick.**
- **NLR Eagle Jobs + Energy (#6)** — SLURM, 2019–2024 full lifetime, ~13.8M rows/62 vars.
  Core job zip ≈ 0.85 GB (skip the separate 1.3 GB energy variant for the runtime pass).
  `data.nlr.gov/system/files/295/…eagle.job-anon.zip` (DOI 10.7799/3023273). Use the `_tz`
  timestamp columns (DST-correct). Home-lab, definitive modern Eagle corpus.
- **NREL Eagle OEDI #5860 (#4)** — SLURM, through Feb 2023, 11M+ jobs, single 241 MB
  `eagle_data.parquet` (also `.csv.bz2`). **CC-BY-4.0**, direct HTTPS
  `data.openei.org/files/5860/eagle_data.parquet`. Already the target of the repo's existing
  `ingest jobs-parquet` workflow → ideal first ingest. Not time-split; filter locally.
- **CC-IN2P3 2024 (#14)** — SLURM `sacct`, full-year 2024, **44M jobs**, TSV-in-tar.gz, 12
  monthly files ≈ 885 MB compressed. **CC-BY-4.0**, Zenodo 18668107. Best-documented +
  largest-sample schema (`submit/eligible/start/end`, `timelimit` vs `elapsed`, alloccpus/mem,
  state, partition). CPU/HTC-centric (weak "nodes requested"). Recent quarter alone ≈ 226 MB.
- **F-DATA / Fugaku (#1)** — Fujitsu scheduler, Mar 2021–Apr 2024, ~24M jobs, 38 monthly
  Parquet. **Total ~28 GB (NOT the "11 TB" cumulative-traffic figure).** Richest current-era
  schema (full lifecycle + power/perf counters). **CC-BY-4.0**, per-month direct URLs
  `zenodo.org/records/11467483/files/<YY_MM>.parquet`. Recent 4 mo ≈ 3 GB; 12 mo ≈ 10 GB
  (recommended for ARM/non-NLR diversity). ARM A64FX → watch cross-system generalization.
- **PM100 / Marconi100 (#3)** — SLURM + per-job power, May–Oct 2020, 231k jobs, single 287 MB
  `job_table.parquet`. **CC-BY-4.0**, Zenodo 10127767. Pre-curated runtime+power → excellent
  tiny dev/benchmark target (older 6-month window; x86+V100).
- **ALCF Public Data / DJC (#11)** — Cobalt/PBS `DIM_JOB_COMPOSITE` (queued/start/end,
  `WALLTIME_SECONDS` vs `RUNTIME_SECONDS`, nodes req/used, queue, exit), CSV.gz ~3–11 MB per
  system-year. Open, `reports.alcf.anl.gov/data/`. Grab Polaris 2022–25 + Theta + Mira DJC
  files (~0.05–0.3 GB); skip telemetry/Darshan tables. **Caveats:** license unstated; server
  blocks scripted user-agents (use browser headers).
- **IC2/Polaris/AWS (#13)** — purpose-built for runtime + resource-utilization prediction,
  published 2024, 706 MB JSON (14 files). **CC-BY-4.0**, Zenodo 15545096 (OSTI 3005909). Grab
  `*_polaris*`/`*_ic2*` (+ optional AWS). **Inspect the JSON schema early** — exact field list
  isn't documented on the landing page.
- **Parallel Workloads Archive (B)** — the canonical runtime corpus. SWF (18 cols): `Run Time`
  (target), `Requested Time` (key feature), requested-vs-used procs/mem, status,
  queue/partition; start/end = `Submit + Wait`. **All 40 logs ≈ 688 MB compressed** (~227 MB
  excluding the 4 Intel-NetBatch pools). Direct HTTP per-log `.swf.gz`; **prefer `-cln`
  cleaned versions** where they exist. Premium modern subset (KIT-FH2 2016–18, CIEMAT-Euler
  2008–17, MetaCentrum2, CEA-Curie ≈ 15M jobs) ≈ 150 MB — but grab everything, it's trivial.
- **Atlas — Mustang + OpenTrinity (#23)** — LANL SLURM traces, Mustang 2011–16 (2.1M jobs;
  submit/start/end, `wallclock_limit`, node/tasks requested, status), OpenTrinity 2017
  (superset: +queue_time, QOS, tasks_allocated, completion_code). Gzipped CSV at
  `ftp.pdl.cmu.edu/pub/datasets/ATLAS/{mustang,trinity}/`, < 1 GB total. Citation-required
  (USENIX ATC'18). **Server blocks HEAD/range** → just download the (small) files. Two Sigma
  traces are on-request (excluded).
- **Lassen LAST (#30)** — LLNL **LSF**, ~1.47M jobs, per-job summary (submit/start/end,
  elapsed, req/alloc nodes, disposition, exit, energy, net). GitHub `LLNL/LAST`, **git-LFS** —
  selective pull the summary CSV(s) (`GIT_LFS_SKIP_SMUDGE=1` clone + `git lfs pull --include`),
  skip energy/network time series. ~1–3 GB. Confirm whether requested-walltime is explicit vs.
  derived. LSF ≠ SLURM (state/field semantics differ).
- **MIT Supercloud (#33)** — modern SLURM + GPU, 2021, 460,497 jobs. Real scheduler table
  (submit/start/end, requested vs. used walltime/nodes/CPUs/**GPUs**/mem, exit, state) sits on
  a **separate S3 prefix** from the 2 TB telemetry. `aws s3 sync s3://mit-supercloud-dataset/<scheduler-prefix> . --no-sign-request`
  (~1–5 GB). **Verify the exact scheduler prefix at download.**
- **Blue Waters workload (#37)** — **Torque/Moab** accounting (ctime/qtime/etime, start, end,
  `resources_used.walltime`, `Resource_List.walltime`, nodect, exec_host, Exit_status), Apr
  2013–Sep 2016. Published as downloadable per-day text files via **Globus** (collection
  `854c1a5c-…`), separate from the 95 TB LDMS telemetry. Grab only the Torque accounting
  subfolder (~4–5 GB); parse the key=value text yourself. No license text (cite NSF).
- **FRESCO (#26)** — Purdue/TACC. Job accounting (submit/start/end, requested resources, user,
  exit) for Conte (Torque, 2015–17), Stampede1 (Torque, 2013–16), **Anvil (Slurm+XDMoD,
  2022–23, A100)**. Take **accounting CSVs only** (~5–20 GB); **deliberately exclude the
  per-node TACC-Stats/XDMoD timeseries** (hundreds of GB). Web browse or Globus at
  `datadepot.rcac.purdue.edu/sbagchi/fresco/`; fetch via Globus.
- **Adastra MI250 (#31)** — SLURM, 15 days 2024, 30,570 jobs, **single 1.2 MB parquet**.
  **CC-BY-4.0**, Zenodo 14007065. Most recent EU system; trivially include (verify columns on
  open).

### 3.2 Tier 2 — Cloud/GPU complements (NO requested walltime) → **INCLUDE (secondary)**

These are clean, tiny, recent per-job GPU/DNN traces with duration + queue wait + requested
resources — but **none has a requested-walltime field** (even Helios/Acme were `sacct`-collected
yet dropped `Timelimit`). Treat as cross-domain complements, not primaries.

- **Helios (#20)** — 4 SenseTime GPU clusters, Apr–Sep 2020, 3.36M jobs (submit/start/end,
  duration, queue, gpu/cpu/node counts, state). Whole `data.zip` = 36 MB / 343 MB unzipped.
  GitHub `S-Lab-System-Group/HeliosData`. **CC-BY-4.0.**
- **Acme (#21)** — Shanghai AI Lab Seren/Kalos LLM clusters, Mar–Aug 2023, ~1.1M jobs. Two job
  CSVs (`trace_seren.csv` 99 MB + `trace_kalos.csv` 9 MB) ≈ 108 MB — fetch just those from
  HuggingFace `Qinghao/AcmeTrace`, avoid the 80 GB `utilization/` tree. **CC-BY-4.0.**
- **Alibaba GPU-v2026 (#17)** — newest/largest (ASI, 155k GPUs, 6 mo, OSDI'26).
  `asi_opensource_job_execution_summary` has `duration_hours`, `schedule_delay_sec` (queue
  wait), `gpu_request`, priority/type. Direct Aliyun OSS; grab only the summary ZIP (~1–10 GB),
  skip hourly pod/server/network tables. (Older v2018 CPU batch = 270 GB uncompressed +
  survey-gated → optional, see §3.3.)

### 3.3 Optional / conditional (documented; grab if wanted) → **MAYBE**

| Dataset | Why optional | Slice / size | Gate |
|---|---|---|---|
| ALCF IEEE DataPort (#12) | duplicates open #11's job data | DJC files ~0.1 GB | IEEE DataPort login |
| Titan RUR 2018–19 (#44) | actual runtime but **no requested walltime/queue** | ~3.5–4 GB | Globus |
| Philly (#19) | GPU-DNN only, no walltime, 2017 | job log ~0.3–1 GB | github |
| Google Borg 2011 (#16) | Borg ≠ SLURM, no walltime, normalized units | ~15–41 GB | GCS (2019 excluded: 2.4 TiB/BigQuery) |
| Summit login-node (#28) | LSF, **hourly polling** (±1 h), reconstruct | ~3 GB dl | verify live availability |
| GWA GWF traces (#34) | old grid, task-granular; good for GWF/SWF adapter tests | ~1–3 GB | http |
| Alibaba v2018 batch (#17) | large **CPU** batch (only budget-relevant item) | ~270 GB uncompressed | short survey |
| NREL Eagle 3-mo (#5) | tiny non-contiguous JSON — good **CI fixture** | 13 MB | osti/http |
| Azure (#18) | VM-lifetime proxy, no scheduler semantics | ~0.2 GB | github/blob |
| SURFace / Lisa (#32) | ideal `sacct` schema **but job table not published** | — | reproduce or email authors |

### 3.4 Fetch backends required

The recommended set spans more backends than P2 currently implements (`http`, `manual`, +
planned extras `s3`/`git-lfs`/`bigquery`). Mapping:

- **http / oedi / osti** (direct HTTPS): NREL Eagle, ALCF, PWA, Atlas, F-DATA, PM100, CC-IN2P3,
  IC2, Adastra, NLR Eagle/Kestrel (presigned S3 over HTTPS). ✅ covered by P2 `http`.
- **git-lfs**: Lassen LAST. → P2 extra.
- **s3** (`--no-sign-request`): MIT Supercloud, (Azure blob). → P2 extra.
- **github**: Helios (plain repo file). ✅ via `http`.
- **NEW backends to add:** **Globus** (FRESCO, Blue Waters, Titan RUR), **HuggingFace Hub**
  (Acme), **Aliyun OSS** (Alibaba), **BigQuery** (Google 2019 — excluded). Until implemented,
  these can be handled via the `manual` kind (checksum-verify a user-fetched file) or grabbed
  via their native CLIs and pointed at with `--from`.

### 3.5 Disk-budget summary

| Bundle | Download | On disk (est.) | % of 500 GB |
|---|---:|---:|---:|
| Lean (Tier-1 core, F-DATA 4 mo, FRESCO Anvil-only, no cloud) | ~22 GB | ~45 GB | ~9 % |
| **Recommended (Tier 1 + Tier 2, F-DATA 12 mo)** | **~41 GB** | **~80–100 GB** | **~16–20 %** |
| + optional (Titan, Google 2011, GWA, Summit, Philly) | +~30–60 GB | +~60–120 GB | still < 45 % |
| + Alibaba v2018 full CPU batch | +~270 GB | (uncompressed) | approaches ceiling |

The premium-slice strategy is the whole point: we skip every multi-TB telemetry payload and
keep only the job/accounting tables.

---

## 4. Full dataset catalog (all entries)

Detailed per-dataset findings (contents, size, format, access, download, recency, license,
runtime relevance) live in the six investigation transcripts and are summarized here for reuse
across the deferred phases.

### 4.1 Individual system traces (Cat. A, #1–15)

| # | Dataset | System | Runtime rel. | Total size | Premium slice | Recent | License | First pass |
|---|---------|--------|--------------|-----------:|---------------|--------|---------|-----------|
| 1 | F-DATA | Fugaku | core | ~28 GB | 12 mo ~10 GB | Apr 2024 | CC-BY-4.0 | **YES** |
| 2 | M100 ExaData | Marconi100 | partial | 49.9 TB | job_table (extract) | Sep 2022 | CC-BY-4.0 | NO (PM100 covers it) |
| 3 | PM100 | Marconi100 | core | 287 MB | whole | 2020 | CC-BY-4.0 | **YES** |
| 4 | NREL Eagle (OEDI 5860) | Eagle | core | 352 MB | parquet 241 MB | Feb 2023 | CC-BY-4.0 | **YES** |
| 5 | NREL Eagle 3-mo | Eagle | core (tiny) | 13 MB | whole | 2020 | open | MAYBE (CI fixture) |
| 6 | NLR Eagle+Energy | Eagle | core | 2.17 GB | core zip 0.85 GB | 2019–24 | nlr-data-1.0 | **YES** |
| 7 | NLR Kestrel | Kestrel | core | 697 MB | whole | **Dec 2025** | nlr-data-1.0 | **YES (top)** |
| 8 | NLR Eagle Node Power | Eagle | none | 7.8 GB | — | 2024 | open | NO (power) |
| 9 | NLR Eagle GPU Metrics | Eagle | none | <2 GB | — | 2024 | open | NO (telemetry) |
| 10 | NLR GenAI Power | Kestrel | none | 1.0 GB | — | 2025 | open | NO (power) |
| 11 | ALCF Public (DJC) | Mira/Theta/Polaris | core | ~few 100 MB | DJC files ~0.3 GB | Polaris→2025 | unstated | **YES** |
| 12 | ALCF IEEE DataPort | ANL (all) | core | many GB–TB | DJC only ~0.1 GB | →2025 | unstated | MAYBE (login) |
| 13 | IC2/Polaris/AWS | multi | core | 706 MB | HPC ~0.4 GB | 2024 | CC-BY-4.0 | **YES** |
| 14 | CC-IN2P3 2024 | CC-IN2P3 | core | 885 MB | full 0.88 GB | **2024** | CC-BY-4.0 | **YES** |
| 15 | C6EnPLS | CRESCO6 | partial | 8.9 GB | job CSVs ~50 MB | 2024 | CC0-1.0 | NO (power phase) |

### 4.2 Parallel Workloads Archive (Cat. B) — see §3.1; all 40 logs ≈ 0.67 GB, SWF, HTTP, prefer `-cln`. **YES.**

### 4.3 Commercial / cloud (Cat. C, #16–21)

| # | Dataset | Runtime rel. | Premium slice | Recent | License | First pass |
|---|---------|--------------|---------------|--------|---------|-----------|
| 16 | Google Borg | partial | 2011 events ~15–41 GB | 2019 (gated) | CC-BY-4.0 | MAYBE (2011) |
| 17 | Alibaba | core (GPU-v2026) | job summary ~1–10 GB | **2026** | research-use | **YES** (v2026); v2018 optional |
| 18 | Azure | partial | V2 vmtable ~0.2 GB | 2019/24 | CC-BY/MIT | NO |
| 19 | Philly | partial | job log ~0.3–1 GB | 2017 | CC-BY-4.0 | MAYBE |
| 20 | Helios | core | whole ~0.4 GB | 2020 | CC-BY-4.0 | **YES** |
| 21 | Acme | core | job CSVs ~0.11 GB | 2023 | CC-BY-4.0 | **YES** |

*All cloud/GPU traces lack requested-walltime — complements, not primaries.*

### 4.4 Failure/reliability + grid (Cat. D/G, #22–26, 34–35)

| # | Dataset | Runtime rel. | Premium slice | First pass |
|---|---------|--------------|---------------|-----------|
| 22 | CFDR | none | — | NO (failure phase) |
| 23 | Atlas (Mustang+OpenTrinity) | core | 2 CSV.gz < 1 GB | **YES** |
| 24 | Backblaze | none | — | NO (failure phase) |
| 25 | Loghub | none | — | NO (log-anomaly phase) |
| 26 | FRESCO | core (accounting) | accounting ~5–20 GB | **YES** (exclude TACC-Stats) |
| 34 | GWA | partial | GWF traces ~1–3 GB | MAYBE (adapter tests) |
| 35 | FTA | none | — | NO (failure phase) |

### 4.5 DOE/Euro telemetry + misc (Cat. E/F/H/I/J, #27–33, 36–45)

| # | Dataset | Runtime rel. | Premium slice | First pass |
|---|---------|--------------|---------------|-----------|
| 27 | Summit GPU DBE | none | — | NO (failure) |
| 28 | Summit login-node | partial (hourly LSF) | ~3 GB dl | MAYBE |
| 29 | Frontier HPL | none | — | NO (power) |
| 30 | Lassen LAST | core (LSF) | job summary ~1–3 GB | **YES** |
| 31 | Adastra MI250 | core | 1.2 MB | **YES** |
| 32 | SURFace (Lisa) | core schema, **not published** | n/a | NO (job table absent) |
| 33 | MIT Supercloud | core (SLURM+GPU) | scheduler ~1–5 GB | **YES** |
| 36 | Monet | none | — | NO (network) |
| 37 | Blue Waters | core (Torque) | accounting ~4–5 GB | **YES** |
| 38 | HMDR/m888 | none | — | NO (resilience) |
| 39 | HPC-ODA | none | — | NO (sensor/anomaly) |
| 40 | Antarex | none | — | NO (fault) |
| 41 | Prodigy/HPAS | none | — | NO (anomaly) |
| 42 | Oliner-Stearley 5 logs | none | — | NO (RAS logs) |
| 43 | Titan GPU Lifetimes | none | — | NO (GPU reliability) |
| 44 | Titan RUR | partial (no req. walltime) | 2018–19 ~4 GB | MAYBE |
| 45 | Darshan | partial (weak) | — | NO (I/O phase) |

---

## 5. Corrections to the source catalog (`hpc_operational_datasets.xlsx`)

- **F-DATA** is **~28 GB**, not TB — the "11.1 TB" Zenodo figure is *cumulative traffic*.
- **M100** "job_table = record 7588815" is wrong — that record is the full 2020 telemetry
  tarball set; no standalone job_table record exists (extract `plugin=job_table` from monthly
  tars — or just use PM100, its curated slice).
- **#4 NREL Eagle** is a **single non-time-split** 352 MB file (not "split by time"),
  **CC-BY-4.0**, **direct HTTPS only** (no S3 path).
- **#5 NREL Eagle 3-mo** months are **Dec 2019 / Apr 2020 / Aug 2020** (non-consecutive).
- **#6/#7** OSTI DOIs resolve to **data.nlr.gov/submissions/#295 and #302** (not 288/312);
  license is **`nlr-data-1.0`** (non-SPDX). Kestrel's Dec 2025 end-date is future vs. its
  Jun 2025 publication → likely a refreshed record; confirm max timestamp on download.
- **#8 Eagle Node Power** is **6 yearly zips ≈ 7.8 GB** (not 7 zips / 7.6 GB).
- **#32 SURFace** is the SURF **Lisa** cluster (not Cartesius), and its job table is **not in
  the public release** (only 42.6 GB of node telemetry is).
- **#28 Summit login-node** is **hourly LSF `bjobs` polling** → per-job runtime is
  reconstructable but only ~±1 h accurate (partial, not core).
- **NREL = NLR** (same institution); `data.nrel.gov` 301-redirects to `data.nlr.gov`.
- **OpenTrinity** date is **2017** (USENIX ATC'18), not 2016.

## 6. Caveats & gotchas for ingest tooling

1. **No requested-walltime in cloud/GPU traces** (Helios, Acme, Philly, Alibaba, Google) — the
   key HPC feature is absent; model duration from resources/type/queue for those.
2. **FRESCO datadepot** is fetched via Globus (see the FRESCO row above).
3. **Atlas ftp.pdl.cmu.edu** blocks HEAD/range → can't size remotely; download the (small) gz.
4. **ALCF `reports.alcf.anl.gov`** blocks scripted user-agents → send browser headers.
5. **Schema heterogeneity** across schedulers (SLURM `sacct`, Cobalt/PBS DJC, Torque
   key=value, LSF `bjobs`, SWF, GWF) → the normalize step needs a per-source mapping (this is
   exactly what the descriptor `mapping` + `oda.mapping` translation is for).
6. **Big-payload separation**: MIT Supercloud (S3 prefix), Blue Waters (Globus subfolder),
   FRESCO (skip TACC-Stats), Lassen (git-LFS include), Alibaba (skip hourly tables), Acme (skip
   `utilization/`) — in every case the job table is a tiny, separable slice of a huge dataset.
7. **License variance**: mostly CC-BY-4.0; CC0 (C6EnPLS); `nlr-data-1.0` (Eagle/Kestrel,
   non-SPDX); several **unstated** (ALCF, Blue Waters, Titan RUR, Summit) — record per-dataset
   and, since the fetch subsystem never redistributes bytes, verify only before any republish.

## 7. Deferred to later phases

- **Power/energy:** M100 (49.9 TB), PM100 power cols, NLR Eagle node/GPU power (#8/#9), NLR
  GenAI power (#10), C6EnPLS, Adastra power, Frontier HPL, SURFace telemetry.
- **Failure/reliability:** CFDR, FTA, Backblaze, Loghub, Oliner-Stearley 5 logs, Summit GPU
  DBE, Titan GPU Lifetimes, HMDR/m888.
- **Anomaly detection:** HPC-ODA, Antarex, Prodigy/HPAS/Taxonomist.
- **I/O:** Darshan. **Network:** Monet.

## 8. Next steps

1. **Sign off** on the recommended download set (§1) and any optional additions.
2. **Curate descriptors** (P4b): for each chosen dataset, fetch the premium slice once, pin
   per-file `sha256` + bytes, author the `oda.dataset.v0.1.0` descriptor, and register it in
   the registry (v0.2.0). This is the step that needs real network + the real bytes.
3. **Fetch-backend extras** (as needed): git-lfs, s3, and new Globus / HuggingFace / Aliyun-OSS
   backends (or route them through the `manual` kind initially).
4. **Ingest + benchmark** the first dataset end-to-end (DoD-5), starting with **NREL Eagle
   (#4)** — it's CC-BY, tiny, and already native to the repo's `ingest jobs-parquet` pipeline.
