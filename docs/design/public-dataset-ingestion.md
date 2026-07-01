# Design Spec — Public Dataset Ingestion

**Status:** Draft (RFC)
**Date:** 2026-07-01
**Targets:** a new `datasets` module (`src/hpc_oda_commons/datasets/`)
**Decisions locked (session review):**

- **Network posture:** quarantined stdlib fetch — core uses `urllib`; special
  backends (S3, git-LFS, BigQuery) are optional install extras; gated datasets
  use a `manual` mode that verifies a user-supplied file by checksum. Fetch is
  opt-in and refused under `HPC_ODA_OFFLINE` unless already cached. Zero new hard
  dependencies.
- **Catalog home:** extend the registry with a `dataset` entry_type via a Schema
  Evolution Request (registry `v0.1.0` → `v0.2.0`).
- **Phase-1 scope:** runtime + power datasets that map to existing/near-existing
  schemas and existing models.
- **Redistribution:** fetch-from-source only; checksum-verify; never mirror/host
  dataset bytes.
- **Size discipline:** refuse downloads ≥ 5 GB by default (override via
  `--max-size` / `--slice` / `--all`); every dataset ships a curated `default`
  slice under the gate.
- **Default slice:** the most recent full period of the dataset.

---

## 1. Goal & non-goals

**Goal:** Turn "find → get → filter → preprocess a public HPC dataset" from a
per-institution, per-year re-implementation into one declarative, reproducible
command that yields a canonical ODA table a recipe can benchmark.

**Non-goals (Phase 1):** no mirroring/redistribution; no failure/anomaly/
telemetry schemas or models yet; no TB-scale telemetry (M100 49.9 TB, MIT
Supercloud 2 TB). Phase 1 is job/power tables that map to `oda.job.v0.2.0`.

## 2. Where it fits

Extends the existing three-stage pipeline with a **stage-0 "acquire"** that
produces the same canonical artifact the current ingest path does — so everything
downstream (recipe → benchmark → leaderboard) is unchanged:

```
oda.dataset.yml (descriptor) ──registered──► registry entry (discovery via browse/info)
      │
      ▼ [FETCH]     kind: http|zenodo|osti|oedi|github|git-lfs|s3|manual
      │             → .hpc_oda/cache/datasets/<id>/raw/… + <id>.lock.json  (sha256-pinned, offline-refused)
      ▼ [DECODE]    format: parquet|csv|swf|json|log|tar → intermediate rows
      ▼ [NORMALIZE] map → oda.job.v0.2.0 (+power columns)   ← REUSES apply_mapping_spec + validate_parquet_with_quality
      │             → data/datasets/<id>/{data.parquet, manifest.json, quality.json}
      │
      └──► recipe.dataset.table_path ──► hpc-oda benchmark ──► result ──► leaderboard
```

Only **FETCH** is a substantially new subsystem. DECODE is thin. NORMALIZE,
artifacts, provenance, and catalog all reuse existing machinery.

## 3. Module layout (expand the existing `datasets/` package)

```
src/hpc_oda_commons/datasets/
├── synthetic.py, synthetic/           # EXISTING (bundled synthetic generator + data) — untouched
├── descriptors/                       # NEW: bundled oda.dataset.*.yml, one per dataset (like recipes/)
│   ├── job-runtime/  └─ job-power/
├── catalog.py                         # NEW: load/query descriptors; feed registry browse/info
├── fetch/
│   ├── base.py                        # Fetcher Protocol, FetchPlan, cache + lockfile, checksum, offline gate
│   ├── http.py                        # stdlib urllib backend + zenodo/osti/oedi/github URL resolvers
│   ├── manual.py                      # gated datasets: print instructions, verify user-supplied file by sha256
│   └── extras/  (s3.py, gitlfs.py, bigquery.py)   # LATER, behind optional install extras
├── decode/
│   ├── base.py                        # Decoder Protocol
│   └── parquet.py, csv.py, swf.py     # Phase 1 (tar_logs.py, json.py later)
├── normalize.py                       # thin wrapper delegating to ingest.jobs_parquet.apply
└── prepare.py                         # orchestrator: fetch → decode → normalize → validate → manifest
```

