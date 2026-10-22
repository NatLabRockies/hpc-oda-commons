# Dataset descriptors

A descriptor is a YAML file that says where a dataset's files are, how to read them, and how
their columns map onto the canonical job schema. `hpc-oda datasets fetch` and
`hpc-oda datasets prepare` take a descriptor's path, or a bundled dataset's name (`pm100`
or `dataset.pm100`), as does `hpc-oda recipes write`. Every bundled dataset has one in
[`src/hpc_oda_commons/datasets/descriptors/`](../../src/hpc_oda_commons/datasets/descriptors/),
and [Benchmark your own data](../how-to/benchmark-your-data.md) walks through writing one for
your own export.

The schema, `oda.dataset.v0.1.0`
([dataset/v0.1.0.json](../../src/hpc_oda_commons/schemas/oda/dataset/v0.1.0.json)), is the
full list of fields. This page explains what they do.

A complete example is the guide's
[`example_cluster.yml`](../how-to/benchmark-your-data/example_cluster.yml): a Slurm `sacct`
export with hashed users and power derived from the energy counter.

## About the dataset

| Field | Meaning |
|---|---|
| `dataset_id` | `dataset.<name>`. It names the data, not a task. |
| `schema_version` | `oda.dataset.v0.1.0`. |
| `name`, `version`, `description` | Shown on the dataset's card. Describe the source, not how it's used. |
| `systems`, `providers`, `tags` | Shown on the card. |
| `citation` | `doi` and `url` for the dataset itself, and `papers`: each a `title` with a `doi` or `url`. |
| `license` | `spdx`, plus `gated: true` when access needs registration or an agreement. |
| `size` | `default_bytes` and `full_bytes` drive the download size guard (`--max-size`). `rows_hint` is free text. |

`problem_domains`, `targets[].capabilities` and `targets[].suitable_models` are retired. They
are still accepted, but ignored.

## `source`: where the files are

- **`kind`:** `manual` for a file you supply with `--from`, such as your own export or a gated
  download. Every other kind (`http`, `zenodo`, `oedi`, `s3`, ...) is fetched over HTTPS from
  each resource's `url`. The kind records where that URL points.
- **`resources`:** one entry per file: `filename`, `sha256` and `bytes`, plus `url` unless the
  kind is `manual`. Fetching and preparing check every file against its `sha256`, so a prepared
  table is tied to exact inputs.
- **`instructions`:** for `manual`, how to get the file.
- **`slices`:** optional named subsets of the resources. `default` names the one fetched unless
  `--slice` or `--all` says otherwise; each entry in `available` lists filename globs under
  `include`.

## `decode`: how to read the files

`format` is one of `parquet`, `csv` (also TSV and other delimited text, with a `delimiter`
option), `swf` or `json`. Compressed and archived files (`.gz`, `.zip`, `.tar`, `.tar.gz`) are
unpacked first. `options` holds format settings: `delimiter`, `columns` (read only these),
`record_path` for JSON, and `member_glob` to pick files from an archive.

## `targets`: the tables to write

Each target writes one canonical table:

- **`schema`:** the output schema, `oda.job.v0.2.0`.
- **`mapping`:** the canonical columns, each with a rule (below).
- **`filter`:** optional row filters, applied after mapping:
  - `require_nonnull: [columns]`: drop rows missing any of them;
  - `require_positive: [columns]`: drop rows where a value is zero or less (missing values are
    kept);
  - `require_end_after_start: true`: drop rows whose start is after their end.
- **`select`:** optional list of the canonical columns to keep. It must keep the schema's
  required fields.
- **`sample`:** optional cap on the table: `rows`, with `strategy` `head`, `random` or
  `stratified` (`by` columns, `seed`).
- **`output`:** `id` and `path`, such as `data/datasets/<name>/data.parquet`.

What a dataset serves follows from what it maps. With `runtime_seconds` it serves runtime
prediction. With `avgpcon_per_node` or `maxpcon_per_node`, the power per node, it serves power
prediction (`TARGET_DOMAINS` in `src/hpc_oda_commons/datasets/descriptor.py`).

## Mapping rules

Each canonical column gets a rule:

```yaml
mapping:
  submit_time: { from: Submit, type: timestamp, format: iso8601 }
  runtime_seconds: { from: ElapsedRaw, type: duration, unit: seconds }
  user: { from: User, type: hash_identifier }
  avgpcon_per_node: { derive: "avgpcon / num_nodes_alloc" }
```

| Key | Meaning |
|---|---|
| `from` | The source column. |
| `type` | How to read the value. Omitted, it passes through unchanged. |
| `format` | For `timestamp`: `iso8601`, `epoch_s`, `epoch_ms` or `epoch_us`. |
| `unit` | For `duration`: `seconds`, `minutes`, `hours`, `hh:mm:ss` or `timedelta`. For `memory`: `bytes`, `kb`, `mb`, `gb`, `kib`, `mib` or `gib`. For `energy`: `j`, `kj`, `wh` or `kwh`. |
| `null_values` | Source values that mean "no reading", such as `[0]` for an energy counter. They become null. |
| `null_when` | Conditions on other source columns (`source` with `gt`, `ge`, `lt`, `le` or `in`). Where any holds, this column is null and the row is kept. |
| `trim_quantiles` | `[low, high]`, such as `[0.001, 0.999]`. After the filter, values outside these quantiles become null; the row is kept. |
| `derive` | Compute the column from others when its source is missing: `end_time - start_time` for `runtime_seconds`, or `<column> / <column>` of two mapped columns (which may be ratios themselves). |
| `synthesize` | `row_index`: number the rows, for a source with no job id. |

`trim_quantiles` takes its bounds from the whole prepared table, test months included: a
look-ahead in where the cut falls, not in any value. The manifest records, for each trimmed
column, the quantiles, the bounds and how many values became null.

The `type` values:

| Type | Reads |
|---|---|
| `timestamp` | A time, in the rule's `format`, to UTC. |
| `duration` | A length of time, in the rule's `unit`, to seconds. Markers such as `UNLIMITED`, and Slurm's "no limit" sentinels, become null. |
| `memory` | A size, in the rule's `unit`, to MB. |
| `memory_slurm` | A Slurm memory string such as `160G`, `2366M` or `90000Mn` (per node), to MB. A per-CPU value such as `4Gc` becomes null, since it needs the job's CPU count. |
| `energy` | Energy, in the rule's `unit`, to joules. |
| `hash_identifier` | A user, account or other name, hashed as it is read. Set `HPC_ODA_HASH_SALT` to salt the hashes. |
| `integer`, `number`, `string` | The value as that type. |
| `list_mean`, `list_max` | The mean or maximum of a list, such as a power trace. |
| `passthrough` | The value unchanged, as when `type` is omitted. |

The bundled descriptors are worked examples:
[`nlr_kestrel.yml`](../../src/hpc_oda_commons/datasets/descriptors/nlr_kestrel.yml) derives
power from Slurm's energy counter, and
[`pm100.yml`](../../src/hpc_oda_commons/datasets/descriptors/pm100.yml) reduces a power trace.

## Preparing a table

`hpc-oda datasets prepare <descriptor>` fetches (or, with `--from`, copies) and checks the
files, decodes them, maps them, filters them and runs the quality check. It works one batch of
rows at a time, so a table larger than memory can still be prepared. It writes the table, a
`manifest.json` and a `data.parquet.quality.json` beside it.
