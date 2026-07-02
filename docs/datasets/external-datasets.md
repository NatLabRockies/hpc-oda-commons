# External datasets (not auto-fetched)

hpc-oda-commons prefers **lightweight, dependency-free fetching**: every *registered* dataset
pins a direct-HTTPS URL + `sha256`, and `hpc-oda datasets fetch` / `prepare` downloads and
normalizes it with the stdlib fetcher — no extra tooling. (Most sources that *look* like they
need a special backend turn out to be direct HTTPS anyway — public **S3**, **HuggingFace**
`resolve`, **git-LFS** media URLs, and presigned 302 redirects are all handled by the plain
`http` backend; see [`curation-status.md`](curation-status.md).)

A couple of valuable datasets aren't auto-fetched: **Blue Waters** needs a **Globus** login (no
direct HTTPS at all), and **Alibaba GPU-v2026** *is* a plain-HTTPS URL but its Aliyun-OSS host is
not resolvable from every network (it's blocked from the environment these descriptors were built
in, so its checksum couldn't be pinned). They're documented here so you can retrieve them yourself
and turn them into canonical `oda.job.v0.2.0` tables.

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

### Alibaba GPU-v2026 (Alibaba ASI)

- **What:** `asi_opensource_job_execution_summary` from Alibaba's ASI GPU platform (155k GPUs,
  6 months, OSDI'26). Fields include `duration_hours`, `schedule_delay_sec` (queue wait),
  `gpu_request`, priority/type. **No requested-walltime** (Kubernetes GPU trace) → a secondary,
  cross-domain complement.
- **Where:** a plain-HTTPS public OSS URL — **not** an SDK (the
  [clusterdata download page](https://github.com/alibaba/clusterdata/blob/master/cluster-trace-gpu-v2026/docs/data_download.md)
  uses `curl -O`): `https://tre-clusterdata.oss-cn-hangzhou.aliyuncs.com/cluster-trace-gpu-v2026/data/asi_opensource_job_execution_summary.zip`
  (1,188,295,031 bytes; skip the huge `*_hourly.zip` telemetry). **Caveat:** that host did not
  resolve from the environment these descriptors were built in (DNS-blocked), so it isn't a
  registered/pinned dataset — but on a network that reaches `aliyuncs.com` it fits the normal
  lightweight fetch: download it, then use the wizard or a pinned `kind: http` descriptor.
- **Format:** ZIP → `part-000.parquet` (archive decode + a straightforward mapping handle it).
- **License:** research-use (see the Alibaba `clusterdata` repository).

---

*Note:* FRESCO (Purdue Anvil) and Lassen (LLNL, git-LFS) were initially expected to need Globus /
git-LFS, but both turned out to be reachable over plain HTTPS, so they are now normally-fetched
registered datasets (`dataset.job_runtime.fresco_anvil`, `dataset.job_runtime.lassen`). If a
"Globus/OSS-only" dataset later exposes an HTTPS path, prefer registering it normally.
