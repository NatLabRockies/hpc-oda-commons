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