Descriptors are bundled package-data exactly like `recipes/**/*.yml`; the registry
gets lightweight `dataset` entries (`reference.kind=path`) pointing at them — the
same pattern recipes already use.

## 4. Core abstraction — the Dataset Descriptor (`oda.dataset.v0.1.0`, NEW schema family)

One YAML per dataset, fully declaring the ETL. Sketch (F-DATA / Fugaku):

```yaml
dataset_id: dataset.job_power.fdata_fugaku
schema_version: oda.dataset.v0.1.0
name: F-DATA (Fugaku Job Records)
version: 1.0.0
description: ...
problem_domains: [job-runtime-prediction, job-power-prediction]
systems: [Fugaku];  providers: [RIKEN R-CCS, Univ. Bologna]
citation: { doi: 10.5281/zenodo.11467483 };  license: { spdx: CC-BY-4.0, gated: false }
tags: [fugaku, power, energy, parquet]

size:                                     # surfaced in `datasets list/info`; drives the fetch guardrail (§5)
  default_bytes: 3200000000               # total download for the DEFAULT slice
  full_bytes:    480000000000             # everything (informational)
  rows_hint: "~24M jobs"

source:
  kind: zenodo
  record: "11467483"
  resources:                              # full pinned catalog — every resource checksummed
    - { filename: 23_04.parquet, url: https://zenodo.org/.../23_04.parquet, sha256: <hex>, bytes: 280000000 }
    - { filename: 21_04.parquet, url: https://zenodo.org/.../21_04.parquet, sha256: <hex>, bytes: 210000000 }
    # … all monthly files …
  slices:                                 # named selections over `resources` (cream-of-the-crop curation)
    default: recent                       # what `fetch`/`prepare` use unless --slice/--all
    recent: { description: "most recent full year", include: ["23_*.parquet"] }
    full:   { description: "Mar 2021 – Apr 2024",   include: ["*.parquet"] }

decode: { format: parquet, options: {} }

targets:
  - schema: oda.job.v0.2.0
    capabilities:                         # EXPLICIT model-suitability, validated against `mapping` outputs
      - { problem_domain: job-runtime-prediction, target_column: runtime_seconds }
      - { problem_domain: job-power-prediction,    target_column: maxpcon }
    suitable_models: [model.job_runtime_xgboost, model.job_power_uopc]   # optional curated hint
    mapping:                              # reuses apply.py transform vocab (timestamp/duration/memory/hash_identifier)
      job_id:          { from: jobid,   type: hash_identifier }
      start_time:      { from: sdt,     type: timestamp, format: epoch_s }
      end_time:        { from: edt,     type: timestamp, format: epoch_s }
      runtime_seconds: { from: duration, type: duration, unit: seconds }
      maxpcon:              { from: maxpcon }     # power target — carried via additionalProperties:true
      user:                 { from: usr,   type: hash_identifier }
      name:                 { from: jnam }
      processors_requested: { from: cnumr, type: integer }
      nodes_requested:      { from: nnumr, type: integer }
    select: [job_id, start_time, end_time, runtime_seconds, maxpcon, user, name,
             processors_requested, nodes_requested]   # keep only what models need
    filter: { completed_only: true }                  # optional row filter
    sample: { rows: 500000, strategy: stratified, by: [partition], seed: 42 }  # optional, deterministic
    output: { id: fdata_fugaku, path: data/datasets/fdata_fugaku/data.parquet }
```

The mapping deliberately reuses the existing transform types so we don't reinvent
normalization. For `manual`/gated datasets (Alibaba, Google), `source.kind:
manual` carries `instructions:` + expected `sha256:`, and `fetch` verifies the
file the user supplies rather than downloading.

### Size metadata, slices, and model-suitability

Three additions make the descriptor size-aware, subset-friendly, and explicit
about which models it can drive:

