# Architecture

Internal architecture reference for developers (and developer agents). For the
contribution process and coding standards, see
[`CONTRIBUTING.md`](../CONTRIBUTING.md). For using the tool, see
[`agent-usage.md`](agent-usage.md).

## Data flow

```text
Raw input: a public dataset's files, a site export, or a slurmctld log
  -> [datasets prepare] fetch (or --from), check checksums, decode, map onto the job
     schema, filter, quality-check: one batch of rows at a time
     [ingest] the jobs-parquet wizard or the slurmctld parser, for a first look
  -> Canonical ODA Table (Parquet) + Manifest + Quality Report
  -> [datasets characterize] the table's health and benchmark window: a runtime card
  -> [Embed] (optional) serialize submission-time fields, encode to a dense
             `embedding` column -> Embedded ODA Table + Embed Manifest
  -> [datasets ceiling] the lowest error a submit-time predictor could reach
  -> [Benchmark] read the recipe's window of the table, split it, train, score
  -> Result Bundle {result.json, metrics.json, provenance.json}
  -> [Leaderboard] one table per target, from the runs on the benchmark's protocol
  -> [cards] model and dataset cards, generated from the code, the files and the leaderboard
```

## Package layout (`src/hpc_oda_commons/`)

- **`qst/`** -- CLI entry point (Typer). Entry point: `hpc-oda = hpc_oda_commons.qst.cli:app`.
  Orchestrates only; business logic belongs in kernel/models/benchmark. `cli_reference.py`
  writes `docs/reference/cli.md` from the help text (`make docs-cli`).
- **`kernel/`** -- Core primitives: ODA tables, manifests, mapping specs, result bundles,
  provenance, hashing, metrics (`metrics.py`), serialization (`serialization.py`).
- **`models/`** -- Prediction models, one folder each with a `model.yml` (title, version,
  class, description, optional method notes) beside the code. `ids.py` maps the model ids
  from before #249 to the current ones; `feature_policy.py` is the submit-time feature
  allowlist.
  - `baseline/` -- the training (or window) mean.
  - `rolling_tabular/` -- the shared base for the rolling tabular models:
    `RollingTabularModel` + `RollingTabularConfig` (`base.py`), categorical preprocessing
    (OHE + SVD, `preprocessing.py`), the rolling split (`split.py`), and the on-disk store that
    shares daily preprocessing across runs (`artifact_store.py`, #213). Concrete models supply
    a regressor via the `_new_regressor()` seam, or override `_fit_predict`.
  - `xgboost/`, `random_forest/`, `mlp/` -- subclass `RollingTabularModel` and supply their
    regressor.
  - `moe_xgboost/`, `signature_memorizer/` -- subclass `RollingTabularModel` and override the
    fit/predict seam: a mixture of per-(user, walltime-bin) experts, and a lookup of identical
    past jobs.
  - `tfidf_knn/` -- TF-IDF + kNN with rolling evaluation (`evaluate()`); text handling in
    `vectorization.py`.
  - `embedding_knn/` -- kNN over a precomputed dense `embedding` column, with a selectable
    exact top-k backend (`backends.py`: numpy / torch / faiss).
  - `uopc/` -- user-based online power prediction: a fixed split (`evaluate_fixed()`), the
    paper protocol on a date cutoff (`evaluate_paper_reproduction()`,
    `evaluate_paper_sensitivity()`), and the shared rolling windows (`rolling.py`).
- **Targets** -- every model predicts the recipe's metric target (`runtime_seconds` by default):
  the runner sets `target_field` on target-configurable models and fails a model that cannot
  predict it (`benchmark/runner.py`, `recipe_target` / `_require_target`). Features come from
  `models/feature_policy.py`'s `feature_allowlist()`, which never includes the target.
- **`embeddings/`** -- Embedding module behind `hpc-oda embed`: leakage-guarded row
  serialization (`serialize.py` -- submission-time fields only, `prose`/`kv` formats),
  encoders (`encoders.py` -- `HashingEncoder` stub + `SentenceTransformerEncoder`), and the
  `embed_table` runner (`runner.py` -- chunk-cached/resumable, writes an embedded table +
  provenance manifest). Heavy deps are the optional `embed` extra.
- **`benchmark/`** -- Running and reporting benchmarks:
  - `recipes.py` (loading and validation), `runner.py` (execution, and `RUNNERS`, the table of
    which model runs under which split), `run_extras.py`, `table_rows.py`;
  - `results.py` and `tracks.py` (the leaderboard: one table per target, the protocols, which
    runs count), `arm_selection.py` (walk-forward choice among lookback arms),
    `leaderboard_display.py`;
  - `model_cards.py` and `dataset_cards.py` (the generated cards);
  - `recipe_writer.py` (`hpc-oda recipes write`).
- **`benchmarking/`** -- Dataset characterization and the cluster runner:
  `characterize.py` and `cards.py` (runtime cards), `ceiling.py` (error ceilings), and `hpc/`
  (`bench-matrix`: `matrix.py` plans the model × dataset matrix, `slice.py` cuts windows and
  holds `read_window`, which applies a recipe's declared window as a table is read,
  `orchestrate.py` and `config.py` drive a cluster from a local, gitignored site config).
- **`datasets/`** -- Descriptors (`descriptors/`, one flat folder; `descriptor.py`) and the
  prepare pipeline (`prepare.py`): `fetch/` (HTTPS or a manual file, checksum-verified),
  `decode/` (Parquet, CSV, SWF, JSON), `normalize.py` (mapping onto the job schema, streamed in
  batches). `ids.py` maps dataset ids from before #249. `synthetic.py` and `synthetic/` hold
  the tiny bundled datasets for offline runs.
- **`ingest/`** -- Ingestion pipeline: `jobs_parquet/` (profile, suggest, wizard, apply).
- **`adapters/`** -- Source parsers: `slurmctld/` (regex-based log parser, with its
  `adapter.yml`). Protocol: `SourceAdapter` in `base.py`.
- **`schema/`** -- JSON Schema validation (`validator.py`) and semantic quality rules
  (`quality_rules.py`): negative runtimes, start after end, missing values.
- **`intelligence/`** -- Library-level APIs, not used by any CLI command: mapping suggestions,
  a metadata graph over the registry, synthetic-data scoring. Documented in
  [the Python API](reference/python-api.md).
- **`registry/`** -- The registry (`build.py`), built when it loads from the models'
  `model.yml`, the adapters' `adapter.yml`, the dataset descriptors and the recipes (plus the
  runtime recipes the HPC matrix generates); `index.py` filters and looks it up. A snapshot
  file can be read instead with `--snapshot` (`snapshot.py`).
