# Datasets

This repo follows a **manifest-first** dataset policy.

## In-Repo Data

Only tiny synthetic datasets are stored in-repo to support offline demos and CI.
The runtime dataset lives under:

- `src/hpc_oda_commons/datasets/synthetic/job-runtime/tiny/`

## External Data

Larger datasets should be referenced via manifests and external hosting (e.g.,
Zenodo). See:

- `datasets/external/zenodo_links.yml`
- `datasets/external/golden_datasets.yml`

## Public dataset ingestion

The repo also ships a descriptor-based ingestion subsystem: 25 public runtime
datasets are registered as `oda.dataset.v0.1.0` descriptors under
`src/hpc_oda_commons/datasets/descriptors/` and fetched/normalized with
`hpc-oda datasets fetch <id>` / `hpc-oda datasets prepare <id>`. See:

- [`docs/datasets/curation-status.md`](../docs/datasets/curation-status.md) — registered datasets + roadmap
- [`docs/datasets/external-datasets.md`](../docs/datasets/external-datasets.md) — datasets needing manual/gated retrieval