- **`size`** — declared download size for the default slice (`default_bytes`),
  the full dataset (`full_bytes`), and a `rows_hint`. Surfaced in
  `datasets list`/`info` and drives the fetch guardrail (§5).
- **`source.slices`** — named selections over the pinned `resources` list, with a
  curated **`default`** slice that is small, recent, and representative — the
  "cream of the crop." `fetch`/`prepare` use `default` unless `--slice <name>` or
  `--all` is given. This is how we avoid pulling a TB when a few hundred MB of the
  most relevant months will do, using only file selection (stdlib-friendly, no
  partial-read machinery).
- **`targets[].capabilities`** — an explicit, *validated* list of
  `{problem_domain, target_column}` pairs stating exactly which model types the
  target can drive (runtime via `runtime_seconds`, power via `maxpcon`). An
  optional `suitable_models` gives curated model ids. Descriptor validation
  **rejects a capability whose `target_column` the `mapping` doesn't produce**, so
  a dataset can't claim power-suitability without actually emitting `maxpcon`.
- **`targets[].select` / `filter` / `sample`** trim the *canonical* table:
  column projection, row filters (e.g. completed jobs only), and an optional
  **deterministic** stratified sample (fixed `seed`, recorded in the manifest) to
  cap very large prepared tables without sacrificing reproducibility.

### Power rides `oda.job.v0.2.0` — no new schema in Phase 1

- `oda.job.v0.2.0` is `additionalProperties: true` (`schemas/oda/job/v0.2.0.json:6`),
  so power/energy columns ride along in the *same* canonical table as long as the
  required job fields (`job_id`, `start_time`, `end_time`, `runtime_seconds`) are
  present.
- The UoPC model already resolves columns by alias (`models/job_power_uopc/model.py:24-40`):
  target `maxpcon`; features `user`/`usr`, `name`/`jnam`,
  `processors_requested`/`cnumr`, `nodes_requested`/`nnumr`, order-by
  `end_time`/`edt`. Those aliases are Fugaku F-DATA's native names — so normalize
  emits canonical names and the existing model consumes them.

A dedicated `oda.power.*` family is deferred until/unless a Phase-1 dataset
genuinely lacks the required job-timing fields.

## 5. Fetch subsystem (the one genuinely new piece)

- **Fetcher Protocol:** `plan(descriptor) -> FetchPlan` (resolves resource URLs)
  and `fetch(plan, cache_dir) -> [CachedResource]`.
- **Backends:** `http.py` (stdlib `urllib`, covers Zenodo/OSTI/OEDI/GitHub direct
  downloads — the majority of Phase-1 datasets); `manual.py` (gated). S3/git-LFS/
  BigQuery are **optional extras** (`pip install hpc-oda-commons[fetch-s3]`),
  never core deps.
- **Checksum + lockfile:** each resource verified against descriptor `sha256`; a
  `<id>.lock.json` records resolved URLs, checksums, byte sizes, `fetched_at`,
  descriptor hash, and tool version → the reproducibility backbone.
- **Offline gate:** `HPC_ODA_OFFLINE=1` → `fetch` refuses all network;
  `prepare`/`benchmark` still work if raw bytes are cached and checksums verify.
  Fetch is **always opt-in** — never triggered implicitly by `benchmark`/`validate`.
- **Cache:** `.hpc_oda/cache/datasets/<id>/raw/…` (project-local, matches the
  existing synthetic-cache convention), overridable via `--cache` /
  `HPC_ODA_CACHE_DIR`.
- **Size guardrail:** before downloading, `fetch` sums the selected slice's
  `bytes`. Default policy: **refuse any download ≥ 5 GB** (`--max-size`, default
  `5GB`, or `HPC_ODA_MAX_DOWNLOAD`) with a message showing the size and how to
  proceed (`--slice <smaller>`, raise `--max-size`, or `--all` to force). Between
  1–5 GB it prints a heads-up and proceeds; unknown/`null` size warns and requires
  `--yes`. Slice sizes are curated so each Phase-1 dataset's `default` slice clears
  the gate.