- **`integrity/`** -- Known-good code-hash ledger (`known_hashes.json`) recorded by
  `hpc-oda record-hash` and checked into result-bundle `integrity` blocks.
- **`utils/`** -- Small shared low-level helpers.
- **`tools/`** -- Report generation: `report/html.py` (HTML), `report/console.py` (Rich console).
- **`schemas/`** -- JSON Schema files (Draft 2020-12), versioned as `oda.<type>.v<MAJOR>.<MINOR>.<PATCH>`.
- **`recipes/`** -- Bundled benchmark recipe YAMLs (`job-runtime/`, `job-power/`). This is
  the only location for bundled recipes; custom/trial recipes go in a gitignored `recipes/`
  at the repo root.

## Testing conventions

- **Unit tests** (`tests/unit/`): fast, no external dependencies. Run them alone with
  `pytest -m "not integration"`; `make test` runs every test.
- **Integration tests** (`tests/integration/`, marked `integration`): end-to-end CLI
  workflows, including the own-data guide run as written. Run with
  `HPC_ODA_OFFLINE=1 make test-integration`. The native XGBoost integration test is opt-in,
  since some sandboxes block the OpenMP primitives it needs:
  `HPC_ODA_ENABLE_NATIVE_XGBOOST_IT=1 HPC_ODA_OFFLINE=1 pytest -q -m integration -k native_cli`.
- **Generated pages** are pinned by tests: `test_cli_reference.py`, `test_model_cards.py` and
  `test_dataset_cards.py` fail when a committed page differs from its generator's output, and
  `test_doc_links.py` checks every relative link and anchor in the docs. See
  [CONTRIBUTING.md](../CONTRIBUTING.md).
- **Recipes:** `scripts/validate_recipes.py` checks every bundled recipe; CI runs it.
- **Test fixtures**: generate in temp dirs (`tmp_path`), with the helpers in
  `tests/conftest.py`; never rely on gitignored files or machine-specific absolute paths. Keep
  fixtures deterministic and minimal. If a binary fixture is unavoidable, allowlist it in
  `.gitignore` and commit it.
- **Distinct fixtures**: when a test needs several of something, make them *different* unless
  sameness is what it is testing. Identical fixtures quietly exercise cases nobody meant to
  bless -- a leaderboard ordering test built two bundles for the same benchmark cell and
  asserted both appeared, which was the double-counting bug of #166 sitting in plain sight for
  months. Distinct values cost nothing and keep a fixture from asserting more than intended.
- **Monkeypatching models**: integration tests that exercise the XGBoost / TF-IDF kNN / MLP /
  UoPC benchmark paths monkeypatch the model on `runner.` (e.g. `runner.XGBoostModel`),
  not via `cli.` -- the models are imported in `benchmark/runner.py`.
- **Cross-environment numeric reproducibility** is a known limitation for fitted-model metric
  values; see [`known-issues.md`](known-issues.md) (issue #2).

## Documentation map

[`docs/index.md`](index.md) is the map of the docs. In short:

- `README.md` -- project overview and the first commands.
- `docs/agent-usage.md` -- using the tool (CLI workflow).
- `docs/how-to/`, `docs/reference/`, `docs/concepts/` -- guides and reference.
- `docs/benchmarking/` -- how the runtime and power benchmarks are run, by track.
- `docs/models/`, `docs/datasets/cards/`, `docs/reference/cli.md` -- generated; never edit
  them by hand.
- `CONTRIBUTING.md` -- contribution process, quality gates, coding standards.

If CLI commands, flags, or output paths change, run `make docs-cli`, and update
`docs/how-to/quickstart.md`, `docs/agent-usage.md` and the how-to that uses them.
