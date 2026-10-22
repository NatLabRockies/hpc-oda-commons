# External datasets (not auto-fetched)

hpc-oda-commons prefers **lightweight, dependency-free fetching**. Every *registered* dataset
pins a `sha256` for each of its files, and most also pin a direct HTTPS URL, which
`hpc-oda datasets fetch` and `prepare` download with the stdlib fetcher, with no extra
tooling. Sources that *look* like they need a special backend usually turn out to be direct
HTTPS anyway: public **S3**, **Hugging Face** `resolve` links, **git-LFS** media URLs and
presigned redirects all work with the plain HTTPS fetcher. Always live-check the fetch path:
"gated" labels are often wrong.

Datasets that need a manual download are registered with `source.kind: manual`: you download
the files yourself, and `datasets prepare <descriptor> --from <folder>` checks them against
their pinned `sha256` and prepares them like any other. The three ALCF DJC datasets work this
way ([how to download them](alcf-djc-ingest.md)), and so does a dataset of your own
([Benchmark your own data](../how-to/benchmark-your-data.md)).

This page lists datasets that aren't registered because they can't be fetched that way.

## When a download fails checksum verification

A checksum mismatch means the bytes on disk are not the bytes the descriptor pins. Before
concluding that the source file changed and re-pinning the `sha256`, check what actually
arrived:

- **An HTML page came back instead of the file.** A landing or login page, or a network
  appliance answering on the source's behalf, is served with HTTP 200, so the download
  "succeeds" and the file only fails verification afterwards. `datasets fetch` and `prepare`
  stop with an explicit "the server returned an HTML page" error. Fetch the URL by hand
  (`curl -sSL <url> | head -c 200`) and see what comes back.
- **The source really was re-issued.** Confirm by downloading in a known-good environment and
  hashing it yourself (`shasum -a 256 <file>`); only then update `sha256` and `bytes`, and
  re-check row counts and date ranges before trusting the new file.

If you already hold a verified copy, put it at
`.hpc_oda/cache/datasets/dataset.<name>/raw/<filename>` (or under `HPC_ODA_CACHE_DIR`) and
re-run `prepare`: a cached file whose hash matches is used as-is, with no network access. A
cache folder under a dataset's id from before #249 (`dataset.job_runtime.<name>`) is adopted.

## Datasets

### Blue Waters workload (NCSA)

- **What:** Torque/Moab accounting for the Blue Waters supercomputer, Apr 2013 – Sep 2016,
  ~4.5M jobs. Records include `Resource_List.walltime` (requested) and
  `resources_used.walltime`, `ctime`/`qtime`/`etime`, start/end, `nodect`, `exec_host`,
  `Exit_status` — **primary-quality** (it has requested walltime).
- **Where:** **Globus only** (the [NCSA data-sets page](https://bluewaters.ncsa.illinois.edu/data-sets)
  provides no direct HTTPS, just a Globus file-manager link to collection
  `854c1a5c-fa9f-4df4-a71c-407a33e44da0`). Grab only the **Torque accounting** subfolder
  (~4–5 GB); skip the 95 TB LDMS telemetry.
- **Format:** per-day `key=value` text files. Registering it needs a Torque-accounting decoder
  first; until then, convert it to CSV or Parquet yourself and write a `manual` descriptor for
  the result.
- **License:** none stated — cite the NSF Blue Waters project.