- **Subset selection:** `fetch`/`prepare` operate on the descriptor's `default`
  slice unless overridden — the primary "download only what's worth it" lever.
  (A later optional `[fetch-arrow]` extra can add HTTP-range column/row-group
  pushdown for single-file parquet, making even in-file subsetting
  download-efficient; out of Phase 1.)

## 6. Decode + Normalize (mostly reuse)

- **Decode** → `list[dict]` rows: `parquet.py`/`csv.py` are trivial; `swf.py`
  parses the Parallel Workloads Archive's Standard Workload Format (unlocks the
  ~40 PWA logs later).
- **Normalize** → delegates to `ingest/jobs_parquet/apply.py::apply_mapping_spec`
  (batched at 50k rows — handles F-DATA's ~24M rows), then
  `schema/validator.py::validate_parquet_with_quality`, then writes `manifest.json`
  via `kernel.artifacts`. Manifest gains dataset provenance (descriptor
  id/version/hash, source checksums, mapping hash) — expected to fit the existing
  `oda.manifest.v0.1.0` `inputs/transformations/provenance` structure; if not,
  that's a small manifest SER.

## 7. Catalog / registry integration (SER → registry v0.2.0)

- Add `dataset` to the `entry_type` enum + an `allOf` branch (dataset requires
  `problem_domain`, `reference`; `license` recommended). `test_registry.py` only
  exact-asserts the *model* list, so adding dataset entries is safe.
- `hpc-oda browse --type dataset [--domain … --system … --tag …]` and
  `hpc-oda info dataset.<id>` come for free via the existing index. One commons,
  one discovery surface.
- This is a change to a versioned public schema → **requires an SER issue** per
  `CONTRIBUTING.md` §9.

### Model-suitability (which dataset for which model)

Discovery answers "which datasets can drive model X?" by matching each dataset
target's `capabilities` (§4) against the model's declared input requirements
(problem domain + required target column). This stays robust as models are added —
datasets declare capabilities, models declare needs, the catalog matches — while
`datasets info` renders a human-readable **"Useful for:"** list (domains + models +
the target column each uses). `datasets list --for-model <id>` / `--domain <d>`
filter on the same match.

## 8. CLI surface (`hpc-oda datasets`)

| Command | Does |
|---|---|
| `datasets list [--for-model <id>] [--domain <d>] [--max-size <sz>] [--tag …]` | Discovery (= `browse --type dataset`); shows size, default slice, model-suitability, and ⚠ large/gated flags |
| `datasets info <id>` | License, size + available slices, fetch plan, targets, field mapping, **Useful for:** models/domains, gated? |
| `datasets fetch <id> [--slice <name>\|--all] [--max-size <sz>] [--yes]` | Download the selected slice + checksum-verify → cache + lock; enforces the size guardrail; prints license, prompts on gated; offline-refused unless cached |
| `datasets prepare <id> [--slice <name>] [--target <schema>]` | Full ETL on the selected slice → canonical table + manifest + quality; idempotent (skips if lock+hash match) |
| `datasets recipe <id> --model <id>` | *(nice-to-have)* scaffold a benchmark recipe pointing at the prepared table — closes the loop to `benchmark` |

## 9. Testing & Definition of Done (add DoD-5)

- **Unit:** descriptor schema validation; fetch via `file://` URLs (stdlib
  `urllib` supports it) + checksum + lock determinism + offline-refusal; each
  decoder on tiny fixtures (5-row SWF, 3-row CSV, tiny parquet); normalize incl.
  power-column passthrough; catalog/registry filtering.
- **Integration (DoD-5):** a tiny bundled "public" dataset served via `file://` →
  `datasets prepare` → schema-valid canonical table → `benchmark` with an existing
  model → result bundle. **Fully offline; CI never touches real network** (real-URL
  fetches are opt-in/manual only). Mirrors the DoD-3 pattern.

## 10. Phasing — each a green-gated PR, small and reviewable

- **P0 — RFC + SERs** *(this doc)*: design issue + registry-v0.2.0 SER +
  `oda.dataset.v0.1.0` proposal.
- **P1 — schema + descriptor model:** `oda.dataset.v0.1.0` JSON schema, loader,
  `Descriptor` dataclass, validation, tests. No network.
- **P2 — fetch:** stdlib http backend + cache + lockfile + checksum + offline gate
  + manual/gated + `datasets fetch`. Tests via `file://`.
- **P3 — decode + normalize + prepare:** decoders (parquet/csv/swf) + normalize
  wrapper + `prepare` orchestrator + manifest/quality + tests.
- **P4 — catalog + registry SER impl:** registry v0.2.0, `browse/info` wiring,
  author first descriptors (F-DATA, PM100, Adastra, Eagle/Kestrel, CC-IN2P3,
  C6EnPLS), register, DoD-5.
- **P5 — docs + loop-closing:** `docs/how-to/ingest-public-datasets.md`, reference
  updates, `datasets recipe` helper.

**Deferred (post-Phase-1):** failure/RAS + anomaly-telemetry schemas & models;
extra fetch backends (S3/git-LFS/BigQuery); bulk PWA SWF importer.

## 11. Open questions for the RFC

1. **Power schema:** ride `oda.job.v0.2.0` + canonical power columns (recommended)
   vs. a dedicated `oda.power.*` family — revisit only if a Phase-1 dataset can't
   produce required job-timing fields.
2. **Checksum sourcing:** maintainer curates descriptors by fetching once and
   pinning `sha256` (Zenodo also exposes md5 via API for cross-check).
3. **Descriptor authorship burden:** Phase 1 hand-curates ~6 descriptors; the
   community contributes the rest, registered like recipes.
4. **Manifest fit:** confirm dataset provenance fits `oda.manifest.v0.1.0` without
   a schema bump.
5. **Per-dataset slice curation:** the policy is decided — *most recent full
   period* under a *5 GB refuse-by-default* ceiling; remaining work is picking the
   right period per dataset, and revisiting stratified sampling only if a model
   needs lifetime coverage.

---

## Appendix — Phase-1 candidate datasets (from `docs/hpc_operational_datasets.xlsx`)

Datasets that map to `oda.job.v0.2.0` (+ power columns) and existing models:

| Dataset | System | Domain(s) | Format | Access | Source kind |
|---|---|---|---|---|---|
| F-DATA | Fugaku | runtime, power | Parquet | Open (Zenodo, CC) | zenodo |
| PM100 | Marconi100 | power | Parquet | Open (Zenodo) | zenodo |
| NLR Eagle Jobs + Energy | Eagle | runtime, power | Parquet/Hive | Open (DOI; data.nlr.gov) | osti/oedi |
| NLR Kestrel Jobs | Kestrel | runtime, power | Parquet/Hive | Open (DOI; data.nlr.gov) | osti/oedi |
| Adastra Jobs MI250 | Adastra | runtime, power | Parquet/CSV | Open (Zenodo) | zenodo |
| CC-IN2P3 2024 Workload | CC-IN2P3 | runtime | Slurm/CSV | Open (Zenodo) | zenodo |
| C6EnPLS | CRESCO6 | power/energy | CSV | Open (Zenodo/GitHub) | github/zenodo |

Each Phase-1 descriptor ships a curated **`default` slice** sized under the 5 GB
guardrail (e.g. F-DATA: one representative year; Eagle/Kestrel: a recent
partition); `--all` fetches the full dataset with the large-download warning.
TB-scale sets (M100 49.9 TB, MIT Supercloud 2 TB) stay out of Phase 1.

Deferred domains present in the catalog: failure/reliability (CFDR, FRESCO,
Loghub, FTA), anomaly detection (HPC-ODA, Antarex, Prodigy), GPU reliability
(Titan, Summit), I/O (Darshan), network (Monet), and the ~40-log Parallel
Workloads Archive (SWF).
