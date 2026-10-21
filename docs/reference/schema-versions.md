# Schema Versions

Every artifact the toolkit reads or writes names its schema as
`oda.<type>.v<MAJOR>.<MINOR>.<PATCH>`. The schemas are JSON Schema (Draft 2020-12) files under
[`src/hpc_oda_commons/schemas/oda/`](../../src/hpc_oda_commons/schemas/oda/). Each schema file is
the one home for its fields and which of them are required. A unit test checks that every
schema file is listed here.

## Current schemas

| Schema ID | What it describes | File |
|-----------|-------------------|------|
| `oda.job.v0.2.0` | A canonical job table: one row per job | [job/v0.2.0.json](../../src/hpc_oda_commons/schemas/oda/job/v0.2.0.json) |
| `oda.dataset.v0.1.0` | A dataset descriptor: where the data is and how it maps onto the job schema ([descriptors](descriptors.md)) | [dataset/v0.1.0.json](../../src/hpc_oda_commons/schemas/oda/dataset/v0.1.0.json) |
| `oda.mapping.v0.1.0` | A field mapping, as the jobs-parquet ingest wizard writes it ([mapping.yml](../how-to/ingest-jobs-parquet.md)) | [mapping/v0.1.0.json](../../src/hpc_oda_commons/schemas/oda/mapping/v0.1.0.json) |
| `oda.manifest.v0.1.0` | The lineage of an ingested or prepared table | [manifest/v0.1.0.json](../../src/hpc_oda_commons/schemas/oda/manifest/v0.1.0.json) |
| `oda.recipe.v0.1.0` | A benchmark recipe ([recipes](recipes.md)) | [recipe/v0.1.0.json](../../src/hpc_oda_commons/schemas/oda/recipe/v0.1.0.json) |
| `oda.mdl.v0.1.0` | One metric in a recipe: its name and target column | [mdl/v0.1.0.json](../../src/hpc_oda_commons/schemas/oda/mdl/v0.1.0.json) |
| `oda.result.v0.1.0` | A benchmark result bundle's `result.json` ([reading results](../how-to/interpret-results.md)) | [result/v0.1.0.json](../../src/hpc_oda_commons/schemas/oda/result/v0.1.0.json) |
| `oda.dataset_card.v0.1.0` | A runtime card (`*.card.json`): a table's health and its benchmark window | [dataset_card/v0.1.0.json](../../src/hpc_oda_commons/schemas/oda/dataset_card/v0.1.0.json) |
| `oda.ceiling.v0.1.0` | An error ceiling (`*.ceiling.json`): the lowest error a submit-time predictor could reach | [ceiling/v0.1.0.json](../../src/hpc_oda_commons/schemas/oda/ceiling/v0.1.0.json) |
| `oda.registry.v0.2.0` | The registry `hpc-oda browse` lists, which is built from the package's files | [registry/v0.2.0.json](../../src/hpc_oda_commons/schemas/oda/registry/v0.2.0.json) |

Some outputs carry a version string but have no schema file yet: `oda.leaderboard.v0.2.0`
(`leaderboard.json`), `oda.arm_ranking.v0.1.0` (`bench-matrix rank`), `oda.embedding.v0.1.0`
(the manifest `hpc-oda embed` writes) and `oda.hpc_site.v0.1.0` (the local cluster config).

## The job schema, v0.2.0

The job schema allows extra columns (`additionalProperties: true`), so a site can keep columns
of its own without breaking validation.

In v0.2.0 the timestamp columns (`start_time`, `end_time` and the optional `submit_time`) are
**native Arrow `timestamp(us, tz=UTC)`**, not ISO-8601 strings. The JSON Schema therefore gives
them no `type` or `format`. Their column type is checked structurally instead, by
`collect_job_table_type_issues` in `src/hpc_oda_commons/schema/validator.py`. A v0.1.0 table,
with string timestamps, fails validation against v0.2.0.

## Legacy schemas

| Schema ID | Replaced by |
|-----------|-------------|
| `oda.job.v0.1.0` | `oda.job.v0.2.0`: string timestamps became native timestamps |
| `oda.registry.v0.1.0` | `oda.registry.v0.2.0`: the registry is built from the package's files (#249) |

## Additive changes within a version

Optional fields and enum values are sometimes added to a schema in place. Documents that were
valid stay valid; only new ones use the additions.

- `oda.recipe.v0.1.0`:
  - `split.method: cutoff`, which requires `split.test_start`; `split.theta`, `split.k`,
    `split.theta_values`, `split.k_values` (#125). `split.embedding_field` (#204).
  - `split.target_encode_min_cardinality` and `split.target_encode_smoothing` (#172).
  - `split.node_count` (`allocated` | `requested`) and `split.max_alloc_ratio`, both for
    `method: cutoff` only. `split.uopc_features` (`zscore` | `embedding` | `balanced`), for
    `model.uopc` under `cutoff` or `rolling` (#222). `split.predictor` (`vote` | `mean` |
    `median`), for the same model and methods (#241).
  - `dataset.window` (`start`, `end`, `by`) and `dataset.require_nonnull` (#249).
  - `run.extras` (`save_predictions`, `save_model`).
- `oda.dataset.v0.1.0`:
  - Mapping transform types `list_mean` and `list_max`; `derive` also accepts
    `<field> / <field>` (#204).
  - Transform type `energy` and field option `null_values`; a ratio derive may use another
    ratio (#206). Field option `trim_quantiles`, applied after the target filter (#216). Field
    option `null_when` (#209).
  - `problem_domains` is no longer required. It, `targets[].capabilities` and
    `targets[].suitable_models` are accepted but ignored. The tasks a dataset serves come from
    the target columns its mapping produces (#249). Dataset ids name the data, not a task
    (`dataset.pm100`, formerly `dataset.job_runtime.pm100`).
  - `citation.papers`, the papers that describe a dataset, each a `title` with a `doi` or
    `url` (#249).
- `oda.mapping.v0.1.0`: field options `null_values` (#206) and `null_when` (#209).
- `oda.result.v0.1.0`: `provenance.code.code_changed_during_run`, written by
  `hpc-oda benchmark` (#215). `provenance.code` already allowed extra fields, so the schema
  file is unchanged.
- `oda.ceiling.v0.1.0`: `target_field`, the column the floor bounds; absent means
  `runtime_seconds` (#230). `split.skip_windows`, `split.windows_with_jobs` and
  `split.scored_windows`; `split.training_lookback_days` is no longer required or written,
  since nothing in a ceiling used it (#238).
- Semantics, not shape: a recipe's shared metric `target` is the column the model predicts, and
  a model that can't predict it fails the run (#204).
