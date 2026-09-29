# Export datasets to a data catalog

`hpc-oda catalog export` writes one [MLCommons Croissant 1.0](http://mlcommons.org/croissant/1.0)
record per registered dataset, so the curated datasets can be registered in data catalogs
(for example the AmSC Data Catalog). It reads only the bundled descriptors: no downloads,
no data files.

```bash
hpc-oda catalog export                                      # all datasets → catalog/
hpc-oda catalog export -d dataset.job_runtime.pm100 -o out  # one dataset
```

Output: `<dataset_id>.json` per dataset plus `index.json`.

| Descriptor | Croissant record |
|------------|------------------|
| `name`, `description` | `name`, `description` |
| `citation.doi` / `citation.url` | `@id`, `citeAs`, `url` |
| `license` | `license` (SPDX URL, or the license note) |
| `tags`, `systems`, `problem_domains` | `keywords`, plus `oda:systems`, `oda:problemDomains` |
| `providers` | `creator` |
| `source.resources` | `distribution` (URL, sha256, size); gated files point at the provider's page |
| `targets[].mapping` | `recordSet` for columns read directly from a single Parquet/CSV file; every canonical column in `oda:canonicalFields` |

Every exported record loads with the reference `mlcroissant` library.
